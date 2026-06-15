"""Boss Agent reply workflow commands with legacy rag compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click

from boss_agent_cli.ai.config import AIConfigStore, PROVIDER_BASE_URLS
from boss_agent_cli.ai.service import AIService
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.commands.chat_reply import execute_chat_reply
from boss_agent_cli.display import handle_error_output, handle_output
from boss_agent_cli.display import handle_auth_errors
from boss_agent_cli.rag_reply.adapters.agent_answer import AgentAnswerAdapter
from boss_agent_cli.rag_reply.adapters.ai_fallback import AIFallbackAdapter
from boss_agent_cli.rag_reply.adapters.boss_automation import (
	BossAutomationAdapter,
	BossAutomationError,
	RecentConversationTarget,
)
from boss_agent_cli.rag_reply.adapters.manual_import import import_messages
from boss_agent_cli.rag_reply.adapters.mock_envelope import load_and_ingest_mock_envelope
from boss_agent_cli.rag_reply.adapters.rag_http import RagHttpAdapter
from boss_agent_cli.rag_reply.langchain_memory import build_thread_payload
from boss_agent_cli.rag_reply.models import AuditLogRecord, ConversationRecord, MessageRecord, new_id
from boss_agent_cli.rag_reply.review import draft_to_payload
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


@dataclass(slots=True)
class ResumeSendResult:
	attempted: bool
	status: str
	message_sent: bool
	resume_sent: bool
	messages: list[str]
	error_message: str = ""
	security_id: str = ""


def _workflow_name(ctx: click.Context) -> str:
	"""Return the active workflow surface name."""
	parent = ctx.parent.info_name if ctx.parent else ""
	return "agent" if parent == "agent" else "rag"


def _workflow_command(ctx: click.Context, action: str) -> str:
	"""Return the envelope command name for the current workflow surface."""
	return f"{_workflow_name(ctx)}-{action}"


def _resolve_store(ctx: click.Context) -> RagReplyStore:
	"""Return the workflow store initialized at the configured location."""
	data_dir = Path(ctx.obj["data_dir"])
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	configured = config.get("boss_rag_db_path")
	db_path = Path(str(configured)).expanduser() if configured else data_dir / "boss-rag.sqlite3"
	store = RagReplyStore(db_path)
	store.initialize()
	return store


def _build_shared_ai_service(ctx: click.Context) -> AIService | None:
	"""Construct the optional shared AI service used by local agent helpers."""
	data_dir = Path(ctx.obj["data_dir"])
	store = AIConfigStore(data_dir)
	if not store.is_configured():
		return None
	api_key = store.get_api_key()
	base_url = store.get_base_url()
	if not api_key or not base_url:
		return None
	config = store.load_config()
	return AIService(
		base_url=base_url,
		api_key=api_key,
		model=config["ai_model"],
		temperature=config.get("ai_temperature", 0.7),
		max_tokens=config.get("ai_max_tokens", 4096),
	)


def _build_ai_fallback_adapter(ctx: click.Context) -> AIFallbackAdapter | None:
	"""Construct the optional local AI fallback adapter."""
	ai_service = _build_shared_ai_service(ctx)
	if ai_service is None:
		return None
	return AIFallbackAdapter(ai_service=ai_service)


def _build_agent_answer_adapter(ctx: click.Context) -> AgentAnswerAdapter | None:
	"""Construct the optional agent-side answer composer."""
	ai_service = _build_shared_ai_service(ctx)
	return AgentAnswerAdapter(ai_service=ai_service)


def _build_service(ctx: click.Context) -> BossRagReplyService:
	"""Construct the Boss RAG workflow service."""
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	rag_adapter = RagHttpAdapter(
		base_url=config.get("boss_rag_rag_base_url"),
		timeout_seconds=int(config.get("boss_rag_rag_timeout_seconds", 20)),
		api_key=config.get("boss_rag_rag_api_key"),
		auth_mode=str(config.get("boss_rag_rag_auth_mode", "none")),
	)
	return BossRagReplyService(
		store=_resolve_store(ctx),
		rag_adapter=rag_adapter,
		fallback_adapter=_build_ai_fallback_adapter(ctx),
		agent_answer_adapter=_build_agent_answer_adapter(ctx),
	)


def _build_boss_adapter(ctx: click.Context) -> BossAutomationAdapter:
	"""Construct the read-only Boss automation adapter."""
	data_dir = Path(ctx.obj["data_dir"])
	logger = ctx.obj["logger"]
	auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
	platform = get_platform_instance(ctx, auth)
	return BossAutomationAdapter(platform=platform, store=_resolve_store(ctx))


def _ensure_conversation(
	store: RagReplyStore,
	*,
	conversation_id: str,
	job_id: str | None = None,
	recruiter_id: str | None = None,
	security_id: str | None = None,
) -> ConversationRecord:
	"""Create or refresh a frontend-driven conversation record."""
	existing = store.get_conversation(conversation_id)
	state = dict(existing.state) if existing and isinstance(existing.state, dict) else {"origin": "interview-simulator"}
	if security_id:
		state["security_id"] = security_id
	return ConversationRecord(
		conversation_id=conversation_id,
		source="frontend_bridge",
		job_id=job_id or (existing.job_id if existing else None),
		recruiter_id=recruiter_id or (existing.recruiter_id if existing else None),
		channel=existing.channel if existing else "boss",
		last_message_at=existing.last_message_at if existing else None,
		state=state,
	)


def _persist_frontend_question(
	store: RagReplyStore,
	*,
	conversation_id: str,
	question: str,
	job_id: str | None = None,
	recruiter_id: str | None = None,
	security_id: str | None = None,
) -> MessageRecord:
	"""Persist one frontend prompt into the shared Boss RAG store."""
	conversation = _ensure_conversation(
		store,
		conversation_id=conversation_id,
		job_id=job_id,
		recruiter_id=recruiter_id,
		security_id=security_id,
	)
	message = MessageRecord(
		message_id=new_id("frontmsg"),
		conversation_id=conversation_id,
		message_text=question,
		direction="inbound",
		job_id=conversation.job_id,
		recruiter_id=conversation.recruiter_id,
		source="frontend_prompt",
		raw={"origin": "interview-simulator"},
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id=conversation.conversation_id,
			source=conversation.source,
			job_id=conversation.job_id,
			recruiter_id=conversation.recruiter_id,
			channel=conversation.channel,
			last_message_at=message.created_at,
			state=conversation.state,
		)
	)
	store.save_message(message)
	return message


def _resolve_security_id(
	store: RagReplyStore,
	*,
	conversation_id: str,
	security_id: str | None = None,
	job_id: str | None = None,
) -> str:
	"""Resolve the target security_id from explicit input, conversation state, or stored job."""
	explicit = str(security_id or "").strip()
	if explicit:
		return explicit
	conversation = store.get_conversation(conversation_id)
	if conversation and isinstance(conversation.state, dict):
		from_state = str(conversation.state.get("security_id") or "").strip()
		if from_state:
			return from_state
	resolved_job_id = str(job_id or (conversation.job_id if conversation else "") or "").strip()
	if not resolved_job_id:
		return ""
	job = store.get_job(resolved_job_id)
	return str(job.security_id if job else "").strip()


def _send_resume_reply(ctx: click.Context, *, security_id: str, message: str) -> ResumeSendResult:
	"""Send the chat reply and online resume via the existing CDP chat-reply path."""
	result = execute_chat_reply(
		ctx,
		security_id=security_id,
		message=message,
		send_resume=True,
	)
	if not result.message_sent:
		return ResumeSendResult(
			attempted=True,
			status="message_failed",
			message_sent=False,
			resume_sent=False,
			messages=result.results,
			error_message=result.error_message,
			security_id=result.security_id,
		)
	return ResumeSendResult(
		attempted=True,
		status="sent" if result.resume_sent else "resume_failed",
		message_sent=True,
		resume_sent=result.resume_sent,
		messages=result.results,
		error_message=result.error_message,
		security_id=result.security_id,
	)


def _maybe_auto_send_resume(
	ctx: click.Context,
	*,
	store: RagReplyStore,
	draft: object,
	conversation_id: str,
	job_id: str | None = None,
	security_id: str | None = None,
	auto_send_resume: bool = False,
) -> dict[str, object] | None:
	"""Auto-send the online resume when explicitly enabled and intent matches."""
	if not auto_send_resume:
		return None
	intent = str(getattr(draft, "intent", "") or "")
	if intent != "resume_share_request":
		return None
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	if not bool(config.get("boss_rag_send_enabled", False)):
		return {
			"attempted": False,
			"status": "disabled",
			"message": "未开启 boss_rag_send_enabled，已跳过自动发送简历。",
		}
	resolved_security_id = _resolve_security_id(
		store,
		conversation_id=conversation_id,
		security_id=security_id,
		job_id=job_id,
	)
	if not resolved_security_id:
		return {
			"attempted": False,
			"status": "missing_security_id",
			"message": "缺少 security_id，无法自动发送在线简历。",
		}
	draft_text = str(getattr(draft, "draft_text", "") or "").strip()
	if not draft_text:
		return {
			"attempted": False,
			"status": "missing_message",
			"message": "草稿为空，已跳过自动发送简历。",
		}
	result = _send_resume_reply(ctx, security_id=resolved_security_id, message=draft_text)
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="resume_auto_send",
			entity_type="conversation",
			entity_id=conversation_id,
			payload={
				"security_id": result.security_id,
				"status": result.status,
				"message_sent": result.message_sent,
				"resume_sent": result.resume_sent,
				"error_message": result.error_message,
			},
		)
	)
	return {
		"attempted": result.attempted,
		"status": result.status,
		"message_sent": result.message_sent,
		"resume_sent": result.resume_sent,
		"messages": result.messages,
		"error_message": result.error_message,
		"security_id": result.security_id,
	}


def _require_message_read_enabled(ctx: click.Context) -> bool:
	"""Return False with a structured error when Boss message reading is disabled."""
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	if bool(config.get("boss_rag_allow_message_read", False)):
		return True
	handle_error_output(
		ctx,
		_workflow_command(ctx, "sync-messages"),
		code="RAG_READ_NOT_ENABLED",
		message="Boss message reading is disabled by default. Enable boss_rag_allow_message_read explicitly before syncing messages.",
		recoverable=True,
		recovery_action="Set boss_rag_allow_message_read=true in config.json and retry.",
		hints={
			"manual_action_required": True,
			"default_safe_mode": True,
			"next_actions": [
				"Use boss agent import-messages for manual fallback.",
				"Use boss agent ingest-mock for structured mock envelope testing.",
			],
		},
	)
	return False


def _serialize_target(target: RecentConversationTarget) -> dict[str, object]:
	return {
		"conversation_id": target.conversation_id,
		"security_id": target.security_id,
		"job_id": target.job_id,
		"recruiter_name": target.recruiter_name,
		"company": target.company,
		"title": target.title,
		"last_message": target.last_message,
		"last_message_at": target.last_message_at,
		"unread_count": target.unread_count,
	}


def _cached_recent_targets(store: RagReplyStore, *, limit: int) -> list[dict[str, object]]:
	targets: list[dict[str, object]] = []
	for conversation in store.list_conversations():
		state = conversation.state if isinstance(conversation.state, dict) else {}
		security_id = str(state.get("security_id") or "").strip()
		if not security_id:
			continue
		recruiter = store.get_recruiter(str(conversation.recruiter_id or "")) if conversation.recruiter_id else None
		targets.append(
			{
				"conversation_id": conversation.conversation_id,
				"security_id": security_id,
				"job_id": str(conversation.job_id or ""),
				"recruiter_name": recruiter.display_name if recruiter else "",
				"company": str(state.get("company") or (recruiter.company if recruiter else "") or ""),
				"title": str(state.get("title") or ""),
				"last_message": str(state.get("last_msg") or ""),
				"last_message_at": conversation.last_message_at,
				"unread_count": int(state.get("unread_count") or 0),
			}
		)
		if len(targets) >= limit:
			break
	return targets


def _not_implemented(ctx: click.Context, command: str) -> None:
	"""Emit a consistent placeholder response for unimplemented subcommands."""
	handle_error_output(
		ctx,
		_workflow_command(ctx, command),
		code="NOT_IMPLEMENTED",
		message="This Boss Agent workflow command is planned but not implemented yet.",
		recoverable=False,
		recovery_action="Continue with the next implementation task in docs/superpowers/plans/2026-06-10-boss-rag-reply-agent-implementation-plan.md.",
	)


@click.group("rag")
@click.pass_context
def rag_group(ctx: click.Context) -> None:
	"""Boss Agent workflow commands. Legacy alias: rag."""
	ctx.ensure_object(dict)


@rag_group.command("init")
@click.pass_context
def rag_init_cmd(ctx: click.Context) -> None:
	store = _resolve_store(ctx)
	handle_output(
		ctx,
		_workflow_command(ctx, "init"),
		{"status": "initialized", "db_path": str(store.db_path)},
		render=lambda data: click.echo(f"Initialized Boss Agent store at {data['db_path']}.", err=True),
	)


@rag_group.command("import-messages")
@click.option("--file", "file_path", required=False)
@click.option("--format", "fmt", type=click.Choice(["json", "md", "csv"]), required=False)
@click.pass_context
def rag_import_messages_cmd(ctx: click.Context, file_path: str | None, fmt: str | None) -> None:
	if not file_path or not fmt:
		_not_implemented(ctx, "import-messages")
		return
	store = _resolve_store(ctx)
	result = import_messages(Path(file_path), fmt, store)
	handle_output(
		ctx,
		_workflow_command(ctx, "import-messages"),
		{
			"import_batch_id": result.import_batch_id,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
			"count": result.count,
		},
		render=lambda data: click.echo(f"Imported {data['count']} messages.", err=True),
	)


@rag_group.command("ingest-mock")
@click.option("--file", "file_path", required=False)
@click.pass_context
def rag_ingest_mock_cmd(ctx: click.Context, file_path: str | None) -> None:
	if not file_path:
		_not_implemented(ctx, "ingest-mock")
		return
	store = _resolve_store(ctx)
	result = load_and_ingest_mock_envelope(Path(file_path), store)
	handle_output(
		ctx,
		_workflow_command(ctx, "ingest-mock"),
		{
			"import_batch_id": result.import_batch_id,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
			"count": result.count,
		},
		render=lambda data: click.echo(f"Ingested {data['count']} mock messages.", err=True),
	)


@rag_group.command("sync-jobs")
@click.option("--query", required=False)
@click.pass_context
@handle_auth_errors("rag-sync-jobs")
def rag_sync_jobs_cmd(ctx: click.Context, query: str | None) -> None:
	try:
		with _build_boss_adapter(ctx) as adapter:
			result = adapter.sync_jobs(query=query)
	except BossAutomationError as exc:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "sync-jobs"),
			code=exc.code,
			message=exc.message,
			recoverable=exc.recoverable,
			recovery_action=exc.recovery_action,
			hints=exc.hints,
		)
		return
	handle_output(
		ctx,
		_workflow_command(ctx, "sync-jobs"),
		{
			"sync_batch_id": result.sync_batch_id,
			"source": result.source,
			"job_ids": result.synced_job_ids,
			"count": result.count,
		},
		render=lambda data: click.echo(f"Synced {data['count']} job(s).", err=True),
	)


@rag_group.command("sync-messages")
@click.option("--conversation-id", default=None)
@click.pass_context
@handle_auth_errors("rag-sync-messages")
def rag_sync_messages_cmd(ctx: click.Context, conversation_id: str | None) -> None:
	if not _require_message_read_enabled(ctx):
		return
	try:
		with _build_boss_adapter(ctx) as adapter:
			result = adapter.sync_messages(conversation_id=conversation_id)
	except BossAutomationError as exc:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "sync-messages"),
			code=exc.code,
			message=exc.message,
			recoverable=exc.recoverable,
			recovery_action=exc.recovery_action,
			hints=exc.hints,
		)
		return
	handle_output(
		ctx,
		_workflow_command(ctx, "sync-messages"),
		{
			"import_batch_id": result.import_batch_id,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
			"count": result.count,
		},
		render=lambda data: click.echo(f"Synced {data['count']} recruiter message(s).", err=True),
	)


@rag_group.command("targets")
@click.option("--limit", default=5, type=int, show_default=True, help="返回最近可发送的 Boss 对话目标数量")
@click.pass_context
@handle_auth_errors("rag-targets")
def rag_targets_cmd(ctx: click.Context, limit: int) -> None:
	store = _resolve_store(ctx)
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	safe_limit = max(1, min(limit, 20))
	live_read_enabled = bool(config.get("boss_rag_allow_message_read", False))
	cached_targets = _cached_recent_targets(store, limit=safe_limit)
	refreshed = False
	refresh_error = ""
	source = "cache"
	targets = cached_targets

	if live_read_enabled:
		try:
			with _build_boss_adapter(ctx) as adapter:
				targets = [_serialize_target(target) for target in adapter.list_recent_targets(limit=safe_limit)]
			refreshed = True
			source = "boss_live"
		except BossAutomationError as exc:
			refresh_error = exc.message
			if not cached_targets:
				handle_error_output(
					ctx,
					_workflow_command(ctx, "targets"),
					code=exc.code,
					message=exc.message,
					recoverable=exc.recoverable,
					recovery_action=exc.recovery_action,
					hints=exc.hints,
				)
				return

	handle_output(
		ctx,
		_workflow_command(ctx, "targets"),
		{
			"targets": targets,
			"count": len(targets),
			"limit": safe_limit,
			"source": source,
			"live_read_enabled": live_read_enabled,
			"refreshed": refreshed,
			"refresh_error": refresh_error,
		},
		render=lambda data: click.echo(f"Loaded {data['count']} Boss target(s).", err=True),
		hints={
			"next_actions": [
				"agent ask --conversation-id <session> --question \"麻烦发一下简历\" --security-id <security_id> --auto-send-resume",
				"agent send <draft_id> --security-id <security_id> --send-resume",
			]
		},
	)


@rag_group.command("draft")
@click.option("--conversation-id", default=None)
@click.option("--message-id", default=None)
@click.pass_context
def rag_draft_cmd(ctx: click.Context, conversation_id: str | None, message_id: str | None) -> None:
	service = _build_service(ctx)
	store = service.store
	if message_id:
		drafts = [service.create_draft_for_message(message_id)]
	elif conversation_id:
		drafts = [service.create_draft_for_message(message.message_id) for message in store.list_messages(conversation_id)]
	else:
		drafts = service.create_drafts_for_all_messages()
	handle_output(
		ctx,
		_workflow_command(ctx, "draft"),
		[draft_to_payload(draft) for draft in drafts],
		render=lambda data: click.echo(f"Created {len(data)} draft(s).", err=True),
	)


@rag_group.command("review")
@click.option("--draft-id", default=None)
@click.pass_context
def rag_review_cmd(ctx: click.Context, draft_id: str | None) -> None:
	store = _resolve_store(ctx)
	if draft_id:
		draft = store.get_draft(draft_id)
		if draft is None:
			handle_error_output(
				ctx,
				_workflow_command(ctx, "review"),
				code="DRAFT_NOT_FOUND",
				message=f"Unknown draft_id={draft_id}",
				recoverable=False,
			)
			return
		payload: object = draft_to_payload(draft)
	else:
		payload = [draft_to_payload(draft) for draft in store.list_drafts()]
	handle_output(
		ctx,
		_workflow_command(ctx, "review"),
		payload,
		render=lambda data: click.echo("Draft review ready.", err=True),
	)


@rag_group.command("ask")
@click.option("--conversation-id", required=True)
@click.option("--question", required=True)
@click.option("--job-id", default=None)
@click.option("--recruiter-id", default=None)
@click.option("--security-id", default=None)
@click.option("--auto-send-resume", is_flag=True, default=False)
@click.pass_context
def rag_ask_cmd(
	ctx: click.Context,
	conversation_id: str,
	question: str,
	job_id: str | None,
	recruiter_id: str | None,
	security_id: str | None,
	auto_send_resume: bool,
) -> None:
	service = _build_service(ctx)
	store = service.store
	message = _persist_frontend_question(
		store,
		conversation_id=conversation_id,
		question=question.strip(),
		job_id=job_id,
		recruiter_id=recruiter_id,
		security_id=security_id,
	)
	draft = service.create_draft_for_message(message.message_id)
	evidence = draft.evidence if isinstance(draft.evidence, dict) else {}
	delivery = _maybe_auto_send_resume(
		ctx,
		store=store,
		draft=draft,
		conversation_id=conversation_id,
		job_id=job_id,
		security_id=security_id,
		auto_send_resume=auto_send_resume,
	)
	handle_output(
		ctx,
		_workflow_command(ctx, "ask"),
		{
			"conversation_id": conversation_id,
			"message_id": message.message_id,
			"answer": draft.draft_text,
			"answer_source": str(evidence.get("source") or ""),
			"citations": evidence.get("citations") if isinstance(evidence.get("citations"), list) else [],
			"reasoning_summary": evidence.get("reasoning_summary")
			if isinstance(evidence.get("reasoning_summary"), dict)
			else None,
			"delivery": delivery,
			"error_message": str(evidence.get("error_message") or evidence.get("rag_error_message") or ""),
			"audit_status": draft.audit_status,
			"draft": draft_to_payload(draft),
			"thread": build_thread_payload(store=store, conversation_id=conversation_id),
		},
		render=lambda data: click.echo(
			f"Created draft for {data['conversation_id']} from {data['message_id']}.",
			err=True,
		),
	)


@rag_group.command("thread")
@click.option("--conversation-id", required=True)
@click.pass_context
def rag_thread_cmd(ctx: click.Context, conversation_id: str) -> None:
	store = _resolve_store(ctx)
	handle_output(
		ctx,
		_workflow_command(ctx, "thread"),
		{
			"conversation_id": conversation_id,
			"messages": build_thread_payload(store=store, conversation_id=conversation_id),
		},
		render=lambda data: click.echo(
			f"Loaded {len(data['messages'])} thread message(s) for {data['conversation_id']}.",
			err=True,
		),
	)


@rag_group.command("approve")
@click.argument("draft_id", required=True)
@click.option("--copy", is_flag=True, default=False)
@click.pass_context
def rag_approve_cmd(ctx: click.Context, draft_id: str, copy: bool) -> None:
	service = _build_service(ctx)
	result = service.approve_draft(draft_id, copy_to_clipboard=copy)
	handle_output(
		ctx,
		_workflow_command(ctx, "approve"),
		{
			"draft": draft_to_payload(result.draft),
			"approval_event": {
				"event_id": result.event.event_id,
				"action": result.event.action,
				"copied_to_clipboard": result.copied_to_clipboard,
			},
		},
		render=lambda data: click.echo("Draft approved.", err=True),
	)


@rag_group.command("send")
@click.argument("draft_id", required=True)
@click.option("--security-id", default=None)
@click.option("--send-resume", is_flag=True, default=False)
@click.pass_context
def rag_send_cmd(
	ctx: click.Context,
	draft_id: str,
	security_id: str | None,
	send_resume: bool,
) -> None:
	store = _resolve_store(ctx)
	draft = store.get_draft(draft_id)
	if draft is None:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "send"),
			code="DRAFT_NOT_FOUND",
			message=f"Unknown draft_id={draft_id}",
			recoverable=False,
		)
		return
	message = str(draft.draft_text or "").strip()
	if not message:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "send"),
			code="INVALID_PARAM",
			message=f"Draft {draft_id} has empty draft_text.",
			recoverable=False,
		)
		return
	resolved_security_id = _resolve_security_id(
		store,
		conversation_id=draft.conversation_id,
		security_id=security_id,
	)
	if not resolved_security_id:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "send"),
			code="INVALID_PARAM",
			message="Missing security_id for draft delivery. Pass --security-id or store it in the conversation state first.",
			recoverable=True,
			recovery_action="Provide --security-id, or write security_id into the conversation before retrying.",
		)
		return
	result = execute_chat_reply(
		ctx,
		security_id=resolved_security_id,
		message=message,
		send_resume=send_resume,
	)
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="draft_send",
			entity_type="draft",
			entity_id=draft_id,
			payload={
				"conversation_id": draft.conversation_id,
				"security_id": resolved_security_id,
				"send_resume": send_resume,
				"message_sent": result.message_sent,
				"resume_sent": result.resume_sent,
				"error_message": result.error_message,
			},
		)
	)
	if not result.message_sent:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "send"),
			code="SEND_FAILED",
			message=f"消息发送失败: {result.error_message or '未知错误'}",
			recoverable=True,
			recovery_action="重试或通过 BOSS App 手动发送。",
		)
		return
	handle_output(
		ctx,
		_workflow_command(ctx, "send"),
		{
			"draft": draft_to_payload(draft),
			"security_id": resolved_security_id,
			"message_sent": result.message_sent,
			"resume_sent": result.resume_sent,
			"send_resume": send_resume,
			"results": result.results,
			"error_message": result.error_message,
		},
		render=lambda data: click.echo(
			f"Sent draft {data['draft']['draft_id']} to {data['security_id']}.",
			err=True,
		),
	)


@rag_group.command("audit")
@click.option("--draft-id", default=None)
@click.pass_context
def rag_audit_cmd(ctx: click.Context, draft_id: str | None) -> None:
	store = _resolve_store(ctx)
	payload = [
		{
			"log_id": entry.log_id,
			"event_type": entry.event_type,
			"entity_type": entry.entity_type,
			"entity_id": entry.entity_id,
			"payload": entry.payload,
			"created_at": entry.created_at,
		}
		for entry in store.list_audit_logs(draft_id)
	]
	handle_output(
		ctx,
		_workflow_command(ctx, "audit"),
		payload,
		render=lambda data: click.echo(f"Found {len(data)} audit log(s).", err=True),
	)
