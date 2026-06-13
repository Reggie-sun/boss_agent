"""Domain models for the Boss RAG reply workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
	"""Return an ISO-8601 UTC timestamp."""
	return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
	"""Return a stable prefixed identifier."""
	return f"{prefix}_{uuid4().hex}"


@dataclass(slots=True)
class JobRecord:
	job_id: str
	security_id: str
	title: str
	company: str
	salary: str
	city: str
	summary: str
	detail: dict[str, Any] = field(default_factory=dict)
	source: str = "unknown"
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class RecruiterRecord:
	recruiter_id: str
	display_name: str
	company: str
	profile: dict[str, Any] = field(default_factory=dict)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ConversationRecord:
	conversation_id: str
	source: str
	job_id: str | None = None
	recruiter_id: str | None = None
	channel: str = "boss"
	last_message_at: str | None = None
	state: dict[str, Any] = field(default_factory=dict)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class MessageRecord:
	message_id: str
	conversation_id: str
	message_text: str
	direction: str
	message_type: str = "text"
	job_id: str | None = None
	recruiter_id: str | None = None
	source: str = "manual_import"
	raw: dict[str, Any] = field(default_factory=dict)
	import_batch_id: str | None = None
	created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class DraftRecord:
	draft_id: str
	conversation_id: str
	source_message_id: str
	draft_text: str
	intent: str
	risk_labels: list[str]
	evidence: dict[str, Any]
	approval_required: bool
	send_allowed: bool = False
	audit_status: str = "draft_created"
	rag_session_id: str | None = None
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)

	@classmethod
	def new(
		cls,
		*,
		conversation_id: str,
		source_message_id: str,
		draft_text: str,
		intent: str,
		risk_labels: list[str] | None = None,
		evidence: dict[str, Any] | None = None,
		approval_required: bool = True,
		send_allowed: bool = False,
		audit_status: str = "draft_created",
		rag_session_id: str | None = None,
	) -> "DraftRecord":
		now = utc_now_iso()
		return cls(
			draft_id=new_id("draft"),
			conversation_id=conversation_id,
			source_message_id=source_message_id,
			draft_text=draft_text,
			intent=intent,
			risk_labels=list(risk_labels or []),
			evidence=dict(evidence or {}),
			approval_required=approval_required,
			send_allowed=send_allowed,
			audit_status=audit_status,
			rag_session_id=rag_session_id,
			created_at=now,
			updated_at=now,
		)


@dataclass(slots=True)
class ApprovalEventRecord:
	event_id: str
	draft_id: str
	action: str
	notes: str | None = None
	copied_to_clipboard: bool = False
	created_at: str = field(default_factory=utc_now_iso)

	@classmethod
	def new(
		cls,
		*,
		draft_id: str,
		action: str,
		notes: str | None = None,
		copied_to_clipboard: bool = False,
	) -> "ApprovalEventRecord":
		return cls(
			event_id=new_id("approval"),
			draft_id=draft_id,
			action=action,
			notes=notes,
			copied_to_clipboard=copied_to_clipboard,
		)


@dataclass(slots=True)
class AuditLogRecord:
	log_id: str
	event_type: str
	entity_type: str
	entity_id: str
	payload: dict[str, Any]
	created_at: str = field(default_factory=utc_now_iso)

	@classmethod
	def new(
		cls,
		*,
		event_type: str,
		entity_type: str,
		entity_id: str,
		payload: dict[str, Any] | None = None,
	) -> "AuditLogRecord":
		return cls(
			log_id=new_id("audit"),
			event_type=event_type,
			entity_type=entity_type,
			entity_id=entity_id,
			payload=dict(payload or {}),
		)


@dataclass(slots=True)
class RagCallRecord:
	call_id: str
	conversation_id: str
	request: dict[str, Any]
	status: str
	draft_id: str | None = None
	response: dict[str, Any] | None = None
	created_at: str = field(default_factory=utc_now_iso)

	@classmethod
	def new(
		cls,
		*,
		conversation_id: str,
		request: dict[str, Any],
		status: str,
		draft_id: str | None = None,
		response: dict[str, Any] | None = None,
	) -> "RagCallRecord":
		return cls(
			call_id=new_id("ragcall"),
			draft_id=draft_id,
			conversation_id=conversation_id,
			request=dict(request),
			status=status,
			response=None if response is None else dict(response),
		)

