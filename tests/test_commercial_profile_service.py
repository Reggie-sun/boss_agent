from pathlib import Path

import pytest

from boss_agent_cli.rag_reply.profile_models import (
	ConversationProfileBindingRecord,
	ProfileConfigRecord,
	ProfileRagAuthBindingRecord,
	ProfileUploadRecord,
	TenantRecord,
	UsageCounterRecord,
	UserProfileRecord,
	UserRecord,
)
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _service(tmp_path: Path) -> ProfileService:
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	return ProfileService(store)


def test_profile_service_round_trips_core_records(tmp_path: Path):
	service = _service(tmp_path)
	service.save_tenant(TenantRecord(tenant_id="tenant_001", display_name="Demo"))
	service.save_user(
		UserRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			display_name="Reggie",
			email="r@example.com",
		)
	)
	service.save_profile(
		UserProfileRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			display_name="AI 应用工程师",
			target_title="AI Application Engineer",
			knowledge_base_id="kb_ai",
		)
	)
	service.save_profile_config(
		ProfileConfigRecord(
			tenant_id="tenant_001",
			profile_id="profile_ai",
			contact_phone="13800138000",
			contact_wechat="reggie-ai",
			interview_windows="工作日 20:00 后",
			salary_reply_policy="薪资本人确认",
			resume_attachment_path="/tmp/resume.pdf",
			reply_auto_send_enabled=True,
		)
	)
	service.bind_conversation(
		ConversationProfileBindingRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			conversation_id="conv_001",
			profile_id="profile_ai",
			knowledge_base_id="kb_ai",
		)
	)
	service.save_profile_rag_auth_binding(
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

	assert service.get_tenant("tenant_001").display_name == "Demo"
	assert service.get_user("user_001").email == "r@example.com"
	assert service.list_profiles("tenant_001", "user_001")[0].profile_id == "profile_ai"
	profile_config = service.get_profile_config("profile_ai")
	assert profile_config.contact_wechat == "reggie-ai"
	assert profile_config.reply_auto_send_enabled is True
	assert profile_config.outreach_auto_send_enabled is False
	assert profile_config.proactive_resume_enabled is False
	assert service.get_conversation_binding("conv_001").knowledge_base_id == "kb_ai"
	rag_auth = service.get_profile_rag_auth_binding("profile_ai")
	assert rag_auth.auth_mode == "bearer"
	assert rag_auth.credential_ref == "RAG_PROFILE_AI_TOKEN"
	assert rag_auth.scope_type == "category_id"
	assert rag_auth.scope_id == "cat_ai"


def test_profile_service_tracks_uploads_and_usage(tmp_path: Path):
	service = _service(tmp_path)
	service.save_upload(
		ProfileUploadRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			upload_id="upload_001",
			source_filename="resume.pdf",
			source_type="resume",
			source_size_bytes=1200,
			rag_document_id="doc_001",
			status="indexed",
		)
	)
	service.save_usage_counter(
		UsageCounterRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			metric_name="rag_calls",
			period_start="2026-06-01",
			period_end="2026-07-01",
			used_count=3,
			limit_count=50,
		)
	)

	usage = service.increment_usage(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		metric_name="rag_calls",
		period_start="2026-06-01",
		period_end="2026-07-01",
	)

	assert service.list_uploads("profile_ai")[0].status == "indexed"
	assert usage.used_count == 4
	assert usage.limit_count == 50


def test_profile_service_increment_usage_creates_missing_counter(tmp_path: Path):
	service = _service(tmp_path)

	usage = service.increment_usage(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		metric_name="rag_calls",
		period_start="2026-06-01",
		period_end="2026-07-01",
	)

	assert usage.used_count == 1
	assert usage.limit_count == -1
	stored = service.get_usage_counter(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		metric_name="rag_calls",
		period_start="2026-06-01",
		period_end="2026-07-01",
	)
	assert stored.used_count == 1
	assert stored.limit_count == -1


def test_profile_service_rejects_non_positive_usage_increment(tmp_path: Path):
	service = _service(tmp_path)

	with pytest.raises(ValueError, match="amount"):
		service.increment_usage(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			metric_name="rag_calls",
			period_start="2026-06-01",
			period_end="2026-07-01",
			amount=0,
		)
