"""Passive watcher orchestration for inbound Boss HR messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from boss_agent_cli.rag_reply.auto_actions import AutoReplyAction
from boss_agent_cli.rag_reply.auto_graph import run_auto_reply_graph
from boss_agent_cli.rag_reply.models import AuditLogRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
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
    ) -> None:
        self.store = store
        self.service = service
        self.config = config
        self.delivery = delivery
        self.message_syncer = message_syncer

    def run_once(self, *, live_sync: bool | None = None) -> WatcherRunResult:
        if live_sync is None:
            live_sync = self.config.live_sync
        if live_sync and self.message_syncer is not None:
            self.message_syncer.sync_messages()
        processed = 0
        skipped = 0
        blocked = 0
        tasks: list[dict[str, object]] = []
        for message in self._candidate_messages():
            if self._is_paused(message.conversation_id):
                blocked += 1
                task = self._record_task(
                    message=message,
                    status="paused",
                    intent="unknown",
                    draft_id="",
                    error_message="conversation_paused",
                )
                tasks.append(task)
                continue
            if self._already_processed(message.message_id):
                skipped += 1
                tasks.append(
                    {"message_id": message.message_id, "status": "skipped_duplicate"}
                )
                continue
            task = self._process_message(message)
            tasks.append(task)
            if task["status"] == "sent":
                processed += 1
            elif task["status"] in {"blocked_manual_required", "paused"}:
                blocked += 1
            else:
                processed += 1
        return WatcherRunResult(
            processed=processed, skipped=skipped, blocked=blocked, tasks=tasks
        )

    def _candidate_messages(self) -> list[MessageRecord]:
        return [
            message
            for message in self.store.list_messages()
            if message.direction == "inbound" and message.message_text.strip()
        ]

    def _already_processed(self, message_id: str) -> bool:
        for entry in self.store.list_audit_logs():
            if (
                entry.event_type == "watcher_task"
                and entry.payload.get("message_id") == message_id
                and entry.payload.get("status") != "paused"
            ):
                return True
        return False

    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        draft = self.service.create_draft_for_message(message.message_id)
        result = run_auto_reply_graph(
            message=message,
            draft=draft,
            config=self.config,
            resolve_security_id=self._resolve_security_id,
            target_payload=self._target_payload,
            delivery=self.delivery,
        )
        return self._record_task(
            message=message,
            status=result.status,
            intent=result.intent,
            draft_id=draft.draft_id,
            error_message=result.error_message,
            dry_run=result.dry_run,
            action=_action_from_payload(result.action),
            delivery=result.delivery,
        )

    def _record_task(
        self,
        *,
        message: MessageRecord,
        status: str,
        intent: str,
        draft_id: str,
        error_message: str = "",
        dry_run: bool = False,
        action: AutoReplyAction | None = None,
        delivery: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = {
            "message_id": message.message_id,
            "conversation_id": message.conversation_id,
            "draft_id": draft_id,
            "intent": intent,
            "status": status,
            "error_message": error_message,
            "dry_run": dry_run,
            "action": _action_payload(action),
            "delivery": delivery or {},
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

    def _is_paused(self, conversation_id: str) -> bool:
        paused = False
        for entry in self.store.list_audit_logs(conversation_id):
            if entry.event_type != "watcher_control":
                continue
            payload_conversation_id = entry.payload.get("conversation_id")
            if payload_conversation_id and payload_conversation_id != conversation_id:
                continue
            action = str(entry.payload.get("action") or "").lower()
            if action == "pause":
                paused = True
            elif action == "resume":
                paused = False
        return paused

    def _resolve_security_id(self, conversation_id: str) -> str:
        conversation = self.store.get_conversation(conversation_id)
        if conversation and isinstance(conversation.state, dict):
            return str(conversation.state.get("security_id") or "").strip()
        return ""

    def _target_payload(self, conversation_id: str) -> dict[str, str]:
        conversation = self.store.get_conversation(conversation_id)
        state = (
            conversation.state
            if conversation and isinstance(conversation.state, dict)
            else {}
        )
        return {
            "recruiter_name": str(state.get("recruiter_name") or ""),
            "company": str(state.get("company") or ""),
            "title": str(state.get("title") or ""),
        }


def _action_payload(action: AutoReplyAction | None) -> dict[str, object]:
    if action is None:
        return {}
    return {
        "kind": action.kind,
        "message": action.message,
        "status_after_send": action.status_after_send,
        "send_attachment_resume": action.send_attachment_resume,
        "resume_file": action.resume_file,
        "blocked_reason": action.blocked_reason,
    }


def _action_from_payload(payload: dict[str, object]) -> AutoReplyAction | None:
    if not payload:
        return None
    return AutoReplyAction(
        kind=str(payload.get("kind") or ""),
        message=str(payload.get("message") or ""),
        status_after_send=str(payload.get("status_after_send") or "sent"),
        send_attachment_resume=bool(payload.get("send_attachment_resume") or False),
        resume_file=str(payload.get("resume_file") or ""),
        blocked_reason=str(payload.get("blocked_reason") or ""),
    )
