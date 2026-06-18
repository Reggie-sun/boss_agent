"""Passive watcher orchestration for inbound Boss HR messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from boss_agent_cli.display import error_contract_for_code
from boss_agent_cli.rag_reply.agent_tools import (
    BossAgentToolContext,
    BossAgentToolbox,
    ToolResult,
)
from boss_agent_cli.rag_reply.models import AuditLogRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.tool_graph import run_tool_reply_graph
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


WATCHER_STATUSES = {
    "queued",
    "processing",
    "sent",
    "blocked_manual_required",
    "skipped_duplicate",
    "runtime_unavailable",
    "target_ambiguous",
    "rag_failed",
    "attachment_failed",
    "send_failed",
    "paused",
    "dry_run",
}


class WatcherDelivery(Protocol):
    def send(
        self,
        *,
        security_id: str,
        message: str,
        send_attachment_resume: bool = False,
        resume_file: str = "",
        target: dict[str, str] | None = None,
    ) -> dict[str, object]:
        ...


class WatcherMessageSyncer(Protocol):
    def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
        ...


class WatcherPipelineCandidateProvider(Protocol):
    def list_pipeline_candidates(self) -> list[dict[str, object]]:
        ...


@dataclass(slots=True)
class WatcherRunResult:
    processed: int
    skipped: int
    blocked: int
    tasks: list[dict[str, object]]


class BossPassiveWatcher:
    def __init__(
        self,
        *,
        store: RagReplyStore,
        service: BossRagReplyService,
        config: WatcherConfig,
        delivery: WatcherDelivery,
        message_syncer: WatcherMessageSyncer | None = None,
        pipeline_candidate_provider: WatcherPipelineCandidateProvider | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.config = config
        self.delivery = delivery
        self.message_syncer = message_syncer
        self.pipeline_candidate_provider = pipeline_candidate_provider

    def run_once(self, *, live_sync: bool | None = None) -> WatcherRunResult:
        if live_sync is None:
            live_sync = self.config.live_sync
        if not live_sync and not self.config.dry_run:
            task = self._record_run_task(
                _sync_blocked_task(
                    "live_sync_required_for_delivery",
                    live_sync=False,
                    dry_run=self.config.dry_run,
                )
            )
            return WatcherRunResult(
                processed=0,
                skipped=0,
                blocked=1,
                tasks=[task],
            )
        if live_sync:
            sync_error = self._sync_live_messages()
            if sync_error is not None:
                task = self._record_run_task(sync_error)
                return WatcherRunResult(
                    processed=0,
                    skipped=0,
                    blocked=1,
                    tasks=[task],
                )
        processed = 0
        skipped = 0
        blocked = 0
        tasks: list[dict[str, object]] = []
        for message in self._candidate_messages():
            if self._already_processed(message):
                skipped += 1
                tasks.append(
                    {"message_id": message.message_id, "status": "skipped_duplicate"}
                )
                continue
            if self._is_paused(message.conversation_id):
                blocked += 1
                task = self._record_paused_task(message)
                tasks.append(task)
                continue
            task = self._process_message(message)
            tasks.append(task)
            if task["status"] == "sent":
                processed += 1
            elif task["status"] in {"blocked_manual_required", "paused"}:
                blocked += 1
            else:
                processed += 1
        try:
            pipeline_candidates = self._pipeline_candidates()
        except Exception as exc:
            metadata = _sync_error_metadata(exc)
            task = self._record_run_task(
                _sync_blocked_task(
                    metadata["error_message"],
                    {"error_message": metadata["error_message"]},
                    dry_run=self.config.dry_run,
                    error_code=metadata["error_code"],
                    recoverable=metadata["recoverable"],
                    recovery_action=metadata["recovery_action"],
                    hints=metadata["hints"],
                )
            )
            tasks.append(task)
            blocked += 1
            return WatcherRunResult(
                processed=processed,
                skipped=skipped,
                blocked=blocked,
                tasks=tasks,
            )
        for candidate in pipeline_candidates:
            if self._already_processed_pipeline_candidate(candidate):
                skipped += 1
                tasks.append(
                    {
                        "security_id": str(candidate.get("security_id") or ""),
                        "stage": "read_no_reply",
                        "status": "skipped_duplicate",
                    }
                )
                continue
            task = self._process_pipeline_candidate(candidate)
            tasks.append(task)
            if task["status"] in {"blocked_manual_required", "paused"}:
                blocked += 1
            else:
                processed += 1
        return WatcherRunResult(
            processed=processed, skipped=skipped, blocked=blocked, tasks=tasks
        )

    def _sync_live_messages(self) -> dict[str, object] | None:
        if self.message_syncer is None:
            return _sync_blocked_task(
                "live_sync_unavailable", dry_run=self.config.dry_run
            )
        try:
            result = self.message_syncer.sync_messages() or {}
        except Exception as exc:
            metadata = _sync_error_metadata(exc)
            return _sync_blocked_task(
                metadata["error_message"],
                {"error_message": metadata["error_message"]},
                dry_run=self.config.dry_run,
                error_code=metadata["error_code"],
                recoverable=metadata["recoverable"],
                recovery_action=metadata["recovery_action"],
                hints=metadata["hints"],
            )
        if result.get("ok") is False:
            metadata = _sync_error_metadata(result)
            return _sync_blocked_task(
                metadata["error_message"],
                result,
                dry_run=self.config.dry_run,
                error_code=metadata["error_code"],
                recoverable=metadata["recoverable"],
                recovery_action=metadata["recovery_action"],
                hints=metadata["hints"],
            )
        return None

    def _candidate_messages(self) -> list[MessageRecord]:
        latest_by_conversation: dict[str, MessageRecord] = {}
        for message in self.store.list_messages():
            if message.direction != "inbound" or not message.message_text.strip():
                continue
            latest_by_conversation[message.conversation_id] = message
        return list(latest_by_conversation.values())

    def _pipeline_candidates(self) -> list[dict[str, object]]:
        provider = self.pipeline_candidate_provider
        if provider is None:
            return []
        return [
            candidate
            for candidate in provider.list_pipeline_candidates()
            if candidate.get("stage") == "read_no_reply"
            and str(candidate.get("security_id") or "").strip()
        ]

    def _already_processed(self, message: MessageRecord) -> bool:
        message_key = _platform_message_key(message)
        for entry in self.store.list_audit_logs():
            if (
                entry.event_type != "watcher_task"
                or entry.payload.get("status") == "paused"
            ):
                continue
            processed_message_id = str(entry.payload.get("message_id") or "")
            if processed_message_id == message.message_id:
                return True
            if not message_key or not processed_message_id:
                continue
            processed_message = self.store.get_message(processed_message_id)
            if (
                processed_message is not None
                and _platform_message_key(processed_message) == message_key
            ):
                return True
        return False

    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        context = BossAgentToolContext(
            store=self.store,
            service=self.service,
            config=self.config,
            delivery=self.delivery,
            message_syncer=self.message_syncer,
        )
        result = run_tool_reply_graph(
            message=message,
            toolbox=BossAgentToolbox(context),
        )
        return result.task

    def _process_pipeline_candidate(self, candidate: dict[str, object]) -> dict[str, object]:
        context = BossAgentToolContext(
            store=self.store,
            service=self.service,
            config=self.config,
            delivery=self.delivery,
            message_syncer=self.message_syncer,
        )
        security_id = str(candidate.get("security_id") or "").strip()
        target = _pipeline_target_payload(candidate)
        result = BossAgentToolbox(context).send_read_no_reply_followup_guarded(
            security_id=security_id,
            message=str(candidate.get("message") or ""),
            target=target,
        )
        tool_steps = [
            _tool_step_payload("send_read_no_reply_followup_guarded", result),
            {
                "tool": "record_watcher_audit",
                "ok": True,
                "status": "audit_recorded",
                "error_code": "",
                "error_message": "",
            },
        ]
        task = {
            "message_id": "",
            "conversation_id": "",
            "draft_id": "",
            "intent": "read_no_reply",
            "stage": "read_no_reply",
            "security_id": security_id,
            "status": result.status,
            "error_message": result.error_message,
            "dry_run": self.config.dry_run,
            "action": {
                "kind": "send_read_no_reply_followup",
                "message": str(result.data.get("message") or ""),
            },
            "delivery": dict(result.data.get("delivery") or {}),
            "target": target,
            "tool_steps": tool_steps,
        }
        self.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="security_id",
                entity_id=security_id,
                payload=task,
            )
        )
        return task

    def _record_paused_task(self, message: MessageRecord) -> dict[str, object]:
        payload = {
            "message_id": message.message_id,
            "conversation_id": message.conversation_id,
            "draft_id": "",
            "intent": "unknown",
            "status": "paused",
            "error_message": "conversation_paused",
            "dry_run": self.config.dry_run,
            "action": {},
            "delivery": {},
            "tool_steps": [],
        }
        self.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id=message.conversation_id,
                payload=payload,
            )
        )
        return payload

    def _record_run_task(self, payload: dict[str, object]) -> dict[str, object]:
        self.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="watcher",
                entity_id="live_sync",
                payload=payload,
            )
        )
        return payload

    def _is_paused(self, conversation_id: str) -> bool:
        paused = False
        for entry in self.store.list_audit_logs():
            if entry.event_type != "watcher_control":
                continue
            payload_conversation_id = entry.payload.get("conversation_id")
            applies_globally = (
                entry.entity_id == "global"
                or entry.payload.get("scope") == "global"
            )
            applies_to_conversation = (
                entry.entity_id == conversation_id
                or payload_conversation_id == conversation_id
            )
            if not (applies_globally or applies_to_conversation):
                continue
            action = str(entry.payload.get("action") or "").lower()
            if action == "pause":
                paused = True
            elif action == "resume":
                paused = False
        return paused

    def _already_processed_pipeline_candidate(self, candidate: dict[str, object]) -> bool:
        security_id = str(candidate.get("security_id") or "").strip()
        if not security_id:
            return True
        for entry in self.store.list_audit_logs():
            payload_security_id = str(entry.payload.get("security_id") or "")
            if entry.event_type == "read_no_reply_followup":
                if payload_security_id == security_id and entry.payload.get("status") == "sent":
                    return True
                continue
            if entry.event_type != "watcher_task":
                continue
            if payload_security_id != security_id:
                continue
            if entry.payload.get("status") == "paused":
                continue
            if (
                entry.payload.get("stage") == "read_no_reply"
                or entry.payload.get("intent") == "read_no_reply"
            ):
                return True
        return False


def _sync_blocked_task(
    error_message: str,
    sync: dict[str, object] | None = None,
    *,
    live_sync: bool = True,
    dry_run: bool = False,
    error_code: str = "",
    recoverable: bool = False,
    recovery_action: str = "",
    hints: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "message_id": "",
        "conversation_id": "",
        "draft_id": "",
        "intent": "unknown",
        "status": "blocked_manual_required",
        "error_message": error_message,
        "error_code": error_code,
        "recoverable": recoverable,
        "recovery_action": recovery_action,
        "dry_run": dry_run,
        "action": {},
        "delivery": {},
        "live_sync": live_sync,
        "sync": sync or {},
        "hints": hints or {},
    }


def _sync_error_metadata(error: object) -> dict[str, object]:
    code = _error_attr(error, "error_code") or _error_attr(error, "code")
    message = (
        _error_attr(error, "error_message")
        or _error_attr(error, "message")
        or _error_attr(error, "status")
        or str(error)
        or error.__class__.__name__
    )
    recoverable = bool(_error_attr(error, "recoverable"))
    recovery_action = _error_attr(error, "recovery_action")
    if code and not recovery_action:
        recoverable, recovery_action = error_contract_for_code(
            code,
            fallback_recoverable=recoverable,
            fallback_recovery_action=recovery_action or None,
        )
    hints = _error_attr(error, "hints")
    return {
        "error_code": str(code or ""),
        "error_message": str(message or ""),
        "recoverable": recoverable,
        "recovery_action": str(recovery_action or ""),
        "hints": hints if isinstance(hints, dict) else {},
    }


def _error_attr(error: object, key: str) -> object:
    if isinstance(error, dict):
        return error.get(key)
    return getattr(error, key, None)


def _pipeline_target_payload(candidate: dict[str, object]) -> dict[str, str]:
    return {
        "recruiter_name": str(candidate.get("recruiter_name") or ""),
        "company": str(candidate.get("company") or ""),
        "title": str(candidate.get("title") or ""),
        "security_id": str(candidate.get("security_id") or ""),
        "gid": str(candidate.get("gid") or ""),
        "friend_id": str(candidate.get("friend_id") or ""),
        "uid": str(candidate.get("uid") or ""),
        "encrypt_boss_id": str(candidate.get("encrypt_boss_id") or ""),
        "recruiter_id": str(candidate.get("recruiter_id") or ""),
    }


def _tool_step_payload(tool_name: str, result: ToolResult) -> dict[str, object]:
    return {
        "tool": tool_name,
        "ok": result.ok,
        "status": result.status,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def _platform_message_key(message: MessageRecord) -> tuple[str, ...] | None:
    raw = message.raw if isinstance(message.raw, dict) else {}
    for key in ("id", "msgId", "messageId", "mid"):
        value = raw.get(key)
        if value not in (None, ""):
            return ("raw_id", str(value))
    from_payload = raw.get("from") if isinstance(raw.get("from"), dict) else {}
    from_uid = from_payload.get("uid")
    timestamp = raw.get("time")
    text = " ".join(message.message_text.split())
    if from_uid not in (None, "") and timestamp not in (None, "") and text:
        return ("sender_time_text", str(from_uid), str(timestamp), text)
    if message.source == "boss_sync" and text and message.created_at:
        return ("boss_text_time", text, message.created_at)
    return None
