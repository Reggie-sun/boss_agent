"""Resolve profile-specific Enterprise RAG auth without exposing secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping

from boss_agent_cli.rag_reply.adapters.rag_http import RagHttpAdapter
from boss_agent_cli.rag_reply.profile_models import ProfileRagAuthBindingRecord, RAG_AUTH_MODES, RAG_SCOPE_TYPES


@dataclass(slots=True)
class ResolvedProfileRagAuth:
	rag_adapter: RagHttpAdapter
	document_id: str = ""
	category_id: str = ""
	public_context: dict[str, str] = field(default_factory=dict)


class ProfileRagAuthResolver:
	def __init__(
		self,
		*,
		config: Mapping[str, Any],
		default_base_url: str | None,
		default_timeout_seconds: int = 20,
		default_api_key: str | None = None,
		default_auth_mode: str = "none",
	) -> None:
		self.config = config
		self.default_base_url = default_base_url
		self.default_timeout_seconds = default_timeout_seconds
		self.default_api_key = default_api_key
		self.default_auth_mode = default_auth_mode

	def resolve(self, binding: ProfileRagAuthBindingRecord | None) -> ResolvedProfileRagAuth:
		raw_auth_mode = getattr(binding, "auth_mode", "inherit") if binding else "inherit"
		raw_scope_type = getattr(binding, "scope_type", "none") if binding else "none"
		if binding is not None and not _clean(raw_auth_mode):
			raise ValueError("profile RAG auth_mode must be explicitly set.")
		if binding is not None and not _clean(raw_scope_type):
			raise ValueError("profile RAG scope_type must be explicitly set.")

		auth_mode = (_clean(raw_auth_mode) or "inherit").lower()
		credential_ref = _clean(getattr(binding, "credential_ref", "") if binding else "")
		scope_type = (_clean(raw_scope_type) or "none").lower()
		scope_id = _clean(getattr(binding, "scope_id", "") if binding else "")
		self._validate_profile_binding(auth_mode=auth_mode, credential_ref=credential_ref, scope_type=scope_type, scope_id=scope_id)

		adapter_auth_mode = auth_mode
		api_key = ""
		if auth_mode == "inherit":
			adapter_auth_mode = (_clean(self.default_auth_mode) or "none").lower()
			api_key = _clean(self.default_api_key)
		elif auth_mode in {"x_api_key", "bearer"}:
			api_key = self._resolve_credential(credential_ref)
		elif auth_mode == "none":
			adapter_auth_mode = "none"
		if adapter_auth_mode not in {"none", "x_api_key", "bearer"}:
			raise ValueError("profile RAG auth_mode must resolve to one of: none, x_api_key, bearer.")

		return ResolvedProfileRagAuth(
			rag_adapter=RagHttpAdapter(
				base_url=self.default_base_url,
				timeout_seconds=self.default_timeout_seconds,
				api_key=api_key,
				auth_mode=adapter_auth_mode,
			),
			document_id=scope_id if scope_type == "document_id" else "",
			category_id=scope_id if scope_type == "category_id" else "",
			public_context={
				"auth_mode": auth_mode,
				"credential_ref": credential_ref,
				"scope_type": scope_type,
				"scope_id": scope_id,
			},
		)

	def _resolve_credential(self, credential_ref: str) -> str:
		config_value = self.config.get(credential_ref)
		if config_value not in (None, ""):
			credential = _clean(config_value)
			if credential:
				return credential
			raise ValueError(f"profile RAG credential {credential_ref!r} is not configured.")
		credential = _clean(os.getenv(credential_ref))
		if not credential:
			raise ValueError(f"profile RAG credential {credential_ref!r} is not configured.")
		return credential

	def _validate_profile_binding(self, *, auth_mode: str, credential_ref: str, scope_type: str, scope_id: str) -> None:
		if auth_mode not in RAG_AUTH_MODES:
			raise ValueError(f"profile RAG auth_mode must be one of: {', '.join(sorted(RAG_AUTH_MODES))}.")
		if credential_ref and auth_mode not in {"x_api_key", "bearer"}:
			raise ValueError("profile RAG credential_ref is only valid with x_api_key or bearer auth_mode.")
		if auth_mode in {"x_api_key", "bearer"} and not credential_ref:
			raise ValueError("profile RAG credential_ref is required for profile-specific auth.")
		if scope_type not in RAG_SCOPE_TYPES:
			raise ValueError(f"profile RAG scope_type must be one of: {', '.join(sorted(RAG_SCOPE_TYPES))}.")
		if scope_type == "none" and scope_id:
			raise ValueError("profile RAG scope_type must be document_id or category_id when scope_id is configured.")
		if scope_type in {"document_id", "category_id"} and not scope_id:
			raise ValueError("profile RAG scope_id is required for document_id/category_id scope.")


def _clean(value: object) -> str:
	return str(value or "").strip()
