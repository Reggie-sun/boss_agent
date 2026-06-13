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
)

