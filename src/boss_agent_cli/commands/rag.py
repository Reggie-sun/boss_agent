"""Boss RAG reply workflow commands."""

from __future__ import annotations

from pathlib import Path

import click

from boss_agent_cli.ai.config import AIConfigStore, PROVIDER_BASE_URLS
from boss_agent_cli.ai.service import AIService
from boss_agent_cli.auth.manager import AuthManager
from boss_agent_cli.commands._platform import get_platform_instance
from boss_agent_cli.display import handle_error_output, handle_output
from boss_agent_cli.display import handle_auth_errors
from boss_agent_cli.rag_reply.adapters.ai_fallback import AIFallbackAdapter
from boss_agent_cli.rag_reply.adapters.boss_automation import BossAutomationAdapter, BossAutomationError
from boss_agent_cli.rag_reply.adapters.manual_import import import_messages
from boss_agent_cli.rag_reply.adapters.mock_envelope import load_and_ingest_mock_envelope
from boss_agent_cli.rag_reply.adapters.rag_http import RagHttpAdapter
from boss_agent_cli.rag_reply.review import draft_to_payload
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _resolve_store(ctx: click.Context) -> RagReplyStore:
	"""Return the workflow store initialized at the configured location."""
	data_dir = Path(ctx.obj["data_dir"])
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	configured = config.get("boss_rag_db_path")
	db_path = Path(str(configured)).expanduser() if configured else data_dir / "boss-rag.sqlite3"
	store = RagReplyStore(db_path)
	store.initialize()
	return store


def _build_ai_fallback_adapter(ctx: click.Context) -> AIFallbackAdapter | None:
	"""Construct the optional local AI fallback adapter."""
	data_dir = Path(ctx.obj["data_dir"])
	store = AIConfigStore(data_dir)
	if not store.is_configured():
		config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
		rag_api_key = config.get("boss_rag_rag_api_key")
		if not rag_api_key:
			return None
		return AIFallbackAdapter(
			ai_service=AIService(
				base_url=str(PROVIDER_BASE_URLS["deepseek"]),
				api_key=str(rag_api_key),
				model="deepseek-chat",
			)
		)
	api_key = store.get_api_key()
	base_url = store.get_base_url()
	if not api_key or not base_url:
		return None
	config = store.load_config()
	return AIFallbackAdapter(
		ai_service=AIService(
			base_url=base_url,
			api_key=api_key,
			model=config["ai_model"],
			temperature=config.get("ai_temperature", 0.7),
			max_tokens=config.get("ai_max_tokens", 4096),
		)
	)


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
	)


def _build_boss_adapter(ctx: click.Context) -> BossAutomationAdapter:
	"""Construct the read-only Boss automation adapter."""
	data_dir = Path(ctx.obj["data_dir"])
	logger = ctx.obj["logger"]
	auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
	platform = get_platform_instance(ctx, auth)
	return BossAutomationAdapter(platform=platform, store=_resolve_store(ctx))


def _require_message_read_enabled(ctx: click.Context) -> bool:
	"""Return False with a structured error when Boss message reading is disabled."""
	config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
	if bool(config.get("boss_rag_allow_message_read", False)):
		return True
	handle_error_output(
		ctx,
		"rag-sync-messages",
		code="RAG_READ_NOT_ENABLED",
		message="Boss message reading is disabled by default. Enable boss_rag_allow_message_read explicitly before syncing messages.",
		recoverable=True,
		recovery_action="Set boss_rag_allow_message_read=true in config.json and retry.",
		hints={
			"manual_action_required": True,
			"default_safe_mode": True,
			"next_actions": [
				"Use boss rag import-messages for manual fallback.",
				"Use boss rag ingest-mock for structured mock envelope testing.",
			],
		},
	)
	return False


def _not_implemented(ctx: click.Context, command: str) -> None:
	"""Emit a consistent placeholder response for unimplemented subcommands."""
	handle_error_output(
		ctx,
		command,
		code="NOT_IMPLEMENTED",
		message="This Boss RAG workflow command is planned but not implemented yet.",
		recoverable=False,
		recovery_action="Continue with the next implementation task in docs/superpowers/plans/2026-06-10-boss-rag-reply-agent-implementation-plan.md.",
	)


@click.group("rag")
@click.pass_context
def rag_group(ctx: click.Context) -> None:
	"""Boss RAG reply workflow commands."""
	ctx.ensure_object(dict)


@rag_group.command("init")
@click.pass_context
def rag_init_cmd(ctx: click.Context) -> None:
	store = _resolve_store(ctx)
	handle_output(
		ctx,
		"rag-init",
		{"status": "initialized", "db_path": str(store.db_path)},
		render=lambda data: click.echo(f"Initialized Boss RAG store at {data['db_path']}.", err=True),
	)


@rag_group.command("import-messages")
@click.option("--file", "file_path", required=False)
@click.option("--format", "fmt", type=click.Choice(["json", "md", "csv"]), required=False)
@click.pass_context
def rag_import_messages_cmd(ctx: click.Context, file_path: str | None, fmt: str | None) -> None:
	if not file_path or not fmt:
		_not_implemented(ctx, "rag-import-messages")
		return
	store = _resolve_store(ctx)
	result = import_messages(Path(file_path), fmt, store)
	handle_output(
		ctx,
		"rag-import-messages",
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
		_not_implemented(ctx, "rag-ingest-mock")
		return
	store = _resolve_store(ctx)
	result = load_and_ingest_mock_envelope(Path(file_path), store)
	handle_output(
		ctx,
		"rag-ingest-mock",
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
			"rag-sync-jobs",
			code=exc.code,
			message=exc.message,
			recoverable=exc.recoverable,
			recovery_action=exc.recovery_action,
			hints=exc.hints,
		)
		return
	handle_output(
		ctx,
		"rag-sync-jobs",
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
			"rag-sync-messages",
			code=exc.code,
			message=exc.message,
			recoverable=exc.recoverable,
			recovery_action=exc.recovery_action,
			hints=exc.hints,
		)
		return
	handle_output(
		ctx,
		"rag-sync-messages",
		{
			"import_batch_id": result.import_batch_id,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
			"count": result.count,
		},
		render=lambda data: click.echo(f"Synced {data['count']} recruiter message(s).", err=True),
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
		"rag-draft",
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
				"rag-review",
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
		"rag-review",
		payload,
		render=lambda data: click.echo("Draft review ready.", err=True),
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
		"rag-approve",
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
		"rag-audit",
		payload,
		render=lambda data: click.echo(f"Found {len(data)} audit log(s).", err=True),
	)
