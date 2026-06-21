from pathlib import Path

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
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_commercial_profile_tables_are_created(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()

	assert {
		"tenants",
		"users",
		"user_profiles",
		"profile_configs",
		"profile_uploads",
		"conversation_profile_bindings",
		"profile_rag_auth_bindings",
		"usage_counters",
	}.issubset(set(store.list_tables()))


def test_profile_model_defaults_are_safe():
	tenant = TenantRecord(tenant_id="tenant_001", display_name="Demo Tenant")
	user = UserRecord(tenant_id="tenant_001", user_id="user_001", display_name="Reggie", email="r@example.com")
	profile = UserProfileRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		display_name="AI 应用工程师",
		target_title="AI Application Engineer",
	)
	config = ProfileConfigRecord(tenant_id="tenant_001", profile_id="profile_ai")
	upload = ProfileUploadRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		upload_id="upload_001",
		source_filename="resume.pdf",
		source_type="resume",
	)
	binding = ConversationProfileBindingRecord(
		tenant_id="tenant_001",
		conversation_id="conv_001",
		user_id="user_001",
		profile_id="profile_ai",
		knowledge_base_id="kb_ai",
	)
	rag_auth = ProfileRagAuthBindingRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
	)
	usage = UsageCounterRecord(
		tenant_id="tenant_001",
		user_id="user_001",
		profile_id="profile_ai",
		metric_name="rag_calls",
		period_start="2026-06-01",
		period_end="2026-07-01",
	)

	assert tenant.plan_code == "free"
	assert tenant.subscription_status == "trial"
	assert user.role == "owner"
	assert profile.status == "active"
	assert config.reply_auto_send_enabled is False
	assert config.outreach_auto_send_enabled is False
	assert config.proactive_resume_enabled is False
	assert upload.status == "queued"
	assert binding.binding_source == "manual"
	assert rag_auth.auth_mode == "inherit"
	assert rag_auth.scope_type == "none"
	assert usage.used_count == 0
	assert usage.limit_count == -1


def test_profile_new_generates_personal_knowledge_base_id():
	profile = UserProfileRecord.new(
		tenant_id="tenant_001",
		user_id="user_001",
		display_name="AI 应用工程师",
		target_title="AI Application Engineer",
	)

	assert profile.profile_id.startswith("profile_")
	assert profile.knowledge_base_id == f"kb_{profile.profile_id}"


def test_conversation_binding_generates_personal_knowledge_base_id():
	binding = ConversationProfileBindingRecord(
		tenant_id="tenant_001",
		conversation_id="conv_001",
		user_id="user_001",
		profile_id="profile_ai",
		knowledge_base_id="",
	)

	assert binding.knowledge_base_id == "kb_profile_ai"
