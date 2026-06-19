"""Boss Agent reply workflow commands with legacy rag compatibility."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import click

from boss_agent_cli.api.browser_client import ensure_candidate_chat_page_via_cdp
from boss_agent_cli.ai.config import AIConfigStore
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
from boss_agent_cli.rag_reply.watcher import BossPassiveWatcher, WatcherRunResult
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


@dataclass(slots=True)
class ResumeSendResult:
	attempted: bool
	status: str
	message_sent: bool
	resume_sent: bool
	messages: list[str]
	error_message: str = ""
	security_id: str = ""


class _CliWatcherDelivery:
	"""Send watcher replies through the existing chat-reply delivery path."""

	def __init__(self, ctx: click.Context) -> None:
		self.ctx = ctx

	def send(
		self,
		*,
		security_id: str,
		message: str,
		send_attachment_resume: bool = False,
		resume_file: str = "",
		target: dict[str, str] | None = None,
	) -> dict[str, object]:
		target = target or {}
		result = execute_chat_reply(
			self.ctx,
			security_id=security_id,
			message=message,
			send_resume=False,
			send_attachment_resume=send_attachment_resume,
			resume_file_path=resume_file if send_attachment_resume else None,
			target_recruiter_name=str(target.get("recruiter_name") or ""),
			target_company=str(target.get("company") or ""),
			target_title=str(target.get("title") or ""),
			target_gid=str(target.get("gid") or ""),
			target_friend_id=str(target.get("friend_id") or ""),
			target_uid=str(target.get("uid") or ""),
			target_encrypt_boss_id=str(target.get("encrypt_boss_id") or ""),
			target_recruiter_id=str(target.get("recruiter_id") or ""),
		)
		ok = result.message_sent or (send_attachment_resume and result.resume_sent)
		return {
			"ok": ok,
			"status": "sent" if ok else "send_failed",
			"message_sent": result.message_sent,
			"resume_sent": result.resume_sent,
			"error_message": result.error_message,
			"results": result.results,
			"resume_file": result.resume_file_path,
			"requested_resume_file": resume_file if send_attachment_resume else "",
		}


class _CliWatcherMessageSyncer:
	"""Sync recent Boss messages and pipeline candidates before a watcher cycle."""

	def __init__(self, ctx: click.Context) -> None:
		self.ctx = ctx

	def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
		config = self.ctx.obj.get("config", {}) if self.ctx and self.ctx.obj else {}
		if not bool(config.get("boss_rag_allow_message_read", False)):
			return {
				"ok": False,
				"status": "read_disabled",
				"error_code": "RAG_READ_NOT_ENABLED",
				"error_message": "Boss message reading is disabled by default.",
				"recoverable": True,
				"recovery_action": "Set boss_rag_allow_message_read=true in config.json and retry.",
				"count": 0,
			}
		with _build_boss_adapter(self.ctx) as adapter:
			result = adapter.sync_messages(conversation_id=conversation_id)
		return {
			"ok": True,
			"status": "synced",
			"count": result.count,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
		}

	def list_pipeline_candidates(self) -> list[dict[str, object]]:
		config = self.ctx.obj.get("config", {}) if self.ctx and self.ctx.obj else {}
		if not bool(config.get("boss_rag_allow_message_read", False)):
			return []
		with _build_boss_adapter(self.ctx) as adapter:
			return adapter.list_pipeline_candidates(stale_days=3)


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
		salary_reply=str(config.get("boss_rag_salary_reply") or ""),
	)


def _build_watcher_config(ctx: click.Context) -> WatcherConfig:
	"""Build passive watcher config from the loaded Boss config mapping."""
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	return WatcherConfig.from_mapping(config)


def _build_passive_watcher(ctx: click.Context) -> BossPassiveWatcher:
	"""Construct the passive watcher using the shared RAG service and CLI delivery."""
	service = _build_service(ctx)
	syncer = _CliWatcherMessageSyncer(ctx)
	return BossPassiveWatcher(
		store=service.store,
		service=service,
		config=_build_watcher_config(ctx),
		delivery=_CliWatcherDelivery(ctx),
		message_syncer=syncer,
		pipeline_candidate_provider=syncer,
	)


def _watcher_result_payload(result: WatcherRunResult) -> dict[str, object]:
	"""Serialize a watcher run result for the CLI JSON envelope."""
	return {
		"status": "completed",
		"processed": result.processed,
		"skipped": result.skipped,
		"blocked": result.blocked,
		"tasks": result.tasks[-20:],
	}


def _emit_watcher_cycle_progress(cycle: int, result: WatcherRunResult) -> None:
	click.echo(
		(
			f"Watcher cycle {cycle} processed {result.processed} task(s), "
			f"skipped {result.skipped}, blocked {result.blocked}."
		),
		err=True,
	)


def _watcher_audit_payload(entry: AuditLogRecord) -> dict[str, object]:
	"""Serialize watcher audit entries for status/control commands."""
	payload = dict(entry.payload) if isinstance(entry.payload, dict) else {}
	return {
		"log_id": entry.log_id,
		"event_type": entry.event_type,
		"entity_type": entry.entity_type,
		"entity_id": entry.entity_id,
		"created_at": entry.created_at,
		**payload,
	}


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


def _cached_target_identity(conversation: ConversationRecord) -> tuple[str, ...]:
	state = conversation.state if isinstance(conversation.state, dict) else {}
	gid = str(state.get("gid") or state.get("friend_id") or state.get("uid") or "").strip()
	if gid:
		return ("gid", gid)
	recruiter_id = str(conversation.recruiter_id or "").strip()
	job_id = str(conversation.job_id or "").strip()
	if recruiter_id and job_id:
		return ("recruiter_job", recruiter_id, job_id)
	security_id = str(state.get("security_id") or "").strip()
	if security_id:
		return ("security", security_id)
	return ("conversation", conversation.conversation_id)


def _cached_recent_targets(store: RagReplyStore, *, limit: int) -> list[dict[str, object]]:
	targets: list[dict[str, object]] = []
	seen_identities: set[tuple[str, ...]] = set()
	unique_limit = max(limit, 0)
	if unique_limit == 0:
		return targets
	for conversation in store.list_conversations():
		if str(conversation.source or "") != "boss_sync":
			continue
		identity = _cached_target_identity(conversation)
		if identity in seen_identities:
			continue
		state = conversation.state if isinstance(conversation.state, dict) else {}
		security_id = str(state.get("security_id") or "").strip()
		if not security_id:
			continue
		seen_identities.add(identity)
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
		if len(targets) >= unique_limit:
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
@click.option("--send-attachment-resume", is_flag=True, default=False)
@click.option("--resume-file", default=None)
@click.option("--target-recruiter-name", default="")
@click.option("--target-company", default="")
@click.option("--target-title", default="")
@click.pass_context
def rag_send_cmd(
	ctx: click.Context,
	draft_id: str,
	security_id: str | None,
	send_resume: bool,
	send_attachment_resume: bool,
	resume_file: str | None,
	target_recruiter_name: str,
	target_company: str,
	target_title: str,
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
		send_attachment_resume=send_attachment_resume,
		resume_file_path=resume_file,
		target_recruiter_name=target_recruiter_name,
		target_company=target_company,
		target_title=target_title,
	)
	target_payload = {
		"recruiter_name": target_recruiter_name,
		"company": target_company,
		"title": target_title,
	}
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="draft_send",
			entity_type="draft",
			entity_id=draft_id,
			payload={
				"conversation_id": draft.conversation_id,
				"security_id": resolved_security_id,
				"send_resume": send_resume,
				"send_attachment_resume": send_attachment_resume,
				"resume_file": result.resume_file_path,
				"message_sent": result.message_sent,
				"resume_sent": result.resume_sent,
				"error_message": result.error_message,
				"target": target_payload,
			},
		)
	)
	if not result.message_sent and not (send_attachment_resume and result.resume_sent):
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
			"send_attachment_resume": send_attachment_resume,
			"resume_file": result.resume_file_path,
			"target": target_payload,
			"results": result.results,
			"error_message": result.error_message,
		},
		render=lambda data: click.echo(
			f"Sent draft {data['draft']['draft_id']} to {data['security_id']}.",
			err=True,
		),
	)


@rag_group.command("watcher-status")
@click.option("--limit", default=10, type=int, show_default=True)
@click.pass_context
def rag_watcher_status_cmd(ctx: click.Context, limit: int) -> None:
	store = _resolve_store(ctx)
	config = _build_watcher_config(ctx)
	safe_limit = max(1, min(limit, 50))
	task_entries = [
		entry
		for entry in store.list_audit_logs()
		if entry.event_type == "watcher_task"
	]
	recent_tasks = task_entries[-safe_limit:]
	handle_output(
		ctx,
		_workflow_command(ctx, "watcher-status"),
		{
			"running": config.enabled,
			"dry_run": config.dry_run,
			"tasks": [_watcher_audit_payload(entry) for entry in recent_tasks],
		},
		render=lambda data: click.echo(
			f"Watcher is {'enabled' if data['running'] else 'paused'}; {len(data['tasks'])} recent task(s).",
			err=True,
		),
	)


@rag_group.command("watcher-run")
@click.option("--once", is_flag=True, default=False)
@click.option("--loop", "loop_mode", is_flag=True, default=False)
@click.option("--live-sync/--no-live-sync", default=None)
@click.option("--max-cycles", type=int, default=None)
@click.option("--ensure-chat-page", is_flag=True, default=False)
@click.pass_context
def rag_watcher_run_cmd(
	ctx: click.Context,
	once: bool,
	loop_mode: bool,
	live_sync: bool | None,
	max_cycles: int | None,
	ensure_chat_page: bool,
) -> None:
	if once == loop_mode:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			code="INVALID_PARAM",
			message="watcher-run requires exactly one of --once or --loop.",
			recoverable=True,
			recovery_action="Run agent watcher-run --once or agent watcher-run --loop.",
		)
		return
	config = _build_watcher_config(ctx)
	if loop_mode and max_cycles is not None and max_cycles < 1:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			code="INVALID_PARAM",
			message="watcher-run --max-cycles must be at least 1.",
			recoverable=True,
			recovery_action="Run agent watcher-run --loop --max-cycles 1 or omit --max-cycles for a continuous loop.",
		)
		return
	effective_live_sync = config.live_sync if live_sync is None else live_sync
	if not config.enabled:
		handle_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			{
				"status": "paused",
				"reason": "watcher_disabled",
				"processed": 0,
				"skipped": 0,
				"blocked": 0,
				"tasks": [],
			},
			render=lambda data: click.echo("Watcher is disabled; no tasks processed.", err=True),
		)
		return
	chat_page: dict[str, object] = {}
	if ensure_chat_page:
		chat_page = ensure_candidate_chat_page_via_cdp(ctx.obj.get("cdp_url"))
		if not chat_page.get("ok"):
			handle_error_output(
				ctx,
				_workflow_command(ctx, "watcher-run"),
				code=str(chat_page.get("code") or "CDP_CHAT_PAGE_NOT_READY"),
				message=str(chat_page.get("message") or "Boss 聊天页未就绪。"),
				recoverable=bool(chat_page.get("recoverable", True)),
				recovery_action=str(chat_page.get("recovery_action") or "打开 BOSS 聊天页后重试"),
				details=chat_page,
			)
			return
	watcher = _build_passive_watcher(ctx)
	if once:
		payload = _watcher_result_payload(watcher.run_once(live_sync=effective_live_sync))
	else:
		cycles = 0
		processed = 0
		skipped = 0
		blocked = 0
		tasks: list[dict[str, object]] = []
		while max_cycles is None or cycles < max_cycles:
			result = watcher.run_once(live_sync=effective_live_sync)
			cycles += 1
			processed += result.processed
			skipped += result.skipped
			blocked += result.blocked
			tasks.extend(result.tasks)
			if not bool(ctx.obj.get("json_output", False)):
				_emit_watcher_cycle_progress(cycles, result)
			if max_cycles is not None and cycles >= max_cycles:
				break
			time.sleep(config.poll_seconds)
		payload = {
			"status": "completed",
			"cycles": cycles,
			"processed": processed,
			"skipped": skipped,
			"blocked": blocked,
			"tasks": tasks[-20:],
		}
	if chat_page:
		payload["chat_page"] = chat_page
	handle_output(
		ctx,
		_workflow_command(ctx, "watcher-run"),
		payload,
		render=lambda data: click.echo(
			f"Watcher processed {data['processed']} task(s), skipped {data['skipped']}, blocked {data['blocked']}.",
			err=True,
		),
	)


def _write_watcher_control(ctx: click.Context, *, action: str, conversation_id: str | None) -> dict[str, object]:
	store = _resolve_store(ctx)
	target = str(conversation_id or "").strip()
	entity_type = "conversation" if target else "watcher"
	entity_id = target or "global"
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="watcher_control",
			entity_type=entity_type,
			entity_id=entity_id,
			payload={
				"action": action,
				"conversation_id": target,
				"scope": "conversation" if target else "global",
			},
		)
	)
	return {
		"action": action,
		"conversation_id": target,
		"scope": "conversation" if target else "global",
	}


@rag_group.command("watcher-pause")
@click.option("--conversation-id", default=None)
@click.pass_context
def rag_watcher_pause_cmd(ctx: click.Context, conversation_id: str | None) -> None:
	payload = _write_watcher_control(ctx, action="pause", conversation_id=conversation_id)
	handle_output(
		ctx,
		_workflow_command(ctx, "watcher-pause"),
		payload,
		render=lambda data: click.echo(f"Watcher pause recorded for {data['scope']}.", err=True),
	)


@rag_group.command("watcher-resume")
@click.option("--conversation-id", default=None)
@click.pass_context
def rag_watcher_resume_cmd(ctx: click.Context, conversation_id: str | None) -> None:
	payload = _write_watcher_control(ctx, action="resume", conversation_id=conversation_id)
	handle_output(
		ctx,
		_workflow_command(ctx, "watcher-resume"),
		payload,
		render=lambda data: click.echo(f"Watcher resume recorded for {data['scope']}.", err=True),
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
