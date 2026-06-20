"""Guarded tool facade for Boss inbound reply automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from boss_agent_cli.commands.pipeline import (
    _DEFAULT_READ_NO_REPLY_MESSAGE,
    _READ_NO_REPLY_AGENT_DISCLOSURE,
    _READ_NO_REPLY_FOLLOWUP_EVENT,
    _has_read_no_reply_agent_disclosure,
    _read_no_reply_message,
)
from boss_agent_cli.display import error_contract_for_code
from boss_agent_cli.rag_reply.auto_actions import (
    AutoReplyAction,
    DRAFT_TEXT_REPLY_INTENTS,
    build_action_for_draft,
    require_resume_file,
)
from boss_agent_cli.rag_reply.models import AuditLogRecord, DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig, WatcherConfigError


class AgentToolDraftService(Protocol):
    def create_draft_for_message(self, message_id: str) -> DraftRecord:
        ...


class AgentToolDelivery(Protocol):
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


class AgentToolMessageSyncer(Protocol):
    def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
        ...


@dataclass(slots=True)
class ToolResult:
    ok: bool
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    recoverable: bool = False
    recovery_action: str = ""
    hints: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "data": dict(self.data),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "recoverable": self.recoverable,
            "recovery_action": self.recovery_action,
            "hints": dict(self.hints),
        }


@dataclass(slots=True)
class BossAgentToolContext:
    store: RagReplyStore
    service: AgentToolDraftService
    config: WatcherConfig
    delivery: AgentToolDelivery
    message_syncer: AgentToolMessageSyncer | None = None


class BossAgentToolbox:
    """Fail-closed tools exposed to the Boss inbound reply graph."""

    def __init__(self, context: BossAgentToolContext) -> None:
        self.context = context

    def sync_boss_messages(self, *, conversation_id: str | None = None) -> ToolResult:
        syncer = self.context.message_syncer
        if syncer is None:
            return _blocked_result(error_message="live_sync_unavailable")
        try:
            result = syncer.sync_messages(conversation_id=conversation_id) or {}
        except Exception as exc:
            metadata = _error_metadata(exc)
            return _blocked_result(
                data={"sync": {"error_message": metadata["error_message"]}},
                **metadata,
            )
        if result.get("ok") is False:
            metadata = _error_metadata(result)
            return _blocked_result(data={"sync": dict(result)}, **metadata)
        return ToolResult(ok=True, status="synced", data={"sync": dict(result)})

    def list_unhandled_inbound(self) -> ToolResult:
        latest_by_conversation: dict[str, MessageRecord] = {}
        processed = self._processed_message_ids()
        for message in self.context.store.list_messages():
            if message.direction != "inbound" or not message.message_text.strip():
                continue
            if message.message_id in processed:
                continue
            latest_by_conversation[message.conversation_id] = message
        messages = list(latest_by_conversation.values())
        return ToolResult(
            ok=True,
            status="listed",
            data={
                "messages": [_message_payload(message) for message in messages],
                "message_ids": [message.message_id for message in messages],
            },
        )

    def create_rag_draft(self, *, message_id: str) -> ToolResult:
        try:
            draft = self.context.service.create_draft_for_message(message_id)
        except Exception as exc:
            metadata = _error_metadata(exc)
            return _blocked_result(**metadata)
        return ToolResult(
            ok=True,
            status=draft.audit_status,
            data={
                "draft_id": draft.draft_id,
                "intent": draft.intent,
                "draft_text": draft.draft_text,
            },
        )

    def decide_auto_action(self, *, draft_id: str) -> ToolResult:
        draft = self.context.store.get_draft(draft_id)
        if draft is None:
            return _blocked_result(
                error_code="DRAFT_NOT_FOUND",
                error_message=f"unknown_draft:{draft_id}",
            )
        try:
            action = build_action_for_draft(draft, self.context.config)
            action = self._with_proactive_resume(draft, action)
        except WatcherConfigError as exc:
            return _blocked_result(
                error_code="INVALID_PARAM",
                error_message=str(exc),
            )
        payload = _action_payload(action)
        if action.kind == "block":
            return ToolResult(
                ok=False,
                status=action.status_after_send,
                data={"action": payload},
                error_message=action.blocked_reason,
            )
        return ToolResult(
            ok=True,
            status="action_ready",
            data={"action": payload},
        )

    def _with_proactive_resume(
        self, draft: DraftRecord, action: AutoReplyAction
    ) -> AutoReplyAction:
        if not self.context.config.proactive_resume_enabled:
            return action
        if action.kind != "send_text" or action.send_attachment_resume:
            return action
        if draft.intent not in DRAFT_TEXT_REPLY_INTENTS:
            return action
        if self._conversation_has_sent_resume(draft.conversation_id):
            return action
        return AutoReplyAction(
            kind=action.kind,
            message=action.message,
            status_after_send=action.status_after_send,
            send_attachment_resume=True,
            resume_file=require_resume_file(self.context.config.resume_attachment_path),
            blocked_reason=action.blocked_reason,
        )

    def resolve_boss_target(self, *, conversation_id: str) -> ToolResult:
        target = self._target_payload(conversation_id)
        security_id = target["security_id"].strip()
        if not security_id:
            return _blocked_result(
                error_code="INVALID_PARAM",
                error_message="missing_security_id",
                data={"target": target},
                recoverable=True,
                recovery_action="Sync Boss conversation target and retry.",
            )
        return ToolResult(
            ok=True,
            status="target_resolved",
            data={"security_id": security_id, "target": target},
        )

    def send_boss_reply_guarded(
        self,
        *,
        action: dict[str, object],
        security_id: str,
        target: dict[str, str],
    ) -> ToolResult:
        if not self.context.config.dry_run and not self.context.config.send_enabled:
            return _blocked_result(
                error_code="SEND_DISABLED",
                error_message="boss_rag_send_enabled_disabled",
                recoverable=True,
                recovery_action=(
                    "Run a dry-run first, then explicitly enable Boss RAG sending."
                ),
            )
        message = str(action.get("message") or "").strip()
        if not message:
            return ToolResult(ok=False, status="rag_failed", error_message="empty_message")
        if not security_id.strip():
            return _blocked_result(error_message="missing_security_id")

        status_after_send = str(action.get("status_after_send") or "sent")
        if bool(action.get("send_attachment_resume")):
            return self.send_attachment_resume_guarded(
                message=message,
                security_id=security_id,
                resume_file=str(action.get("resume_file") or ""),
                target=target,
                status_after_send=status_after_send,
            )
        if self.context.config.dry_run:
            return ToolResult(
                ok=True,
                status=status_after_send,
                data={"delivery": {"ok": True, "status": "dry_run"}},
            )

        delivery = self.context.delivery.send(
            security_id=security_id,
            message=message,
            send_attachment_resume=False,
            resume_file="",
            target=target,
        )
        ok = bool(delivery.get("ok"))
        return ToolResult(
            ok=ok,
            status=status_after_send if ok else "send_failed",
            data={"delivery": dict(delivery)},
            error_message="" if ok else str(delivery.get("error_message") or "send_failed"),
        )

    def send_attachment_resume_guarded(
        self,
        *,
        message: str,
        security_id: str,
        resume_file: str,
        target: dict[str, str],
        status_after_send: str = "sent",
    ) -> ToolResult:
        if not self.context.config.dry_run and not self.context.config.send_enabled:
            return _blocked_result(
                error_code="SEND_DISABLED",
                error_message="boss_rag_send_enabled_disabled",
                recoverable=True,
                recovery_action=(
                    "Run a dry-run first, then explicitly enable Boss RAG sending."
                ),
            )
        message = message.strip()
        if not message:
            return ToolResult(ok=False, status="rag_failed", error_message="empty_message")
        if not security_id.strip():
            return _blocked_result(error_message="missing_security_id")
        resolved_resume_file = str(Path(resume_file).expanduser())
        if not _is_pdf_file(resolved_resume_file):
            return ToolResult(
                ok=False,
                status="attachment_failed",
                data={"delivery": {}},
                error_message="invalid_resume_file",
            )
        if self.context.config.dry_run:
            return ToolResult(
                ok=True,
                status=status_after_send,
                data={
                    "delivery": {
                        "ok": True,
                        "status": "dry_run",
                        "send_attachment_resume": True,
                        "resume_file": resolved_resume_file,
                    }
                },
            )

        delivery = self.context.delivery.send(
            security_id=security_id,
            message=message,
            send_attachment_resume=True,
            resume_file=resolved_resume_file,
            target=target,
        )
        ok = bool(delivery.get("ok"))
        return ToolResult(
            ok=ok,
            status=status_after_send if ok else "attachment_failed",
            data={"delivery": dict(delivery)},
            error_message=(
                "" if ok else str(delivery.get("error_message") or "attachment_failed")
            ),
        )

    def send_read_no_reply_followup_guarded(
        self,
        *,
        security_id: str,
        message: str = "",
        target: dict[str, str] | None = None,
    ) -> ToolResult:
        security_id = security_id.strip()
        if not security_id:
            return _blocked_result(error_message="missing_security_id")
        if not self.context.config.dry_run and not self.context.config.send_enabled:
            return _blocked_result(
                error_code="SEND_DISABLED",
                error_message="boss_rag_send_enabled_disabled",
                recoverable=True,
                recovery_action=(
                    "Run a dry-run first, then explicitly enable Boss RAG sending."
                ),
            )
        base_message = message.strip() or _DEFAULT_READ_NO_REPLY_MESSAGE
        final_message = _read_no_reply_message(
            base_message,
            disclose_agent=not _has_read_no_reply_agent_disclosure(
                self.context.store,
                security_id,
            ),
        )
        if self.context.config.dry_run:
            return ToolResult(
                ok=True,
                status="dry_run",
                data={
                    "stage": "read_no_reply",
                    "message": final_message,
                    "message_sent": False,
                    "delivery": {"ok": True, "status": "dry_run"},
                },
            )

        delivery = self.context.delivery.send(
            security_id=security_id,
            message=final_message,
            send_attachment_resume=False,
            resume_file="",
            target=target or {},
        )
        ok = bool(delivery.get("ok"))
        status = "sent" if ok else "send_failed"
        if ok:
            self.context.store.append_audit_log(
                AuditLogRecord.new(
                    event_type=_READ_NO_REPLY_FOLLOWUP_EVENT,
                    entity_type="security_id",
                    entity_id=security_id,
                    payload={
                        "security_id": security_id,
                        "status": "sent",
                        "agent_disclosed": (
                            _READ_NO_REPLY_AGENT_DISCLOSURE in final_message
                        ),
                    },
                )
            )
        return ToolResult(
            ok=ok,
            status=status,
            data={
                "stage": "read_no_reply",
                "message": final_message,
                "message_sent": ok,
                "delivery": dict(delivery),
            },
            error_message="" if ok else str(delivery.get("error_message") or status),
        )

    def record_watcher_audit(
        self,
        *,
        message_id: str,
        conversation_id: str,
        draft_id: str,
        intent: str,
        status: str,
        error_message: str = "",
        dry_run: bool = False,
        action: dict[str, object] | None = None,
        delivery: dict[str, object] | None = None,
        tool_steps: list[dict[str, object]] | None = None,
    ) -> ToolResult:
        payload = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "draft_id": draft_id,
            "intent": intent,
            "status": status,
            "error_message": error_message,
            "dry_run": dry_run,
            "action": action or {},
            "delivery": delivery or {},
            "tool_steps": tool_steps or [],
        }
        self.context.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id=conversation_id,
                payload=payload,
            )
        )
        return ToolResult(ok=True, status="audit_recorded", data={"task": payload})

    def _processed_message_ids(self) -> set[str]:
        processed: set[str] = set()
        for entry in self.context.store.list_audit_logs():
            if (
                entry.event_type == "watcher_task"
                and entry.payload.get("message_id")
                and entry.payload.get("status") != "paused"
            ):
                processed.add(str(entry.payload["message_id"]))
        return processed

    def _conversation_has_sent_resume(self, conversation_id: str) -> bool:
        for entry in self.context.store.list_audit_logs(conversation_id):
            payload = entry.payload
            if payload.get("dry_run") is True:
                continue
            if entry.event_type == "resume_auto_send" and bool(
                payload.get("resume_sent")
            ):
                return True
            if entry.event_type != "watcher_task":
                continue
            delivery = payload.get("delivery") if isinstance(payload, dict) else {}
            if isinstance(delivery, dict) and bool(delivery.get("resume_sent")):
                return True
            action = payload.get("action") if isinstance(payload, dict) else {}
            if not isinstance(action, dict):
                continue
            if (
                bool(action.get("send_attachment_resume"))
                and payload.get("status") == "sent"
            ):
                return True
        return False

    def _target_payload(self, conversation_id: str) -> dict[str, str]:
        conversation = self.context.store.get_conversation(conversation_id)
        state = (
            conversation.state
            if conversation is not None and isinstance(conversation.state, dict)
            else {}
        )
        recruiter = None
        if conversation is not None and conversation.recruiter_id:
            recruiter = self.context.store.get_recruiter(str(conversation.recruiter_id))
        return {
            "recruiter_name": str(
                state.get("recruiter_name")
                or (recruiter.display_name if recruiter else "")
                or ""
            ),
            "company": str(state.get("company") or ""),
            "title": str(state.get("title") or ""),
            "security_id": str(state.get("security_id") or ""),
            "gid": str(state.get("gid") or ""),
            "friend_id": str(state.get("friend_id") or ""),
            "uid": str(state.get("uid") or ""),
            "encrypt_boss_id": str(state.get("encrypt_boss_id") or ""),
            "recruiter_id": str(
                state.get("recruiter_id")
                or (conversation.recruiter_id if conversation else "")
                or ""
            ),
        }


def _action_payload(action: AutoReplyAction) -> dict[str, object]:
    return {
        "kind": action.kind,
        "message": action.message,
        "status_after_send": action.status_after_send,
        "send_attachment_resume": action.send_attachment_resume,
        "resume_file": action.resume_file,
        "blocked_reason": action.blocked_reason,
    }


def _message_payload(message: MessageRecord) -> dict[str, object]:
    return {
        "message_id": message.message_id,
        "conversation_id": message.conversation_id,
        "message_text": message.message_text,
        "direction": message.direction,
        "message_type": message.message_type,
        "job_id": message.job_id,
        "recruiter_id": message.recruiter_id,
        "source": message.source,
        "created_at": message.created_at,
    }


def _blocked_result(
    *,
    error_message: str,
    error_code: str = "",
    data: dict[str, Any] | None = None,
    recoverable: bool = False,
    recovery_action: str = "",
    hints: dict[str, Any] | None = None,
) -> ToolResult:
    if error_code and not recovery_action:
        recoverable, recovery_action = error_contract_for_code(
            error_code,
            fallback_recoverable=recoverable,
            fallback_recovery_action=None,
        )
    return ToolResult(
        ok=False,
        status="blocked_manual_required",
        data=dict(data or {}),
        error_code=error_code,
        error_message=error_message,
        recoverable=recoverable,
        recovery_action=str(recovery_action or ""),
        hints=dict(hints or {}),
    )


def _error_metadata(error: object) -> dict[str, Any]:
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
            str(code),
            fallback_recoverable=recoverable,
            fallback_recovery_action=None,
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


def _is_pdf_file(value: str) -> bool:
    path = Path(value).expanduser()
    return bool(value.strip()) and path.is_file() and path.suffix.lower() == ".pdf"
