"""boss chat-reply — 候选人自动回复聊天消息。"""

import click

from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import boss_command_for_ctx, handle_auth_errors, handle_error_output, handle_output


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
	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]

	auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
	with get_platform_instance(ctx, auth) as platform:
		client = platform._client

		# 先确保在聊天页面
		browser = client._get_browser()
		browser._ensure_started()

		# 导航到聊天页
		from boss_agent_cli.api.browser_client import HOME_URL

		chat_url = "https://www.zhipin.com/web/geek/chat"
		try:
			browser._page.goto(chat_url, wait_until="domcontentloaded", timeout=15000)
		except Exception:
			pass  # 即使超时也继续

		# 发送消息
		resp = client.send_chat_message(security_id, message)
		messages = []

		if resp.get("code") == 0:
			messages.append(f"消息已发送: {message[:50]}...")
		else:
			handle_error_output(
				ctx,
				"chat-reply",
				code="SEND_FAILED",
				message=f"消息发送失败: {resp.get('message', '未知错误')}",
				recoverable=True,
				recovery_action="重试或通过 BOSS App 手动发送",
			)
			return

		if send_resume:
			resp2 = client.send_resume(security_id)
			if resp2.get("code") == 0:
				messages.append("在线简历已发送")
			else:
				messages.append(f"简历发送失败: {resp2.get('message', '未知错误')}")

	handle_output(
		ctx,
		"chat-reply",
		{
			"security_id": security_id,
			"message": message,
			"send_resume": send_resume,
			"results": messages,
		},
		hints={
			"next_actions": [
				boss_command_for_ctx(ctx, f"chatmsg {security_id}"),
				boss_command_for_ctx(ctx, "chat"),
			]
		},
	)
