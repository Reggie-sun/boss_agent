from urllib.parse import quote

import click

from boss_agent_cli.cache.store import CacheStore
from boss_agent_cli.display import boss_command_for_ctx, handle_error_output, handle_output, render_simple_list
from boss_agent_cli.platforms import get_platform
from boss_agent_cli.resume.models import ResumeData
from boss_agent_cli.resume.store import ResumeStore


@click.group("shortlist")
def shortlist_group() -> None:
	"""管理职位候选池。"""


_PREPARE_TONES = ("简洁专业", "积极主动", "稳妥确认")


def _resume_store(ctx: click.Context) -> ResumeStore:
	return ResumeStore(ctx.obj["data_dir"] / "resumes")


def _shortlist_not_found(ctx: click.Context, security_id: str, job_id: str) -> None:
	handle_error_output(
		ctx,
		"shortlist",
		code="SHORTLIST_NOT_FOUND",
		message=f"候选池中不存在职位 {security_id}/{job_id}",
		recoverable=True,
		recovery_action=boss_command_for_ctx(ctx, f"shortlist add {security_id} {job_id}"),
	)


def _load_resume_snapshot(resume: ResumeData) -> dict[str, object]:
	job_intention: list[str] = []
	if resume.job_intention is not None:
		job_intention = [
			f"{item.label}: {item.value}".strip(": ")
			for item in resume.job_intention.items
			if item.value
		][:3]

	skills: list[str] = []
	highlights: list[str] = []
	seen_skills: set[str] = set()
	seen_highlights: set[str] = set()
	for module in resume.modules:
		for row in module.rows:
			if row.get("type") == "tags":
				for tag in row.get("tags", []):
					text = str(tag).strip()
					if text and text not in seen_skills:
						seen_skills.add(text)
						skills.append(text)
				continue
			for line in row.get("content", []):
				text = str(line).strip()
				if text and text not in seen_highlights:
					seen_highlights.add(text)
					highlights.append(text)

	return {
		"name": resume.name,
		"title": resume.title,
		"job_intention": job_intention,
		"skills": skills[:8],
		"highlights": highlights[:4],
	}


def _build_manual_entry(ctx: click.Context, item: dict[str, object]) -> dict[str, object]:
	platform_name = ctx.obj.get("platform") or "zhipin"
	platform_cls = get_platform(platform_name)
	base_url = platform_cls.base_url.rstrip("/")
	title = str(item.get("title", "")).strip()
	company = str(item.get("company", "")).strip()
	query = " ".join(part for part in (title, company) if part).strip()
	if platform_name == "zhipin":
		official_entry_url = f"{base_url}/web/geek/job"
		if query:
			official_entry_url = f"{official_entry_url}?query={quote(query)}"
	else:
		official_entry_url = base_url or "https://m.zhaopin.com"
	return {
		"platform": platform_name,
		"official_entry_url": official_entry_url,
		"detail_command": boss_command_for_ctx(
			ctx,
			f"detail {item['security_id']} --job-id {item['job_id']}",
		),
		"lookup_keywords": [part for part in (title, company) if part],
		"lookup_hint": "回到官方页面后，用职位名/公司名检索，并用 security_id/job_id 二次确认是同一岗位。",
	}


def _build_draft_message(
	item: dict[str, object],
	resume_snapshot: dict[str, object] | None,
	*,
	tone: str,
	note: str,
) -> str:
	title = str(item.get("title") or "该岗位").strip()
	company = str(item.get("company") or "贵司").strip()
	resume_name = ""
	skill_text = ""
	highlights_text = ""
	if resume_snapshot:
		resume_name = str(resume_snapshot.get("name") or "").strip()
		skills = [str(skill) for skill in resume_snapshot.get("skills", []) if str(skill).strip()]
		highlights = [str(line) for line in resume_snapshot.get("highlights", []) if str(line).strip()]
		if skills:
			skill_text = f" 我在{ '、'.join(skills[:3]) }方面有相关经验。"
		elif highlights:
			highlights_text = f" 我最近的相关经历包括：{highlights[0]}。"

	if tone == "积极主动":
		message = f"您好，我对贵司的{title}岗位很感兴趣"
	elif tone == "稳妥确认":
		message = f"您好，我在关注贵司的{title}岗位，想先确认岗位要求与团队方向是否匹配"
	else:
		message = f"您好，我关注到贵司的{title}岗位，希望进一步了解"

	if resume_name:
		message += f"，已准备好 {resume_name} 这版简历"
	message += "。"
	message += skill_text or highlights_text
	if note.strip():
		message += f" 补充说明：{note.strip()}"
	return message.strip()


