"""SQLite schema for the Boss RAG reply workflow."""

from __future__ import annotations

SCHEMA_VERSION = 1

CREATE_TABLE_STATEMENTS = (
	"""
	CREATE TABLE IF NOT EXISTS jobs (
		job_id TEXT PRIMARY KEY,
		security_id TEXT,
		title TEXT,
		company TEXT,
		salary TEXT,
		city TEXT,
		summary TEXT,
		detail_json TEXT NOT NULL,
		source TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS recruiters (
		recruiter_id TEXT PRIMARY KEY,
		display_name TEXT NOT NULL,
		company TEXT NOT NULL,
		profile_json TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS conversations (
		conversation_id TEXT PRIMARY KEY,
		source TEXT NOT NULL,
		job_id TEXT,
		recruiter_id TEXT,
		channel TEXT NOT NULL,
		last_message_at TEXT,
		state_json TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS messages (
		message_id TEXT PRIMARY KEY,
		conversation_id TEXT NOT NULL,
		job_id TEXT,
		recruiter_id TEXT,
		direction TEXT NOT NULL,
		message_text TEXT NOT NULL,
		message_type TEXT NOT NULL,
		source TEXT NOT NULL,
		raw_json TEXT NOT NULL,
		import_batch_id TEXT,
		created_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS drafts (
		draft_id TEXT PRIMARY KEY,
		conversation_id TEXT NOT NULL,
		source_message_id TEXT NOT NULL,
		draft_text TEXT NOT NULL,
		intent TEXT NOT NULL,
		risk_labels_json TEXT NOT NULL,
		evidence_json TEXT NOT NULL,
		approval_required INTEGER NOT NULL,
		send_allowed INTEGER NOT NULL,
		audit_status TEXT NOT NULL,
		rag_session_id TEXT,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS approval_events (
		event_id TEXT PRIMARY KEY,
		draft_id TEXT NOT NULL,
		action TEXT NOT NULL,
		notes TEXT,
		copied_to_clipboard INTEGER NOT NULL,
		created_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS audit_logs (
		log_id TEXT PRIMARY KEY,
		event_type TEXT NOT NULL,
		entity_type TEXT NOT NULL,
		entity_id TEXT NOT NULL,
		payload_json TEXT NOT NULL,
		created_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS rag_calls (
		call_id TEXT PRIMARY KEY,
		draft_id TEXT,
		conversation_id TEXT NOT NULL,
		request_json TEXT NOT NULL,
		response_json TEXT,
		status TEXT NOT NULL,
		created_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS tenants (
		tenant_id TEXT PRIMARY KEY,
		display_name TEXT NOT NULL,
		plan_code TEXT NOT NULL,
		subscription_status TEXT NOT NULL,
		license_key_hash TEXT NOT NULL,
		payment_provider TEXT NOT NULL,
		provider_customer_id TEXT NOT NULL,
		provider_subscription_id TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS users (
		user_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		display_name TEXT NOT NULL,
		email TEXT NOT NULL,
		role TEXT NOT NULL,
		status TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS user_profiles (
		profile_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		user_id TEXT NOT NULL,
		display_name TEXT NOT NULL,
		target_title TEXT NOT NULL,
		knowledge_base_id TEXT NOT NULL,
		status TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS profile_configs (
		profile_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		contact_phone TEXT NOT NULL,
		contact_wechat TEXT NOT NULL,
		interview_windows TEXT NOT NULL,
		salary_reply_policy TEXT NOT NULL,
		resume_attachment_path TEXT NOT NULL,
		reply_auto_send_enabled INTEGER NOT NULL,
		outreach_auto_send_enabled INTEGER NOT NULL,
		proactive_resume_enabled INTEGER NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS profile_uploads (
		upload_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		user_id TEXT NOT NULL,
		profile_id TEXT NOT NULL,
		source_filename TEXT NOT NULL,
		source_type TEXT NOT NULL,
		source_size_bytes INTEGER NOT NULL,
		rag_document_id TEXT NOT NULL,
		status TEXT NOT NULL,
		error_message TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS conversation_profile_bindings (
		conversation_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		user_id TEXT NOT NULL,
		profile_id TEXT NOT NULL,
		knowledge_base_id TEXT NOT NULL,
		binding_source TEXT NOT NULL,
		created_at TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS profile_rag_auth_bindings (
		profile_id TEXT PRIMARY KEY,
		tenant_id TEXT NOT NULL,
		user_id TEXT NOT NULL,
		auth_mode TEXT NOT NULL,
		credential_ref TEXT NOT NULL,
		scope_type TEXT NOT NULL,
		scope_id TEXT NOT NULL,
		updated_at TEXT NOT NULL
	)
	""",
	"""
	CREATE TABLE IF NOT EXISTS usage_counters (
		tenant_id TEXT NOT NULL,
		user_id TEXT NOT NULL,
		profile_id TEXT NOT NULL,
		metric_name TEXT NOT NULL,
		period_start TEXT NOT NULL,
		period_end TEXT NOT NULL,
		used_count INTEGER NOT NULL,
		limit_count INTEGER NOT NULL,
		updated_at TEXT NOT NULL,
		PRIMARY KEY (
			tenant_id,
			user_id,
			profile_id,
			metric_name,
			period_start,
			period_end
		)
	)
	""",
)
