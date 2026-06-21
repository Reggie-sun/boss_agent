from pathlib import Path
from types import SimpleNamespace

from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.profile_models import (
	ConversationProfileBindingRecord,
	ProfileRagAuthBindingRecord,
)
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _store(tmp_path: Path) -> RagReplyStore:
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	return store


def test_fact_question_without_profile_binding_is_blocked(tmp_path: Path):
	store = _store(tmp_path)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))
		),
		profile_service=ProfileService(store),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "profile_binding_required"
	assert draft.send_allowed is False
	assert "profile_binding_required" in draft.risk_labels


def test_fact_question_uses_bound_profile_connector(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)
	captured = {}

	def fake_ask_profile(**kwargs):
		captured.update(kwargs)
		return SimpleNamespace(
			ok=True,
			answer="我负责企业级 RAG 项目。",
			citations=[{"id": "c1"}],
			profile_context={
				"tenant_id": kwargs["tenant_id"],
				"user_id": kwargs["user_id"],
				"profile_id": kwargs["profile_id"],
				"knowledge_base_id": kwargs["knowledge_base_id"],
			},
			reasoning_summary={},
			raw_response={},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(answer=lambda **kwargs: None),
		profile_service=profile_service,
		profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
	)

	draft = service.create_draft_for_message("msg_001")

	assert captured["profile_id"] == "profile_ai"
	assert captured["knowledge_base_id"] == "kb_ai"
	assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"
	assert store.list_rag_calls("conv_001")[0].request["profile_context"]["tenant_id"] == "tenant_001"


def test_bound_profile_passes_secret_free_rag_auth_context(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	profile_service.save_profile_rag_auth_binding(
		ProfileRagAuthBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			auth_mode="bearer",
			credential_ref="RAG_PROFILE_AI_TOKEN",
			scope_type="category_id",
			scope_id="cat_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)
	captured = {}

	def fake_ask_profile(**kwargs):
		captured.update(kwargs)
		return SimpleNamespace(
			ok=True,
			answer="我负责企业级 RAG 项目。",
			citations=[],
			profile_context={
				"tenant_id": "tenant_001",
				"user_id": "user_001",
				"profile_id": "profile_ai",
				"knowledge_base_id": "kb_ai",
			},
			reasoning_summary={},
			raw_response={},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(answer=lambda **kwargs: None),
		profile_service=profile_service,
		profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
	)

	draft = service.create_draft_for_message("msg_001")
	request = store.list_rag_calls("conv_001")[0].request

	assert captured["rag_auth_binding"].credential_ref == "RAG_PROFILE_AI_TOKEN"
	assert request["rag_auth"] == {
		"auth_mode": "bearer",
		"credential_ref": "RAG_PROFILE_AI_TOKEN",
		"scope_type": "category_id",
		"scope_id": "cat_ai",
	}
	assert "secret-token" not in str(request)
	assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"


def test_bound_profile_rag_auth_failure_is_closed_without_fallback(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	profile_service.save_profile_rag_auth_binding(
		ProfileRagAuthBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			auth_mode="bearer",
			credential_ref="RAG_PROFILE_AI_TOKEN",
			scope_type="category_id",
			scope_id="cat_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)

	def fake_ask_profile(**kwargs):
		return SimpleNamespace(
			ok=False,
			answer="",
			citations=[],
			profile_context={
				"tenant_id": kwargs["tenant_id"],
				"user_id": kwargs["user_id"],
				"profile_id": kwargs["profile_id"],
				"knowledge_base_id": kwargs["knowledge_base_id"],
			},
			reasoning_summary={},
			raw_response={},
			error_message="profile RAG credential 'RAG_PROFILE_AI_TOKEN' is not configured.",
			audit_status="rag_auth_invalid",
			send_allowed=False,
			approval_required=True,
		)

	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))
		),
		fallback_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("fallback should not be called"))
		),
		profile_service=profile_service,
		profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.draft_text == ""
	assert draft.audit_status == "rag_auth_invalid"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert "rag_auth_invalid" in draft.risk_labels
	assert draft.evidence["source"] == "profile_rag"
	assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"
	assert draft.evidence["rag_auth"] == {
		"auth_mode": "bearer",
		"credential_ref": "RAG_PROFILE_AI_TOKEN",
		"scope_type": "category_id",
		"scope_id": "cat_ai",
	}
	assert "RAG_PROFILE_AI_TOKEN" in draft.evidence["error_message"]
	assert "secret-token" not in str(draft.evidence)


def test_bound_profile_low_confidence_does_not_call_direct_agent(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)

	def fake_ask_profile(**kwargs):
		return SimpleNamespace(
			ok=True,
			answer="这是一段没有引用支撑的 profile RAG 回答。",
			citations=[],
			profile_context={
				"tenant_id": kwargs["tenant_id"],
				"user_id": kwargs["user_id"],
				"profile_id": kwargs["profile_id"],
				"knowledge_base_id": kwargs["knowledge_base_id"],
			},
			reasoning_summary={"confidence": "low"},
			raw_response={"answer": "low confidence"},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))
		),
		agent_answer_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("direct agent should not be called"))
		),
		profile_service=profile_service,
		profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.draft_text == ""
	assert draft.audit_status == "profile_rag_low_confidence"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert "profile_rag_low_confidence" in draft.risk_labels
	assert draft.evidence["source"] == "profile_rag"
	assert draft.evidence["reason"] == "profile_rag_low_confidence"
	assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"
	assert draft.evidence["rag_auth"] == {
		"auth_mode": "inherit",
		"credential_ref": "",
		"scope_type": "none",
		"scope_id": "",
	}
	assert draft.evidence["citations"] == []
	assert draft.evidence["reasoning_summary"] == {"confidence": "low"}


def test_bound_profile_explicit_low_confidence_metadata_is_closed(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)

	def fake_ask_profile(**kwargs):
		return SimpleNamespace(
			ok=True,
			answer="这是一段有引用但自报低置信的 profile RAG 回答。",
			citations=[{"id": "c1"}],
			profile_context={
				"tenant_id": kwargs["tenant_id"],
				"user_id": kwargs["user_id"],
				"profile_id": kwargs["profile_id"],
				"knowledge_base_id": kwargs["knowledge_base_id"],
			},
			reasoning_summary={"confidence": "low"},
			raw_response={"answer": "low confidence with citations"},
			error_message=None,
			audit_status="draft_created",
			send_allowed=False,
			approval_required=True,
		)

	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))
		),
		agent_answer_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("agent rewrite should not be called"))
		),
		profile_service=profile_service,
		profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.draft_text == ""
	assert draft.audit_status == "profile_rag_low_confidence"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert "profile_rag_low_confidence" in draft.risk_labels
	assert draft.evidence["source"] == "profile_rag"
	assert draft.evidence["reason"] == "profile_rag_low_confidence"
	assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"
	assert draft.evidence["citations"] == [{"id": "c1"}]
	assert draft.evidence["reasoning_summary"] == {"confidence": "low"}


def test_bound_profile_without_profile_connector_is_blocked(tmp_path: Path):
	store = _store(tmp_path)
	profile_service = ProfileService(store)
	profile_service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍一下你的 RAG 项目。",
			direction="inbound",
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))
		),
		profile_service=profile_service,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "profile_rag_connector_required"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert "profile_rag_connector_required" in draft.risk_labels
	assert draft.evidence == {"source": "profile_policy", "reason": "profile_rag_connector_required"}
	assert store.list_rag_calls("conv_001") == []