@shortlist_group.command("add")
@click.argument("security_id")
@click.argument("job_id")
@click.option("--title", default="", help="职位名称")
@click.option("--company", default="", help="公司名称")
@click.option("--city", default="", help="城市")
@click.option("--salary", default="", help="薪资")
@click.option("--source", default="manual", help="来源，如 search/recommend/show/manual")
@click.pass_context
def shortlist_add_cmd(ctx: click.Context, security_id: str, job_id: str, title: str, company: str, city: str, salary: str, source: str) -> None:
	with CacheStore(ctx.obj["data_dir"] / "cache" / "boss_agent.db") as cache:
		cache.add_shortlist(
			{
				"security_id": security_id,
				"job_id": job_id,
				"title": title,
				"company": company,
				"city": city,
				"salary": salary,
				"source": source,
			}
		)
	handle_output(
		ctx,
		"shortlist",
		{
			"action": "add",
			"security_id": security_id,
			"job_id": job_id,
			"title": title,
			"company": company,
			"city": city,
			"salary": salary,
			"source": source,
		},
		hints={
			"next_actions": [
				boss_command_for_ctx(ctx, "shortlist list"),
				boss_command_for_ctx(ctx, f"shortlist remove {security_id} {job_id}"),
			]
		},
	)


@shortlist_group.command("list")
@click.pass_context
def shortlist_list_cmd(ctx: click.Context) -> None:
	with CacheStore(ctx.obj["data_dir"] / "cache" / "boss_agent.db") as cache:
		items = cache.list_shortlist()
	handle_output(
		ctx,
		"shortlist",
		items,
		render=lambda data: render_simple_list(
			data,
			"shortlist",
			[
				("title", "title", "bold cyan"),
				("company", "company", "green"),
				("city", "city", "yellow"),
				("salary", "salary", "dim"),
				("source", "source", "magenta"),
			],
		),
		hints={"next_actions": [boss_command_for_ctx(ctx, "detail <security_id> --job-id <job_id>")]},
	)


@shortlist_group.command("remove")
@click.argument("security_id")
@click.argument("job_id")
@click.pass_context
def shortlist_remove_cmd(ctx: click.Context, security_id: str, job_id: str) -> None:
	with CacheStore(ctx.obj["data_dir"] / "cache" / "boss_agent.db") as cache:
		removed = cache.remove_shortlist(security_id, job_id)
	handle_output(
		ctx,
		"shortlist",
		{"action": "remove", "security_id": security_id, "job_id": job_id, "removed": removed},
		hints={"next_actions": [boss_command_for_ctx(ctx, "shortlist list")]},
	)


