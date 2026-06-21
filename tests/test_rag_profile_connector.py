from types import SimpleNamespace

import pytest

from boss_agent_cli.rag_reply.adapters.profile_rag_auth import ProfileRagAuthResolver
from boss_agent_cli.rag_reply.adapters.rag_profile import RagProfileConnector
from boss_agent_cli.rag_reply.profile_models import ProfileRagAuthBindingRecord


def test_ask_profile_requires_complete_identity():
	resolver = SimpleNamespace(
		resolve=lambda binding: SimpleNamespace(
			rag_adapter=SimpleNamespace(answer=lambda **kwargs: None),
			document_id="",
			category_id="",
			public_context={},
		)
	)
	connector = RagProfileConnector(rag_auth_resolver=resolver)

	result = connector.ask_profile(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="",
		knowledge_base_id="kb_ai",
		question="介绍一下项目。",
		conversation_id="conv_001",
	)

	assert result.ok is False
	assert result.audit_status == "profile_context_invalid"
	assert result.send_allowed is False


def test_ask_profile_wraps_current_chat_ask_without_metadata():
	captured = {}

	def fake_answer(**kwargs):
		captured.update(kwargs)
		return SimpleNamespace(
			ok=True,
			answer="我负责企业级 RAG 项目。",
			citations=[{"id": "c1"}],
			reasoning_summary={},
			raw_response={"answer": "我负责企业级 RAG 项目。"},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	resolver = SimpleNamespace(
		resolve=lambda binding: SimpleNamespace(
			rag_adapter=SimpleNamespace(answer=fake_answer),
			document_id="",
			category_id="",
			public_context={},
		)
	)
	connector = RagProfileConnector(rag_auth_resolver=resolver)
	result = connector.ask_profile(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		knowledge_base_id="kb_ai",
		question="介绍一下项目。",
		conversation_id="conv_001",
	)

	assert result.ok is True
	assert captured["rag_question"] == "介绍一下项目。"
	assert captured["session_id"].startswith("boss-profile-")
	assert "metadata" not in captured
	assert "tenant_id" not in captured
	assert "profile_id" not in captured
	assert result.profile_context["profile_id"] == "profile_ai"


def test_ask_profile_requires_conversation_id_before_resolving_auth():
	def fail_if_called(binding):
		raise AssertionError("RAG auth resolver should not be called for invalid profile context")

	connector = RagProfileConnector(rag_auth_resolver=SimpleNamespace(resolve=fail_if_called))

	result = connector.ask_profile(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		knowledge_base_id="kb_ai",
		question="介绍一下项目。",
		conversation_id=" ",
	)

	assert result.ok is False
	assert result.audit_status == "profile_context_invalid"
	assert result.send_allowed is False
	assert "conversation_id" in str(result.error_message)


def test_ask_profile_isolates_session_by_tenant_and_user():
	captured_sessions = []

	def fake_answer(**kwargs):
		captured_sessions.append(kwargs["session_id"])
		return SimpleNamespace(
			ok=True,
			answer="draft",
			citations=[],
			reasoning_summary=None,
			raw_response={},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	resolver = SimpleNamespace(
		resolve=lambda binding: SimpleNamespace(
			rag_adapter=SimpleNamespace(answer=fake_answer),
			document_id="",
			category_id="",
			public_context={},
		)
	)
	connector = RagProfileConnector(rag_auth_resolver=resolver)

	for tenant_id, user_id in [("tenant_001", "user_001"), ("tenant_002", "user_002")]:
		connector.ask_profile(
			tenant_id=tenant_id,
			user_id=user_id,
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
			question="介绍一下项目。",
			conversation_id="conv_001",
		)

	assert captured_sessions[0] != captured_sessions[1]


def test_ask_profile_returns_closed_result_when_rag_auth_is_invalid():
	connector = RagProfileConnector(
		rag_auth_resolver=SimpleNamespace(
			resolve=lambda binding: (_ for _ in ()).throw(ValueError("profile RAG credential is required."))
		)
	)

	result = connector.ask_profile(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		knowledge_base_id="kb_ai",
		question="介绍一下项目。",
		conversation_id="conv_001",
	)

	assert result.ok is False
	assert result.answer == ""
	assert result.audit_status == "rag_auth_invalid"
	assert result.send_allowed is False
	assert result.approval_required is True
	assert "credential" in str(result.error_message)


def test_profile_rag_auth_uses_profile_specific_bearer_without_leaking_secret():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode="bearer",
		credential_ref="RAG_PROFILE_AI_TOKEN",
	)
	resolver = ProfileRagAuthResolver(
		config={"RAG_PROFILE_AI_TOKEN": "secret-token"},
		default_base_url="http://127.0.0.1:8020",
		default_timeout_seconds=20,
		default_api_key="",
		default_auth_mode="none",
	)

	resolved = resolver.resolve(binding)

	assert resolved.rag_adapter._build_headers() == {"Authorization": "Bearer secret-token"}
	assert resolved.public_context["credential_ref"] == "RAG_PROFILE_AI_TOKEN"
	assert "secret-token" not in str(resolved.public_context)


def test_profile_rag_auth_normalizes_profile_specific_auth_mode():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode="Bearer",
		credential_ref="RAG_PROFILE_AI_TOKEN",
	)
	resolver = ProfileRagAuthResolver(
		config={"RAG_PROFILE_AI_TOKEN": "secret-token"},
		default_base_url="http://127.0.0.1:8020",
	)

	resolved = resolver.resolve(binding)

	assert resolved.rag_adapter._build_headers() == {"Authorization": "Bearer secret-token"}
	assert resolved.public_context["auth_mode"] == "bearer"


