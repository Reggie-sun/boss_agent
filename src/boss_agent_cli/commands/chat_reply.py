"""boss chat-reply — 候选人自动回复聊天消息。"""

from dataclasses import dataclass
from pathlib import Path

import click

from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import boss_command_for_ctx, handle_auth_errors, handle_error_output, handle_output


@dataclass(slots=True)
class ChatReplyExecutionResult:
	security_id: str
	message: str
	send_resume: bool
	message_sent: bool
	resume_sent: bool
	results: list[str]
	error_message: str = ""
	resume_file_path: str = ""


def execute_chat_reply(
	ctx: click.Context,
	*,
	security_id: str,
	message: str,
	send_resume: bool = False,
	send_attachment_resume: bool = False,
	resume_file_path: str | None = None,
	target_recruiter_name: str = "",
	target_company: str = "",
	target_title: str = "",
	target_gid: str = "",
	target_friend_id: str = "",
	target_uid: str = "",
	target_encrypt_boss_id: str = "",
	target_recruiter_id: str = "",
) -> ChatReplyExecutionResult:
	"""Send a chat reply and optionally the online resume through the existing CDP path."""
	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]

	auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
	with get_platform_instance(ctx, auth) as platform:
		client = platform._client
		if send_attachment_resume:
			if not resume_file_path:
				return ChatReplyExecutionResult(
					security_id=security_id,
					message=message,
					send_resume=send_resume,
					message_sent=False,
					resume_sent=False,
					results=[],
					error_message="缺少附件简历文件路径",
				)
			attachment_path = Path(resume_file_path).expanduser()
			if not attachment_path.exists():
				return ChatReplyExecutionResult(
					security_id=security_id,
					message=message,
					send_resume=send_resume,
					message_sent=False,
					resume_sent=False,
					results=[],
					error_message=f"附件简历不存在: {attachment_path}",
					resume_file_path=str(attachment_path),
				)
			resume_response = client.send_resume_attachment(
				security_id,
				str(attachment_path),
				target_recruiter_name=target_recruiter_name,
				target_company=target_company,
				target_title=target_title,
			)
			if resume_response.get("code") == 0:
				return ChatReplyExecutionResult(
					security_id=security_id,
					message=message,
					send_resume=send_resume,
					message_sent=False,
					resume_sent=True,
					results=[f"附件简历已发送: {attachment_path.name}"],
					resume_file_path=str(attachment_path),
				)
			return ChatReplyExecutionResult(
				security_id=security_id,
				message=message,
				send_resume=send_resume,
				message_sent=False,
				resume_sent=False,
				results=[],
				error_message=str(resume_response.get("message") or "附件简历发送失败"),
				resume_file_path=str(attachment_path),
			)

		message_response = client.send_chat_message(
			security_id,
			message,
			target_recruiter_name=target_recruiter_name,
			target_company=target_company,
			target_title=target_title,
			target_gid=target_gid,
			target_friend_id=target_friend_id,
			target_uid=target_uid,
			target_encrypt_boss_id=target_encrypt_boss_id,
			target_recruiter_id=target_recruiter_id,
		)
		if message_response.get("code") != 0:
			return ChatReplyExecutionResult(
				security_id=security_id,
				message=message,
				send_resume=send_resume,
				message_sent=False,
				resume_sent=False,
				results=[],
				error_message=str(message_response.get("message") or "消息发送失败"),
			)

		results = [f"消息已发送: {message[:50]}..."]
		if not send_resume:
			return ChatReplyExecutionResult(
				security_id=security_id,
				message=message,
				send_resume=send_resume,
				message_sent=True,
				resume_sent=False,
				results=results,
			)

		resume_response = client.send_resume(
			security_id,
			target_recruiter_name=target_recruiter_name,
			target_company=target_company,
			target_title=target_title,
			target_gid=target_gid,
			target_friend_id=target_friend_id,
			target_uid=target_uid,
			target_encrypt_boss_id=target_encrypt_boss_id,
			target_recruiter_id=target_recruiter_id,
		)
		if resume_response.get("code") == 0:
			results.append("在线简历已发送")
			return ChatReplyExecutionResult(
				security_id=security_id,
				message=message,
				send_resume=send_resume,
				message_sent=True,
				resume_sent=True,
				results=results,
			)

		error_message = str(resume_response.get("message") or "简历发送失败")
		results.append(f"简历发送失败: {error_message}")
		return ChatReplyExecutionResult(
			security_id=security_id,
			message=message,
			send_resume=send_resume,
			message_sent=True,
			resume_sent=False,
			results=results,
			error_message=error_message,
		)


@click.command("chat-reply")
@click.argument("security_id")
@click.argument("message")
@click.option("--send-resume", is_flag=True, help="同时发送在线简历")
@click.pass_context
@handle_auth_errors("chat-reply")
def chat_reply_cmd(ctx: click.Context, security_id: str, message: str, send_resume: bool) -> None:
	"""通过 CDP 自动回复聊天消息。

	依赖 CDP Chrome 模式（cdp_url 已配置）。

	示例：
	  boss chat-reply <security_id> "您好，这是我的简历"
	  boss chat-reply <security_id> "您好" --send-resume
	"""
	result = execute_chat_reply(
		ctx,
		security_id=security_id,
		message=message,
		send_resume=send_resume,
	)
	if not result.message_sent:
		handle_error_output(
			ctx,
			"chat-reply",
			code="SEND_FAILED",
			message=f"消息发送失败: {result.error_message or '未知错误'}",
			recoverable=True,
			recovery_action="重试或通过 BOSS App 手动发送",
		)
		return

	handle_output(
		ctx,
		"chat-reply",
		{
			"security_id": security_id,
			"message": message,
			"send_resume": send_resume,
			"message_sent": result.message_sent,
			"resume_sent": result.resume_sent,
			"results": result.results,
		},
		hints={
			"next_actions": [
				boss_command_for_ctx(ctx, f"chatmsg {security_id}"),
				boss_command_for_ctx(ctx, "chat"),
			]
		},
	)
