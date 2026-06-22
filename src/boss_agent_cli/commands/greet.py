import json
import random
import time

import click

from boss_agent_cli.api.endpoints import (
	JOB_TYPE_CODES,
	SCALE_CODES,
	STAGE_CODES,
)
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.cache.store import CacheStore
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import (
	handle_auth_errors,
	handle_error_output,
	handle_output,
	render_batch_operation_summary,
	render_message_panel,
)
from boss_agent_cli.search_filters import (
	BOSS_INDUSTRY_FILTER_CHOICES,
	SearchFilterCriteria,
	SearchPipelinePlatformError,
	requires_extended_prefilter_scan,
	resolve_welfare_keywords,
	run_search_pipeline,
)


_BATCH_GREET_STOP_ERROR_CODES = (
	"RATE_LIMITED",
	"GREET_LIMIT",
	"TOKEN_REFRESH_FAILED",
	"NETWORK_ERROR",
	"AUTH_EXPIRED",
	"ACCOUNT_RISK",
)
_GREET_AGENT_DISCLOSURE = "我是候选人的求职助理 Agent"
_DEFAULT_GREET_MESSAGE = "您好，我对该岗位很感兴趣，希望能和您聊一聊。"


def _greet_message_with_agent_disclosure(message: str | None = None) -> str:
	base_message = (message or "").strip() or _DEFAULT_GREET_MESSAGE
	if _GREET_AGENT_DISCLOSURE in base_message:
		return base_message
	return f"{_GREET_AGENT_DISCLOSURE}，{base_message}"


def _batch_greet_stop_reason(error_msg: str) -> str | None:
	"""Return a batch-level stop reason for errors that affect every candidate."""
	upper_msg = error_msg.upper()
	for code in _BATCH_GREET_STOP_ERROR_CODES:
		if code in upper_msg:
			return code

	lower_msg = error_msg.lower()
	if any(token in lower_msg for token in ("too many", "rate")) or any(
		token in error_msg for token in ("频率", "频繁", "限流", "稍后再试")
	):
		return "RATE_LIMITED"
	if any(token in error_msg for token in ("上限", "今日已达")):
		return "GREET_LIMIT"
	if "failed to fetch" in lower_msg or "浏览器 fetch" in lower_msg:
		return "NETWORK_ERROR"
	if "环境存在异常" in error_msg:
		return "TOKEN_REFRESH_FAILED"
	if any(token in lower_msg for token in ("stoken", "token", "unauthorized")) or any(
		token in error_msg for token in ("登录", "登陆", "未认证")
	):
		return "AUTH_EXPIRED"
	if any(token in lower_msg for token in ("risk", "forbidden")) or any(
		token in error_msg for token in ("异常访问", "风控", "安全验证")
	):
		return "ACCOUNT_RISK"
	return None


def _emit_batch_greet_progress(enabled: bool, *, current: int, total: int, item: dict) -> None:
	if not enabled:
		return
	click.echo(
		json.dumps(
			{
				"type": "boss_auto_greet_progress",
				"status": "greeting",
				"current": current,
				"total": total,
				"title": item.get("title", ""),
				"company": item.get("company", ""),
			},
			ensure_ascii=False,
		),
		err=True,
	)


@click.command("greet")
@click.argument("security_id")
@click.argument("job_id")
@click.option("--message", default="", help="自定义打招呼消息（发送时会表明求职助理 Agent 身份）")
@click.pass_context
@handle_auth_errors("greet")
def greet_cmd(ctx: click.Context, security_id: str, job_id: str, message: str) -> None:
	"""向指定招聘者打招呼"""
	if not require_compliance_allowed(ctx, "greet"):
		return

	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]

	with CacheStore(data_dir / "cache" / "boss_agent.db") as cache:
		if cache.is_greeted(security_id):
			handle_error_output(
				ctx,
				"greet",
				code="ALREADY_GREETED",
				message="已向该招聘者打过招呼",
				hints={"next_actions": ["boss search <query> — 搜索其他职位"]},
			)
			return

		auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
		with get_platform_instance(ctx, auth) as platform:
			greet_message = _greet_message_with_agent_disclosure(message)
			# greet_before hook — allows veto
			hooks = ctx.obj.get("hooks")
			if hooks:
				veto = hooks.greet_before.call(
					{
						"security_id": security_id,
						"job_id": job_id,
						"message": greet_message,
						"source": "greet",
					}
				)
				if veto:
					handle_error_output(
						ctx,
						"greet",
						code="HOOK_BLOCKED",
						message=f"打招呼被钩子阻止: {veto}",
						recoverable=True,
					)
					return

			resp = platform.greet(security_id, job_id, greet_message)
			if not platform.is_success(resp):
				error_code, _ = platform.parse_error(resp)
				handle_error_output(
					ctx,
					"greet",
					code=error_code if error_code != "UNKNOWN" else "NETWORK_ERROR",
					message=resp.get("message") or "打招呼失败",
					recoverable=True,
					recovery_action="重试",
				)
				return

			cache.record_greet(security_id, job_id)

			# greet_after hook
			if hooks:
				hooks.greet_after.call(
					{
						"security_id": security_id,
						"job_id": job_id,
						"success": True,
						"source": "greet",
					}
				)

			data = {
				"security_id": security_id,
				"job_id": job_id,
				"message": "打招呼成功",
			}
			hints = {
				"next_actions": [
					"boss search <query> — 继续搜索其他职位",
					"boss recommend — 获取个性化推荐",
				],
			}
			handle_output(
				ctx,
				"greet",
				data,
				render=lambda d: render_message_panel(d, title="greet"),
				hints=hints,
			)