@shortlist_group.command("prepare")
@click.argument("security_id")
@click.argument("job_id")
@click.option("--resume", "resume_name", default="", help="关联的本地简历名称")
@click.option(
	"--tone",
	default="简洁专业",
	type=click.Choice(_PREPARE_TONES),
	help="草稿语气",
)
@click.option("--note", default="", help="附加备注，会拼接进手动沟通草稿")
@click.pass_context
def shortlist_prepare_cmd(
	ctx: click.Context,
	security_id: str,
	job_id: str,
	resume_name: str,
	tone: str,
	note: str,
) -> None:
	with CacheStore(ctx.obj["data_dir"] / "cache" / "boss_agent.db") as cache:
		item = cache.get_shortlist_item(security_id, job_id)
		if item is None:
			_shortlist_not_found(ctx, security_id, job_id)
			ctx.exit(1)
			return

		resume_snapshot = None
		if resume_name:
			resume = _resume_store(ctx).get(resume_name)
			if resume is None:
				handle_error_output(
					ctx,
					"shortlist",
					code="RESUME_NOT_FOUND",
					message=f"简历 '{resume_name}' 不存在",
				)
				ctx.exit(1)
				return
			cache.link_resume_to_job(resume_name, security_id, job_id, item["title"], item["company"])
			resume_snapshot = _load_resume_snapshot(resume)

		applied = cache.is_applied(security_id, job_id)
		linked_resumes = cache.get_job_resumes(security_id, job_id)

	manual_entry = _build_manual_entry(ctx, item)
	mark_applied_cmd = boss_command_for_ctx(ctx, f"shortlist mark-applied {security_id} {job_id}")
	if resume_name:
		mark_applied_cmd = f"{mark_applied_cmd} --resume {resume_name}"
	data = {
		"action": "prepare",
		"status": "already_applied" if applied else "prepared",
		"security_id": security_id,
		"job_id": job_id,
		"job": item,
		"resume": resume_snapshot,
		"linked_resumes": linked_resumes,
		"applied": applied,
		"manual_entry": manual_entry,
		"draft_message": _build_draft_message(item, resume_snapshot, tone=tone, note=note),
		"steps": [
			manual_entry["detail_command"],
			"打开 official_entry_url 回到平台官网核对职位",
			"确认岗位后由用户手动提交简历或发起沟通",
			f"完成后运行 {mark_applied_cmd} 回写本地状态",
		],
		"note": note,
	}
	next_actions = [str(manual_entry["detail_command"]), mark_applied_cmd]
	if resume_name:
		next_actions.append(boss_command_for_ctx(ctx, f"resume applications {resume_name}"))
	handle_output(
		ctx,
		"shortlist",
		data,
		hints={"next_actions": next_actions},
	)


@shortlist_group.command("mark-applied")
@click.argument("security_id")
@click.argument("job_id")
@click.option("--resume", "resume_name", default="", help="用于更新本地关联状态的简历名称")
@click.option("--notes", default="已在官方页面手动投递", help="本地状态备注")
@click.pass_context
def shortlist_mark_applied_cmd(
	ctx: click.Context,
	security_id: str,
	job_id: str,
	resume_name: str,
	notes: str,
) -> None:
	with CacheStore(ctx.obj["data_dir"] / "cache" / "boss_agent.db") as cache:
		item = cache.get_shortlist_item(security_id, job_id)
		if item is None:
			_shortlist_not_found(ctx, security_id, job_id)
			ctx.exit(1)
			return

		if resume_name and not _resume_store(ctx).exists(resume_name):
			handle_error_output(
				ctx,
				"shortlist",
				code="RESUME_NOT_FOUND",
				message=f"简历 '{resume_name}' 不存在",
			)
			ctx.exit(1)
			return

		cache.record_apply(security_id, job_id)
		updated_resumes: list[str] = []
		if resume_name:
			existing = {item["resume_name"] for item in cache.get_job_resumes(security_id, job_id)}
			if resume_name not in existing:
				cache.link_resume_to_job(resume_name, security_id, job_id, item["title"], item["company"])
			cache.update_job_link_status(resume_name, security_id, job_id, "manually_applied", notes)
			updated_resumes.append(resume_name)
		else:
			for linked in cache.get_job_resumes(security_id, job_id):
				cache.update_job_link_status(linked["resume_name"], security_id, job_id, "manually_applied", notes)
				updated_resumes.append(linked["resume_name"])

	data = {
		"action": "mark-applied",
		"security_id": security_id,
		"job_id": job_id,
		"status": "manually_applied",
		"notes": notes,
		"updated_resumes": updated_resumes,
	}
	next_actions = [boss_command_for_ctx(ctx, "shortlist list")]
	for linked_resume in updated_resumes[:1]:
		next_actions.append(boss_command_for_ctx(ctx, f"resume applications {linked_resume}"))
	handle_output(
		ctx,
		"shortlist",
		data,
		hints={"next_actions": next_actions},
	)