def test_profile_rag_auth_maps_category_scope_to_supported_chat_field():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type="category_id",
		scope_id="cat_ai",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	resolved = resolver.resolve(binding)

	assert resolved.category_id == "cat_ai"
	assert resolved.document_id == ""


def test_profile_rag_auth_inherits_default_global_auth():
	resolver = ProfileRagAuthResolver(
		config={},
		default_base_url="http://127.0.0.1:8020",
		default_api_key="shared-key",
		default_auth_mode="x_api_key",
	)

	resolved = resolver.resolve(None)

	assert resolved.rag_adapter._build_headers() == {"X-API-Key": "shared-key"}
	assert resolved.public_context["auth_mode"] == "inherit"


def test_profile_rag_auth_inherits_case_insensitive_default_auth_mode():
	resolver = ProfileRagAuthResolver(
		config={},
		default_base_url="http://127.0.0.1:8020",
		default_api_key="shared-key",
		default_auth_mode="Bearer",
	)

	resolved = resolver.resolve(None)

	assert resolved.rag_adapter._build_headers() == {"Authorization": "Bearer shared-key"}
	assert resolved.public_context["auth_mode"] == "inherit"


def test_profile_rag_auth_maps_document_scope_to_supported_chat_field():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type="document_id",
		scope_id="doc_ai",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	resolved = resolver.resolve(binding)

	assert resolved.document_id == "doc_ai"
	assert resolved.category_id == ""


def test_profile_rag_auth_rejects_unknown_scope_type():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type="collection_id",
		scope_id="cat_ai",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="scope_type"):
		resolver.resolve(binding)


def test_profile_rag_auth_allows_explicit_none_scope_without_scope_id():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type="none",
		scope_id="",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	resolved = resolver.resolve(binding)

	assert resolved.document_id == ""
	assert resolved.category_id == ""


def test_profile_rag_auth_rejects_explicit_blank_scope_type_without_scope_id():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type="",
		scope_id="",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="scope_type"):
		resolver.resolve(binding)


@pytest.mark.parametrize("scope_type", ["", "none"])
def test_profile_rag_auth_rejects_scope_id_without_scoped_type(scope_type):
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type=scope_type,
		scope_id="cat_ai",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="scope_type"):
		resolver.resolve(binding)


@pytest.mark.parametrize("scope_type", ["document_id", "category_id"])
def test_profile_rag_auth_requires_scope_id_for_scoped_binding(scope_type):
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		scope_type=scope_type,
		scope_id=" ",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="scope_id"):
		resolver.resolve(binding)


@pytest.mark.parametrize("auth_mode", ["x_api_key", "bearer"])
def test_profile_rag_auth_requires_profile_credential_for_profile_auth(auth_mode):
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode=auth_mode,
		credential_ref="MISSING_PROFILE_RAG_TOKEN",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="credential"):
		resolver.resolve(binding)


def test_profile_rag_auth_rejects_explicit_blank_auth_mode():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode="",
	)
	resolver = ProfileRagAuthResolver(config={}, default_base_url="http://127.0.0.1:8020")

	with pytest.raises(ValueError, match="auth_mode"):
		resolver.resolve(binding)


@pytest.mark.parametrize("auth_mode", ["inherit", "none"])
def test_profile_rag_auth_rejects_credential_ref_for_non_profile_auth(auth_mode):
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode=auth_mode,
		credential_ref="RAG_PROFILE_AI_TOKEN",
	)
	resolver = ProfileRagAuthResolver(
		config={"RAG_PROFILE_AI_TOKEN": "secret-token"},
		default_base_url="http://127.0.0.1:8020",
	)

	with pytest.raises(ValueError, match="credential_ref"):
		resolver.resolve(binding)


def test_profile_rag_auth_rejects_blank_profile_credential_value():
	binding = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		auth_mode="bearer",
		credential_ref="RAG_PROFILE_AI_TOKEN",
	)
	resolver = ProfileRagAuthResolver(
		config={"RAG_PROFILE_AI_TOKEN": " "},
		default_base_url="http://127.0.0.1:8020",
	)

	with pytest.raises(ValueError, match="credential"):
		resolver.resolve(binding)
