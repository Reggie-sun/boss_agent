"""SQLite persistence service for commercial profile records."""

from __future__ import annotations

import sqlite3

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


class ConversationBindingScopeError(ValueError):
	"""Raised when an existing conversation binding belongs to another tenant/user."""

	def __init__(self, existing: ConversationProfileBindingRecord) -> None:
		self.existing = existing
		super().__init__(
			f"conversation_id={existing.conversation_id} is already bound to another tenant/user scope."
		)


class ProfileService:
	"""Persist commercial profile state in the Boss RAG SQLite store."""

	def __init__(self, store: RagReplyStore) -> None:
		self.store = store

	def save_tenant(self, record: TenantRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO tenants (
					tenant_id, display_name, plan_code, subscription_status,
					license_key_hash, payment_provider, provider_customer_id,
					provider_subscription_id, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.tenant_id,
					record.display_name,
					record.plan_code,
					record.subscription_status,
					record.license_key_hash,
					record.payment_provider,
					record.provider_customer_id,
					record.provider_subscription_id,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def get_tenant(self, tenant_id: str) -> TenantRecord | None:
		with self.store.connect() as conn:
			row = conn.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
		return None if row is None else self._row_to_tenant(row)

	def save_user(self, record: UserRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO users (
					user_id, tenant_id, display_name, email, role, status, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.user_id,
					record.tenant_id,
					record.display_name,
					record.email,
					record.role,
					record.status,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def get_user(self, user_id: str) -> UserRecord | None:
		with self.store.connect() as conn:
			row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
		return None if row is None else self._row_to_user(row)

	def save_profile(self, record: UserProfileRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO user_profiles (
					profile_id, tenant_id, user_id, display_name, target_title,
					knowledge_base_id, status, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.profile_id,
					record.tenant_id,
					record.user_id,
					record.display_name,
					record.target_title,
					record.knowledge_base_id,
					record.status,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def get_profile(self, profile_id: str) -> UserProfileRecord | None:
		with self.store.connect() as conn:
			row = conn.execute(
				"SELECT * FROM user_profiles WHERE profile_id = ?",
				(profile_id,),
			).fetchone()
		return None if row is None else self._row_to_profile(row)

	def list_profiles(self, tenant_id: str, user_id: str) -> list[UserProfileRecord]:
		with self.store.connect() as conn:
			rows = conn.execute(
				"""
				SELECT * FROM user_profiles
				WHERE tenant_id = ? AND user_id = ?
				ORDER BY created_at, profile_id
				""",
				(tenant_id, user_id),
			).fetchall()
		return [self._row_to_profile(row) for row in rows]

	def save_profile_config(self, record: ProfileConfigRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO profile_configs (
					profile_id, tenant_id, contact_phone, contact_wechat,
					interview_windows, salary_reply_policy, resume_attachment_path,
					reply_auto_send_enabled, outreach_auto_send_enabled,
					proactive_resume_enabled, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.profile_id,
					record.tenant_id,
					record.contact_phone,
					record.contact_wechat,
					record.interview_windows,
					record.salary_reply_policy,
					record.resume_attachment_path,
					int(record.reply_auto_send_enabled),
					int(record.outreach_auto_send_enabled),
					int(record.proactive_resume_enabled),
					record.updated_at,
				),
			)
			conn.commit()

	def get_profile_config(self, profile_id: str) -> ProfileConfigRecord | None:
		with self.store.connect() as conn:
			row = conn.execute(
				"SELECT * FROM profile_configs WHERE profile_id = ?",
				(profile_id,),
			).fetchone()
		return None if row is None else self._row_to_profile_config(row)

	def save_upload(self, record: ProfileUploadRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO profile_uploads (
					upload_id, tenant_id, user_id, profile_id, source_filename,
					source_type, source_size_bytes, rag_document_id, status,
					error_message, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.upload_id,
					record.tenant_id,
					record.user_id,
					record.profile_id,
					record.source_filename,
					record.source_type,
					record.source_size_bytes,
					record.rag_document_id,
					record.status,
					record.error_message,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def list_uploads(self, profile_id: str) -> list[ProfileUploadRecord]:
		with self.store.connect() as conn:
			rows = conn.execute(
				"""
				SELECT * FROM profile_uploads
				WHERE profile_id = ?
				ORDER BY created_at, upload_id
				""",
				(profile_id,),
			).fetchall()
		return [self._row_to_upload(row) for row in rows]

	def bind_conversation(self, record: ConversationProfileBindingRecord) -> None:
		with self.store.connect() as conn:
			conn.execute("BEGIN IMMEDIATE")
			existing_row = conn.execute(
				"SELECT * FROM conversation_profile_bindings WHERE conversation_id = ?",
				(record.conversation_id,),
			).fetchone()
			if existing_row is not None:
				existing = self._row_to_conversation_binding(existing_row)
				if existing.tenant_id != record.tenant_id or existing.user_id != record.user_id:
					raise ConversationBindingScopeError(existing)
			conn.execute(
				"""
				INSERT OR REPLACE INTO conversation_profile_bindings (
					conversation_id, tenant_id, user_id, profile_id, knowledge_base_id,
					binding_source, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.conversation_id,
					record.tenant_id,
					record.user_id,
					record.profile_id,
					record.knowledge_base_id,
					record.binding_source,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def get_conversation_binding(self, conversation_id: str) -> ConversationProfileBindingRecord | None:
		with self.store.connect() as conn:
			row = conn.execute(
				"SELECT * FROM conversation_profile_bindings WHERE conversation_id = ?",
				(conversation_id,),
			).fetchone()
		return None if row is None else self._row_to_conversation_binding(row)

	def save_profile_rag_auth_binding(self, record: ProfileRagAuthBindingRecord) -> None:
		with self.store.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO profile_rag_auth_bindings (
					profile_id, tenant_id, user_id, auth_mode, credential_ref,
					scope_type, scope_id, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.profile_id,
					record.tenant_id,
					record.user_id,
					record.auth_mode,
					record.credential_ref,
					record.scope_type,
					record.scope_id,
					record.updated_at,
				),
			)
			conn.commit()

	def get_profile_rag_auth_binding(self, profile_id: str) -> ProfileRagAuthBindingRecord | None:
		with self.store.connect() as conn:
			row = conn.execute(
				"SELECT * FROM profile_rag_auth_bindings WHERE profile_id = ?",
				(profile_id,),
			).fetchone()
		return None if row is None else self._row_to_profile_rag_auth_binding(row)

	def save_usage_counter(self, record: UsageCounterRecord) -> None:
		with self.store.connect() as conn:
			self._insert_usage_counter(conn, record)
			conn.commit()

	def get_usage_counter(
		self,
		tenant_id: str,
		user_id: str,
		profile_id: str,
		metric_name: str,
		period_start: str,
		period_end: str,
	) -> UsageCounterRecord | None:
		with self.store.connect() as conn:
			row = conn.execute(
				"""
				SELECT * FROM usage_counters
				WHERE tenant_id = ?
					AND user_id = ?
					AND profile_id = ?
					AND metric_name = ?
					AND period_start = ?
					AND period_end = ?
				""",
				(tenant_id, user_id, profile_id, metric_name, period_start, period_end),
			).fetchone()
		return None if row is None else self._row_to_usage_counter(row)

	def increment_usage(
		self,
		*,
		tenant_id: str,
		user_id: str,
		profile_id: str,
		metric_name: str,
		period_start: str,
		period_end: str,
		amount: int = 1,
	) -> UsageCounterRecord:
		if amount <= 0:
			raise ValueError("amount must be positive")
		with self.store.connect() as conn:
			conn.execute("BEGIN IMMEDIATE")
			row = conn.execute(
				"""
				SELECT * FROM usage_counters
				WHERE tenant_id = ?
					AND user_id = ?
					AND profile_id = ?
					AND metric_name = ?
					AND period_start = ?
					AND period_end = ?
				""",
				(tenant_id, user_id, profile_id, metric_name, period_start, period_end),
			).fetchone()
			updated = UsageCounterRecord(
				tenant_id=tenant_id,
				user_id=user_id,
				profile_id=profile_id,
				metric_name=metric_name,
				period_start=period_start,
				period_end=period_end,
				used_count=(int(row["used_count"]) if row is not None else 0) + amount,
				limit_count=int(row["limit_count"]) if row is not None else -1,
			)
			self._insert_usage_counter(conn, updated)
			conn.commit()
		return updated

	def _row_to_tenant(self, row: sqlite3.Row) -> TenantRecord:
		return TenantRecord(
			tenant_id=str(row["tenant_id"]),
			display_name=str(row["display_name"]),
			plan_code=str(row["plan_code"]),
			subscription_status=str(row["subscription_status"]),
			license_key_hash=str(row["license_key_hash"]),
			payment_provider=str(row["payment_provider"]),
			provider_customer_id=str(row["provider_customer_id"]),
			provider_subscription_id=str(row["provider_subscription_id"]),
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_user(self, row: sqlite3.Row) -> UserRecord:
		return UserRecord(
			tenant_id=str(row["tenant_id"]),
			user_id=str(row["user_id"]),
			display_name=str(row["display_name"]),
			email=str(row["email"]),
			role=str(row["role"]),
			status=str(row["status"]),
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_profile(self, row: sqlite3.Row) -> UserProfileRecord:
		return UserProfileRecord(
			tenant_id=str(row["tenant_id"]),
			user_id=str(row["user_id"]),
			profile_id=str(row["profile_id"]),
			display_name=str(row["display_name"]),
			target_title=str(row["target_title"]),
			knowledge_base_id=str(row["knowledge_base_id"]),
			status=str(row["status"]),
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_profile_config(self, row: sqlite3.Row) -> ProfileConfigRecord:
		return ProfileConfigRecord(
			tenant_id=str(row["tenant_id"]),
			profile_id=str(row["profile_id"]),
			contact_phone=str(row["contact_phone"]),
			contact_wechat=str(row["contact_wechat"]),
			interview_windows=str(row["interview_windows"]),
			salary_reply_policy=str(row["salary_reply_policy"]),
			resume_attachment_path=str(row["resume_attachment_path"]),
			reply_auto_send_enabled=self._bool_from_sqlite(row["reply_auto_send_enabled"]),
			outreach_auto_send_enabled=self._bool_from_sqlite(row["outreach_auto_send_enabled"]),
			proactive_resume_enabled=self._bool_from_sqlite(row["proactive_resume_enabled"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_upload(self, row: sqlite3.Row) -> ProfileUploadRecord:
		return ProfileUploadRecord(
			tenant_id=str(row["tenant_id"]),
			user_id=str(row["user_id"]),
			profile_id=str(row["profile_id"]),
			upload_id=str(row["upload_id"]),
			source_filename=str(row["source_filename"]),
			source_type=str(row["source_type"]),
			source_size_bytes=int(row["source_size_bytes"]),
			rag_document_id=str(row["rag_document_id"]),
			status=str(row["status"]),
			error_message=str(row["error_message"]),
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_conversation_binding(self, row: sqlite3.Row) -> ConversationProfileBindingRecord:
		return ConversationProfileBindingRecord(
			tenant_id=str(row["tenant_id"]),
			conversation_id=str(row["conversation_id"]),
			user_id=str(row["user_id"]),
			profile_id=str(row["profile_id"]),
			knowledge_base_id=str(row["knowledge_base_id"]),
			binding_source=str(row["binding_source"]),
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_profile_rag_auth_binding(self, row: sqlite3.Row) -> ProfileRagAuthBindingRecord:
		return ProfileRagAuthBindingRecord(
			tenant_id=str(row["tenant_id"]),
			user_id=str(row["user_id"]),
			profile_id=str(row["profile_id"]),
			auth_mode=str(row["auth_mode"]),
			credential_ref=str(row["credential_ref"]),
			scope_type=str(row["scope_type"]),
			scope_id=str(row["scope_id"]),
			updated_at=str(row["updated_at"]),
		)

	def _row_to_usage_counter(self, row: sqlite3.Row) -> UsageCounterRecord:
		return UsageCounterRecord(
			tenant_id=str(row["tenant_id"]),
			user_id=str(row["user_id"]),
			profile_id=str(row["profile_id"]),
			metric_name=str(row["metric_name"]),
			period_start=str(row["period_start"]),
			period_end=str(row["period_end"]),
			used_count=int(row["used_count"]),
			limit_count=int(row["limit_count"]),
			updated_at=str(row["updated_at"]),
		)

	def _insert_usage_counter(self, conn: sqlite3.Connection, record: UsageCounterRecord) -> None:
		conn.execute(
			"""
			INSERT OR REPLACE INTO usage_counters (
				tenant_id, user_id, profile_id, metric_name, period_start,
				period_end, used_count, limit_count, updated_at
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				record.tenant_id,
				record.user_id,
				record.profile_id,
				record.metric_name,
				record.period_start,
				record.period_end,
				record.used_count,
				record.limit_count,
				record.updated_at,
			),
		)

	@staticmethod
	def _bool_from_sqlite(value: object) -> bool:
		return bool(int(value or 0))
