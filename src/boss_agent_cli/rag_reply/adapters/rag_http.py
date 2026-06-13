"""HTTP adapter for the external Enterprise RAG service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(slots=True)
class RagAnswerResult:
	ok: bool
	answer: str
	citations: list[dict[str, Any]] = field(default_factory=list)
	reasoning_summary: dict[str, Any] | None = None
	raw_response: dict[str, Any] | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True


class RagHttpAdapter:
	"""Call the Enterprise RAG `POST /api/v1/chat/ask` endpoint."""

	def __init__(
		self,
		*,
		base_url: str | None,
		timeout_seconds: int = 20,
		api_key: str | None = None,
		auth_mode: str = "none",
	) -> None:
		self.base_url = (base_url or "").rstrip("/")
		self.timeout_seconds = timeout_seconds
		self.api_key = (api_key or "").strip()
		self.auth_mode = (auth_mode or "none").strip().lower()

	def answer(
		self,
		*,
		rag_question: str,
		session_id: str,
		mode: str = "accurate",
	) -> RagAnswerResult:
		"""Return a closed result when the HTTP call fails."""
		if not self.base_url:
			return RagAnswerResult(
				ok=False,
				answer="",
				error_message="boss_rag_rag_base_url is not configured.",
				audit_status="rag_failed",
			)
		payload = {
			"question": rag_question,
			"session_id": session_id,
			"mode": mode,
		}
		try:
			headers = self._build_headers()
		except ValueError as exc:
			return RagAnswerResult(
				ok=False,
				answer="",
				error_message=str(exc),
				audit_status="rag_failed",
			)
		try:
			response = httpx.post(
				f"{self.base_url}/api/v1/chat/ask",
				json=payload,
				timeout=self.timeout_seconds,
				headers=headers,
			)
			response.raise_for_status()
			data = response.json()
		except (httpx.HTTPError, ValueError) as exc:
			return RagAnswerResult(
				ok=False,
				answer="",
				error_message=str(exc),
				audit_status="rag_failed",
			)
		return RagAnswerResult(
			ok=True,
			answer=str(data.get("answer") or ""),
			citations=list(data.get("citations") or []),
			reasoning_summary=data.get("reasoning_summary")
			if isinstance(data.get("reasoning_summary"), dict)
			else None,
			raw_response=data if isinstance(data, dict) else None,
		)

	def _build_headers(self) -> dict[str, str] | None:
		if self.auth_mode in {"", "none"}:
			return None
		if not self.api_key:
			raise ValueError("boss_rag_rag_api_key is required when boss_rag_rag_auth_mode is enabled.")
		if self.auth_mode == "x_api_key":
			return {"X-API-Key": self.api_key}
		if self.auth_mode == "bearer":
			return {"Authorization": f"Bearer {self.api_key}"}
		raise ValueError(
			f"Unknown boss_rag_rag_auth_mode={self.auth_mode!r}. Use one of: none, x_api_key, bearer."
		)
