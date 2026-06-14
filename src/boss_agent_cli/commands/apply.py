import click

from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.cache.store import CacheStore
from boss_agent_cli.compliance import require_compliance_allowed
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import boss_command_for_ctx, handle_auth_errors, handle_error_output, handle_output, render_message_panel
from boss_agent_cli.resume.store import ResumeStore


def _build_apply_message(resume_name: str, job_title: str, company: str, custom_message: str) -> str:
	"""构建投递附带的打招呼消息。"""
	if custom_message.strip():
		return custom_message.strip()
	if resume_name:
		parts = [f"您好，我对贵司的{job_title}岗位很感兴趣"]
		if company:
			parts[0] = f"您好，我对{company}的{job_title}岗位很感兴趣"
		parts.append(f"，已准备好 {resume_name} 这版简历，希望能和您聊一聊。")
		return "".join(parts)
	return ""


@click.command("apply")
@click.argument("security_id")
@click.argument("job_id")
@click.option("--lid", default="", help="列表项 ID（可选）")
@click.option("--resume", "resume_name", default="", help="关联的本地简历名称（自动附带投递）")
@click.option("--message", default="", help="自定义打招呼消息（不填则根据简历自动生成）")
@click.option("--title", default="", help="职位名称（用于自动生成消息）")
@click.option("--company", default="", help="公司名称（用于自动生成消息）")
@click.pass_context
@handle_auth_errors("apply")
def apply_cmd(
	ctx: click.Context,
	security_id: str,
	job_id: str,
	lid: str,
	resume_name: str,
	message: str,
	title: str,
	company: str,
) -> None:
	"""全自动投递：发送立即沟通请求并自动附带在线简历。

	配置 boss_apply_auto_enabled=true（默认开启）时，
	即使 low_risk_mode=true 也会放行 apply 命令。

	示例：
	  boss apply <sid> <jid>                          # 纯打招呼
	  boss apply <sid> <jid> --resume default          # 自动附带简历投递
	  boss apply <sid> <jid> --resume default --message "自定义消息"
	"""
	if not require_compliance_allowed(ctx, "apply"):
		return

	data_dir = ctx.obj["data_dir"]
	logger = ctx.obj["logger"]

	with CacheStore(data_dir / "cache" / "boss_agent.db") as cache:
		if cache.is_applied(security_id, job_id):
			handle_error_output(
				ctx,
				"apply",
				code="ALREADY_APPLIED",
				message="已对该职位发起过投递/立即沟通",
				hints={
					"next_actions": [
						boss_command_for_ctx(ctx, "me --section deliver"),
						boss_command_for_ctx(ctx, "chat"),
					]
				},
			)
			return

		# 加载并关联本地简历
		resume_snapshot: dict | None = None
		if resume_name:
			resume_store = ResumeStore(data_dir / "resumes")
			resume = resume_store.get(resume_name)
			if resume is None:
				handle_error_output(
					ctx,
					"apply",
					code="RESUME_NOT_FOUND",
					message=f"简历 '{resume_name}' 不存在",
					recoverable=True,
					recovery_action=f"boss resume init --name {resume_name}",
				)
				return
			# 关联简历到职位
			cache.link_resume_to_job(resume_name, security_id, job_id, title, company)
			# 构建简历快照用于展示
			resume_snapshot = {
				"name": resume.name,
				"title": resume.title,
			}

		# 构建打招呼消息
		greeting = _build_apply_message(resume_name, title, company, message)

		auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
		with get_platform_instance(ctx, auth) as platform:
			resp = platform.apply(security_id, job_id, lid=lid, message=greeting)
			if not platform.is_success(resp):
				error_code, _ = platform.parse_error(resp)
				handle_error_output(
					ctx,
					"apply",
					code=error_code if error_code != "UNKNOWN" else "NETWORK_ERROR",
					message=resp.get("message") or "投递/立即沟通提交失败",
					recoverable=True,
					recovery_action="重试",
				)
				return
			cache.record_apply(security_id, job_id, resume_name=resume_name)

	# 构建输出
	output_data: dict = {
		"security_id": security_id,
		"job_id": job_id,
		"lid": lid,
		"mode": "auto_apply" if resume_name else "immediate_chat_apply",
		"message": "投递/立即沟通已提交",
	}
	if resume_snapshot:
		output_data["resume"] = resume_snapshot
	if greeting:
		output_data["greeting"] = greeting

	next_actions = [
		boss_command_for_ctx(ctx, "me --section deliver"),
		boss_command_for_ctx(ctx, "chat"),
	]
	if resume_name:
		next_actions.insert(0, boss_command_for_ctx(ctx, f"resume applications {resume_name}"))

	handle_output(
		ctx,
		"apply",
		output_data,
		render=lambda d: render_message_panel(d, title="apply"),
		hints={"next_actions": next_actions},
	)
