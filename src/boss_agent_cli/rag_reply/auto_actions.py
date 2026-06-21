"""Automatic reply action decisions for Boss RAG drafts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from boss_agent_cli.rag_reply.models import DraftRecord
from boss_agent_cli.rag_reply.watcher_config import (
    WatcherConfig,
    WatcherConfigError,
    build_contact_reply,
    build_interview_window_reply,
    salary_handoff_reply,
    salary_preset_reply,
)


DRAFT_TEXT_REPLY_INTENTS = {
    "project_question",
    "resume_question",
    "technical_question",
    "general_question",
    "smalltalk",
    "resignation_status",
    "personal_status",
    "job_location_acceptance",
}


@dataclass(slots=True)
class AutoReplyAction:
    kind: str
    message: str = ""
    status_after_send: str = "sent"
    send_attachment_resume: bool = False
    resume_file: str = ""
    blocked_reason: str = ""
    attachment_required: bool = False
    profile_config_applied: bool = False
    profile_reply_auto_send_enabled: bool = True


def build_action_for_draft(
    draft: DraftRecord, config: WatcherConfig
) -> AutoReplyAction:
    intent = draft.intent
    draft_text = (draft.draft_text or "").strip()
    if intent in DRAFT_TEXT_REPLY_INTENTS:
        if not draft_text:
            return AutoReplyAction(
                kind="block", status_after_send="rag_failed", blocked_reason="empty_draft"
            )
        return AutoReplyAction(kind="send_text", message=draft_text)
    if intent == "resume_share_request":
        resume_file = _require_resume_file(config.resume_attachment_path)
        message = draft_text or "可以的，我这边通过 BOSS 直聘发送附件简历给您。"
        return AutoReplyAction(
            kind="send_text",
            message=message,
            send_attachment_resume=True,
            resume_file=resume_file,
            attachment_required=True,
        )
    if intent in {"interview_time", "availability_or_schedule"}:
        return AutoReplyAction(
            kind="send_text", message=build_interview_window_reply(config)
        )
    if intent == "contact_exchange":
        return AutoReplyAction(kind="send_text", message=build_contact_reply(config))
    if intent == "salary_or_offer":
        preset = salary_preset_reply(config.salary_reply_policy)
        if preset == salary_handoff_reply():
            raise WatcherConfigError(
                "boss_rag_salary_reply is required for automatic salary replies."
            )
        if draft_text and draft_text != salary_handoff_reply():
            return AutoReplyAction(kind="send_text", message=draft_text)
        return AutoReplyAction(kind="send_text", message=preset)
    return AutoReplyAction(
        kind="block",
        status_after_send="blocked_manual_required",
        blocked_reason="intent_not_allowlisted",
    )


def _require_resume_file(value: str) -> str:
    return require_resume_file(value)


def require_resume_file(value: str) -> str:
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