@click.command("batch-greet")
@click.argument("query")
@click.option("--city", default=None, help="城市名称")
@click.option("--salary", default=None, help="薪资范围")
@click.option("--experience", default=None, help="经验要求（如 3-5年）")
@click.option("--education", default=None, help="学历要求（如 本科）")
@click.option(
	"--industry", default=None, type=click.Choice(BOSS_INDUSTRY_FILTER_CHOICES, case_sensitive=False), help="行业类型"
)
@click.option(
	"--scale",
	default=None,
	type=click.Choice(list(SCALE_CODES.keys()), case_sensitive=False),
	help="公司规模（如 100-499人）",
)
@click.option(
	"--stage",
	default=None,
	type=click.Choice(list(STAGE_CODES.keys()), case_sensitive=False),
	help="融资阶段（如 已上市、A轮）",
)
@click.option(
	"--job-type",
	default=None,
	type=click.Choice(list(JOB_TYPE_CODES.keys()), case_sensitive=False),
	help="职位类型（全职/兼职/实习）",
)
@click.option("--welfare", default=None, help="福利筛选（如 双休、五险一金），逗号分隔时按 AND 匹配")
@click.option("--count", default=10, help="打招呼数量上限（最大 150）")
@click.option("--dry-run", is_flag=True, default=False, help="仅模拟执行，不实际打招呼")
@click.option("--progress-json", is_flag=True, default=False, hidden=True, help="向 stderr 输出自动开聊进度 JSONL")
@click.pass_context
@handle_auth_errors("batch-greet")
def batch_greet_cmd(
	ctx: click.Context,
	query: str,
	city: str | None,
	salary: str | None,
	experience: str | None,
	education: str | None,
	industry: str | None,
	scale: str | None,
	stage: str | None,
	job_type: str | None,
	welfare: str | None,
	count: int,
	dry_run: bool,
	progress_json: bool,
) -> None:
	"""搜索后批量打招呼（上限 150）"""
	if not require_compliance_allowed(ctx, "batch-greet"):
		return

	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]

	config = ctx.obj.get("config", {})
	configured_max = config.get("batch_greet_max", 150)
	try:
		max_count = int(configured_max)
	except (TypeError, ValueError):
		max_count = 150
	max_count = min(max(max_count, 1), 150)
	count = min(max(count, 1), max_count)

	with CacheStore(data_dir / "cache" / "boss_agent.db") as cache:
		auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
		with get_platform_instance(ctx, auth) as platform:
			welfare_conditions = None
			if welfare:
				labels = [w.strip() for w in welfare.split(",") if w.strip()]
				welfare_conditions = [(label, resolve_welfare_keywords(label)) for label in labels]

			criteria = SearchFilterCriteria(
				query=query,
				city=city,
				salary=salary,
				experience=experience,
				education=education,
				industry=industry,
				scale=scale,
				stage=stage,
				job_type=job_type,
			)
			try:
				needs_extended_scan = requires_extended_prefilter_scan(criteria, welfare_conditions)
			except ValueError as exc:
				handle_error_output(ctx, "batch-greet", code="INVALID_PARAM", message=str(exc))
				return
			if needs_extended_scan:
				max_pages = max(5, count)
			else:
				max_pages = count if count > 1 else 1
			try:
				pipeline_result = run_search_pipeline(
					platform,
					cache,
					logger,
					criteria=criteria,
					max_pages=max_pages,
					limit=count,
					welfare_conditions=welfare_conditions,
					skip_greeted=True,
				)
			except SearchPipelinePlatformError as exc:
				recoverable = exc.code == "NETWORK_ERROR"
				handle_error_output(
					ctx,
					"batch-greet",
					code=exc.code,
					message=exc.message or "搜索结果获取失败",
					recoverable=recoverable,
					recovery_action="重试" if recoverable else None,
					details=exc.details,
				)
				return
			candidates = pipeline_result.items

			if dry_run:
				handle_output(
					ctx,
					"batch-greet",
					{
						"dry_run": True,
						"candidates": candidates,
						"count": len(candidates),
					},
					render=lambda d: render_batch_operation_summary(d, title="batch-greet"),
				)
				return

			if not candidates:
				if pipeline_result.stats.jobs_skipped_greeted:
					handle_error_output(
						ctx,
						"batch-greet",
						code="NO_UNGREETED_CANDIDATES",
						message="搜索到职位，但匹配候选都已开聊；请放宽筛选、提高数量，或清理本地已开聊缓存后再试。",
						recoverable=True,
						recovery_action="先用预览确认搜索结果，或调整筛选条件/数量后重试",
						details={
							"pages_scanned": pipeline_result.stats.pages_scanned,
							"jobs_seen": pipeline_result.stats.jobs_seen,
							"jobs_prefiltered": pipeline_result.stats.jobs_prefiltered,
							"jobs_skipped_greeted": pipeline_result.stats.jobs_skipped_greeted,
						},
					)
					return
				handle_error_output(
					ctx,
					"batch-greet",
					code="NO_CANDIDATES",
					message="没有找到可开聊候选人，请放宽筛选条件或先用预览确认搜索结果。",
					recoverable=True,
					recovery_action="调整关键词/城市/薪资/福利筛选后重试",
				)
				return

			results = []
			stopped_reason = None
			stopped_error = None
			greet_message = _greet_message_with_agent_disclosure()

			for idx, item in enumerate(candidates):
				retry_count = 0
				success = False
				_emit_batch_greet_progress(
					progress_json,
					current=idx + 1,
					total=len(candidates),
					item=item,
				)

				while retry_count <= 1:
					try:
						resp = platform.greet(item["security_id"], item["job_id"], greet_message)
						if not platform.is_success(resp):
							error_code, error_detail = platform.parse_error(resp)
							if error_code == "UNKNOWN":
								raise RuntimeError(resp.get("message") or error_detail or "greet failed")
							error_msg = error_code
							if error_detail:
								error_msg = f"{error_code}: {error_detail}"
							raise RuntimeError(error_msg)
						cache.record_greet(item["security_id"], item["job_id"])
						results.append(
							{
								"security_id": item["security_id"],
								"job_id": item["job_id"],
								"title": item["title"],
								"company": item["company"],
								"status": "success",
							}
						)
						success = True
						logger.info(f"打招呼成功: {item['title']} @ {item['company']}")
						break
					except Exception as e:
						error_msg = str(e)
						stop_reason = _batch_greet_stop_reason(error_msg)
						if stop_reason:
							stopped_reason = stop_reason
							stopped_error = error_msg
							break
						if retry_count == 0:
							logger.warning(f"打招呼失败，重试中: {item['title']}")
							retry_count += 1
							time.sleep(random.uniform(1.0, 2.0))
						else:
							results.append(
								{
									"security_id": item["security_id"],
									"job_id": item["job_id"],
									"title": item["title"],
									"company": item["company"],
									"status": "failed",
									"error": error_msg,
								}
							)
							break

				if stopped_reason:
					break

				if success and idx < len(candidates) - 1:
					bg_delay = config.get("batch_greet_delay", [1.0, 10.0])
					time.sleep(random.uniform(bg_delay[0], bg_delay[1]))

			data = {
				"greeted": [r for r in results if r["status"] == "success"],
				"failed": [r for r in results if r["status"] == "failed"],
				"total_greeted": sum(1 for r in results if r["status"] == "success"),
				"total_failed": sum(1 for r in results if r["status"] == "failed"),
			}
			if stopped_reason:
				data["stopped_reason"] = stopped_reason
			if stopped_error:
				data["stopped_error"] = stopped_error

			handle_output(
				ctx,
				"batch-greet",
				data,
				render=lambda d: render_batch_operation_summary(d, title="batch-greet"),
			)
