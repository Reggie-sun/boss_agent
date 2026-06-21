"""Commercial profile domain models for Boss Agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from boss_agent_cli.rag_reply.models import new_id, utc_now_iso


PLAN_CODES = {"free", "pro", "team", "enterprise"}
SUBSCRIPTION_STATUSES = {"trial", "active", "past_due", "suspended", "canceled"}
PROFILE_STATUSES = {"active", "archived"}
UPLOAD_STATUSES = {"queued", "uploaded", "indexed", "failed"}
BINDING_SOURCES = {"manual", "default", "imported"}
RAG_AUTH_MODES = {"inherit", "none", "x_api_key", "bearer"}
RAG_SCOPE_TYPES = {"none", "document_id", "category_id"}

METRIC_PROFILE_COUNT = "profile_count"
METRIC_UPLOAD_COUNT = "profile_upload_count"
METRIC_UPLOAD_BYTES = "profile_upload_bytes"
METRIC_RAG_CALLS = "rag_calls"
METRIC_REPLY_AUTO_SEND = "reply_auto_send"
METRIC_OUTREACH_AUTO_GREET = "outreach_auto_greet"
METRIC_ATTACHMENT_RESUME_SEND = "attachment_resume_send"


@dataclass(slots=True)
class TenantRecord:
	tenant_id: str
	display_name: str
	plan_code: str = "free"
	subscription_status: str = "trial"
	license_key_hash: str = ""
	payment_provider: str = ""
	provider_customer_id: str = ""
	provider_subscription_id: str = ""
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UserRecord:
	tenant_id: str
	user_id: str
	display_name: str
	email: str
	role: str = "owner"
	status: str = "active"
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UserProfileRecord:
	tenant_id: str
	user_id: str
	profile_id: str
	display_name: str
	target_title: str
	knowledge_base_id: str = ""
	status: str = "active"
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)

	@classmethod
	def new(
		cls,
		*,
		tenant_id: str,
		user_id: str,
		display_name: str,
		target_title: str,
		knowledge_base_id: str = "",
	) -> "UserProfileRecord":
		return cls(
			tenant_id=tenant_id,
			user_id=user_id,
			profile_id=new_id("profile"),
			display_name=display_name,
			target_title=target_title,
			knowledge_base_id=knowledge_base_id,
		)


@dataclass(slots=True)
class ProfileConfigRecord:
	tenant_id: str
	profile_id: str
	contact_phone: str = ""
	contact_wechat: str = ""
	interview_windows: str = ""
	salary_reply_policy: str = ""
	resume_attachment_path: str = ""
	reply_auto_send_enabled: bool = False
	outreach_auto_send_enabled: bool = False
	proactive_resume_enabled: bool = False
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ProfileUploadRecord:
	tenant_id: str
	user_id: str
	profile_id: str
	upload_id: str
	source_filename: str
	source_type: str
	source_size_bytes: int = 0
	rag_document_id: str = ""
	status: str = "queued"
	error_message: str = ""
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ConversationProfileBindingRecord:
	tenant_id: str
	conversation_id: str
	user_id: str
	profile_id: str
	knowledge_base_id: str
	binding_source: str = "manual"
	created_at: str = field(default_factory=utc_now_iso)
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ProfileRagAuthBindingRecord:
	tenant_id: str
	user_id: str
	profile_id: str
	auth_mode: str = "inherit"
	credential_ref: str = ""
	scope_type: str = "none"
	scope_id: str = ""
	updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UsageCounterRecord:
	tenant_id: str
	user_id: str
	profile_id: str
	metric_name: str
	period_start: str
	period_end: str
	used_count: int = 0
	limit_count: int = -1
	updated_at: str = field(default_factory=utc_now_iso)
