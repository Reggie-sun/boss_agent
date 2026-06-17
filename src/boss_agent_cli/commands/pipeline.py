import time
from typing import Any

import click

from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands.chat_reply import execute_chat_reply
from boss_agent_cli.commands.friend_list_pages import collect_friend_list_items
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import error_contract_for_code, handle_auth_errors, handle_error_output, handle_output, render_simple_list
from boss_agent_cli.pipeline_state import build_pipeline_items, select_follow_up_candidates, select_read_no_reply_candidates


_DEFAULT_READ_NO_REPLY_MESSAGE = "您好，想跟进一下这个岗位目前是否还在招聘？如果方便的话可以继续沟通，我这边对岗位方向比较感兴趣。"


def _collect_pipeline_items(ctx: click.Context, *, command_name: str, now_ts_ms: int | None, stale_days: int) -> list[dict[str, Any]]:
	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]
	auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))

	with get_platform_instance(ctx, auth) as platform:
		chat_items, friend_error = collect_friend_list_items(platform)
		if friend_error is not None:
			code, message = platform.parse_error(friend_error)
			recoverable, recovery_action = error_contract_for_code(code)
			handle_error_output(
				ctx, command_name,
				code=code,
				message=message or "沟通列表获取失败",
				recoverable=recoverable,
				recovery_action=recovery_action,
			)
			return []
		interview_resp = platform.interview_data()
		if not platform.is_success(interview_resp):
			code, message = platform.parse_error(interview_resp)
			recoverable, recovery_action = error_contract_for_code(code)
			handle_error_output(
				ctx, command_name,
				code=code,
				message=message or "面试列表获取失败",
				recoverable=recoverable,
				recovery_action=recovery_action,
			)
			return []
		interview_data = platform.unwrap_data(interview_resp) or {}
		interview_items = interview_data.get("interviewList") or []

	return build_pipeline_items(
		chat_items=chat_items,
		interview_items=interview_items,
		now_ts_ms=now_ts_ms or int(time.time() * 1000),
		stale_days=stale_days,
	)


def _render_pipeline(data: list[dict[str, Any]], title: str) -> None:
	render_simple_list(
		data,
		title,
		[
			("阶段", "stage", "bold cyan"),
			("公司", "company", "green"),
			("职位/关系", "title", "yellow"),
			("来源", "source", "dim"),
			("未读", "unread", "red"),
			("已读", "msg_status", "dim"),
			("最近时间", "last_time", "dim"),
			("原因", "reason", ""),
		],
	)


def _send_read_no_reply_followups(
	ctx: click.Context,
	*,
	items: list[dict[str, Any]],
	message: str,
	max_send: int,
	dry_run: bool,
) -> list[dict[str, object]]:
	targets = select_read_no_reply_candidates(items)[:max_send]
	results: list[dict[str, object]] = []
	for target in targets:
		security_id = str(target.get("security_id") or "").strip()
		base_result = {
			"security_id": security_id,
			"stage": "read_no_reply",
			"message_sent": False,
			"error_message": "",
		}
		if not security_id:
			results.append({**base_result, "status": "missing_security_id"})
			continue
		if dry_run:
			results.append({**base_result, "status": "dry_run"})
			continue
		result = execute_chat_reply(
			ctx,
			security_id=security_id,
			message=message,
			send_resume=False,
		)
		results.append(
			{
				**base_result,
				"status": "sent" if result.message_sent else "send_failed",
				"message_sent": result.message_sent,
				"error_message": result.error_message,
			}
		)
	return results


@click.command("pipeline")
@click.option("--days-stale", default=3, type=int, help="超过 N 天未推进则标记为 follow_up")
@click.option("--now-ts-ms", default=None, type=int, help="测试用：覆盖当前时间戳（毫秒）")
@click.pass_context
@handle_auth_errors("pipeline")
def pipeline_cmd(ctx: click.Context, days_stale: int, now_ts_ms: int | None) -> None:
	if not require_compliance_allowed(ctx, "pipeline"):
		ctx.exit(1)

	items = _collect_pipeline_items(ctx, command_name="pipeline", now_ts_ms=now_ts_ms, stale_days=days_stale)
	handle_output(
		ctx,
		"pipeline",
		items,
		render=lambda data: _render_pipeline(data, "pipeline"),
		hints={"next_actions": ["boss follow-up", "boss chat", "boss interviews"]},
	)


@click.command("follow-up")
@click.option("--days-stale", default=3, type=int, help="超过 N 天未推进则视为 follow_up")
@click.option("--now-ts-ms", default=None, type=int, help="测试用：覆盖当前时间戳（毫秒）")
@click.option("--send-read-no-reply", is_flag=True, help="对 read_no_reply 候选生成或发送主动跟进消息")
@click.option("--message", default=_DEFAULT_READ_NO_REPLY_MESSAGE, show_default=True, help="read_no_reply 主动跟进消息")
@click.option("--max-send", default=1, type=click.IntRange(1, 5), show_default=True, help="本次最多处理的 read_no_reply 数量")
@click.option("--dry-run/--live-send", default=True, show_default=True, help="默认只预览；--live-send 才实际发送")
@click.pass_context
@handle_auth_errors("follow-up")
def follow_up_cmd(
	ctx: click.Context,
	days_stale: int,
	now_ts_ms: int | None,
	send_read_no_reply: bool,
	message: str,
	max_send: int,
	dry_run: bool,
) -> None:
	if not require_compliance_allowed(ctx, "follow-up"):
		ctx.exit(1)

	items = _collect_pipeline_items(ctx, command_name="follow-up", now_ts_ms=now_ts_ms, stale_days=days_stale)
	candidates = select_follow_up_candidates(items)
	if send_read_no_reply:
		clean_message = message.strip()
		if not clean_message:
			handle_error_output(
				ctx,
				"follow-up",
				code="INVALID_PARAM",
				message="--message 不能为空",
				recoverable=True,
				recovery_action="传入非空 --message 后重试",
			)
			return
		if not dry_run and not bool(ctx.obj.get("config", {}).get("boss_rag_send_enabled", False)):
			handle_error_output(
				ctx,
				"follow-up",
				code="SEND_DISABLED",
				message="主动跟进发送未开启：需要显式设置 boss_rag_send_enabled=true，并使用 --live-send。",
				recoverable=True,
				recovery_action="先 dry-run 复核，确认后设置 boss_rag_send_enabled=true 再加 --live-send。",
			)
			return
		send_results = _send_read_no_reply_followups(
			ctx,
			items=candidates,
			message=clean_message,
			max_send=max_send,
			dry_run=dry_run,
		)
		handle_output(
			ctx,
			"follow-up",
			{
				"candidates": candidates,
				"send_results": send_results,
				"dry_run": dry_run,
				"message": clean_message,
				"max_send": max_send,
			},
			render=lambda data: _render_pipeline(data["candidates"], "follow-up"),
			hints={
				"next_actions": [
					"复核 send_results 后，如确需发送，设置 boss_rag_send_enabled=true 并加 --live-send",
					"boss chat",
				]
			},
		)
		return
	handle_output(
		ctx,
		"follow-up",
		candidates,
		render=lambda data: _render_pipeline(data, "follow-up"),
		hints={"next_actions": ["boss chat", "boss mark <security_id> --label 沟通中"]},
	)
