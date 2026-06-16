"""Passive watcher orchestration for inbound Boss HR messages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from boss_agent_cli.rag_reply.models import AuditLogRecord, DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import (
    WatcherConfig,
    WatcherConfigError,
    build_contact_reply,
    build_interview_window_reply,
    salary_handoff_reply,
)


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


@dataclass(slots=True)
class WatcherAction:
    kind: str
    message: str = ""
    status_after_send: str = "sent"
    send_attachment_resume: bool = False
    resume_file: str = ""
    blocked_reason: str = ""


def build_action_for_draft(draft: DraftRecord, config: WatcherConfig) -> WatcherAction:
    intent = draft.intent
    draft_text = (draft.draft_text or "").strip()
    if intent in {
        "project_question",
        "resume_question",
        "smalltalk",
        "resignation_status",
        "personal_status",
        "job_location_acceptance",
    }:
        if not draft_text:
            return WatcherAction(
                kind="block", status_after_send="rag_failed", blocked_reason="empty_draft"
            )
        return WatcherAction(kind="send_text", message=draft_text)
    if intent == "resume_share_request":
        resume_file = _require_resume_file(config.resume_attachment_path)
        message = draft_text or "可以的，我这边通过 BOSS 直聘发送附件简历给您。"
        return WatcherAction(
            kind="send_text",
            message=message,
            send_attachment_resume=True,
            resume_file=resume_file,
        )
    if intent in {"interview_time", "availability_or_schedule"}:
        return WatcherAction(
            kind="send_text", message=build_interview_window_reply(config)
        )
    if intent == "contact_exchange":
        return WatcherAction(kind="send_text", message=build_contact_reply(config))
    if intent == "salary_or_offer":
        if draft_text and draft_text != salary_handoff_reply():
            return WatcherAction(kind="send_text", message=draft_text)
        return WatcherAction(
            kind="send_text",
            message=salary_handoff_reply(),
            status_after_send="blocked_manual_required",
        )
    return WatcherAction(
        kind="block",
        status_after_send="blocked_manual_required",
        blocked_reason="intent_not_allowlisted",
    )


def _require_resume_file(value: str) -> str:
    path = Path(value).expanduser()
    if not value.strip() or not path.is_file():
        raise WatcherConfigError(
            "boss_rag_resume_attachment_path must point to an existing PDF file."
        )
    if path.suffix.lower() != ".pdf":
        raise WatcherConfigError(
            "boss_rag_resume_attachment_path must point to a PDF file."
        )
    return str(path)


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
    ) -> None:
        self.store = store
        self.service = service
        self.config = config
        self.delivery = delivery

    def run_once(self) -> WatcherRunResult:
        processed = 0
        skipped = 0
        blocked = 0
        tasks: list[dict[str, object]] = []
        for message in self._candidate_messages():
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
            elif task["status"] == "blocked_manual_required":
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
            ):
                return True
        return False

    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        draft = self.service.create_draft_for_message(message.message_id)
        try:
            action = build_action_for_draft(draft, self.config)
        except WatcherConfigError as exc:
            return self._record_task(
                message=message,
                status="blocked_manual_required",
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message=str(exc),
            )
        if action.kind == "block":
            return self._record_task(
                message=message,
                status=action.status_after_send,
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message=action.blocked_reason,
            )
        security_id = self._resolve_security_id(message.conversation_id)
        if not security_id:
            return self._record_task(
                message=message,
                status="blocked_manual_required",
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message="missing_security_id",
            )
        target = self._target_payload(message.conversation_id)
        if self.config.dry_run:
            return self._record_task(
                message=message,
                status=action.status_after_send,
                intent=draft.intent,
                draft_id=draft.draft_id,
                dry_run=True,
                action=action,
                delivery={"ok": True, "status": "dry_run"},
            )
        delivery = self.delivery.send(
            security_id=security_id,
            message=action.message,
            send_attachment_resume=action.send_attachment_resume,
            resume_file=action.resume_file,
            target=target,
        )
        status = action.status_after_send if delivery.get("ok") else "send_failed"
        return self._record_task(
            message=message,
            status=status,
            intent=draft.intent,
            draft_id=draft.draft_id,
            action=action,
            delivery=delivery,
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
        action: WatcherAction | None = None,
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


def _action_payload(action: WatcherAction | None) -> dict[str, object]:
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
