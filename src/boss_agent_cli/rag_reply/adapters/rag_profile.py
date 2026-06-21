"""Profile-aware wrapper around the current Enterprise RAG chat adapter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RagProfileAnswerResult:
	ok: bool
	answer: str
	citations: list[dict[str, object]] = field(default_factory=list)
	profile_context: dict[str, str] = field(default_factory=dict)
	reasoning_summary: dict[str, object] | None = None
	raw_response: dict[str, object] | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True


class RagProfileConnector:
	def __init__(self, *, rag_auth_resolver: Any) -> None:
		self.rag_auth_resolver = rag_auth_resolver

	def ask_profile(
		self,
		*,
		tenant_id: str,
		user_id: str,
		profile_id: str,
		knowledge_base_id: str,
		question: str,
		conversation_id: str,
		rag_auth_binding: Any = None,
		mode: str = "accurate",
	) -> RagProfileAnswerResult:
		profile_context = {
			"tenant_id": tenant_id.strip(),
			"user_id": user_id.strip(),
			"profile_id": profile_id.strip(),
			"knowledge_base_id": knowledge_base_id.strip(),
		}
		conversation_id = conversation_id.strip()
		if not all(profile_context.values()) or not conversation_id:
			return RagProfileAnswerResult(
				ok=False,
				answer="",
				citations=[],
				profile_context=profile_context,
				error_message="tenant_id/user_id/profile_id/knowledge_base_id/conversation_id are required.",
				audit_status="profile_context_invalid",
			)

		session_hash = hashlib.sha1(
			(
				f"{profile_context['tenant_id']}:{profile_context['user_id']}:"
				f"{conversation_id}:{profile_context['profile_id']}:{profile_context['knowledge_base_id']}"
			).encode("utf-8")
		).hexdigest()[:16]
		try:
			resolved = self.rag_auth_resolver.resolve(rag_auth_binding)
		except ValueError as exc:
			return RagProfileAnswerResult(
				ok=False,
				answer="",
				citations=[],
				profile_context=profile_context,
				error_message=str(exc),
				audit_status="rag_auth_invalid",
			)
		result = resolved.rag_adapter.answer(
			rag_question=question,
			session_id=f"boss-profile-{session_hash}",
			mode=mode,
			document_id=resolved.document_id or None,
			category_id=resolved.category_id or None,
		)
		return RagProfileAnswerResult(
			ok=bool(result.ok),
			answer=str(result.answer or ""),
			citations=list(result.citations or []),
			profile_context=profile_context,
			reasoning_summary=result.reasoning_summary,
			raw_response=result.raw_response,
			error_message=result.error_message,
			audit_status=result.audit_status,
			send_allowed=False,
			approval_required=True,
		)
