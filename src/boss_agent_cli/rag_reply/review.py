"""Review payload helpers for Boss RAG drafts."""

from __future__ import annotations

from boss_agent_cli.rag_reply.models import DraftRecord


def draft_to_payload(draft: DraftRecord) -> dict[str, object]:
	"""Convert a draft record into a CLI-safe payload."""
	return {
		"draft_id": draft.draft_id,
		"conversation_id": draft.conversation_id,
		"source_message_id": draft.source_message_id,
		"draft_text": draft.draft_text,
		"intent": draft.intent,
		"risk_labels": list(draft.risk_labels),
		"evidence": dict(draft.evidence),
		"approval_required": draft.approval_required,
		"send_allowed": draft.send_allowed,
		"audit_status": draft.audit_status,
		"rag_session_id": draft.rag_session_id,
		"created_at": draft.created_at,
		"updated_at": draft.updated_at,
	}

