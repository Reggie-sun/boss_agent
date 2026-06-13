"""SQLite persistence for the Boss RAG reply workflow."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from boss_agent_cli.rag_reply.models import (
	ApprovalEventRecord,
	AuditLogRecord,
	ConversationRecord,
	DraftRecord,
	JobRecord,
	MessageRecord,
	RagCallRecord,
	RecruiterRecord,
)
from boss_agent_cli.rag_reply.schema import CREATE_TABLE_STATEMENTS


class RagReplyStore:
	"""Persist local Boss RAG state in a dedicated SQLite database."""

	def __init__(self, db_path: Path) -> None:
		self.db_path = Path(db_path)

	def initialize(self) -> None:
		self.db_path.parent.mkdir(parents=True, exist_ok=True)
		with self.connect() as conn:
			for statement in CREATE_TABLE_STATEMENTS:
				conn.execute(statement)
			conn.commit()

	def connect(self) -> sqlite3.Connection:
		conn = sqlite3.connect(self.db_path)
		conn.row_factory = sqlite3.Row
		return conn

	def list_tables(self) -> list[str]:
		with self.connect() as conn:
			rows = conn.execute(
				"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
			).fetchall()
		return [str(row["name"]) for row in rows]

	def save_job(self, record: JobRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO jobs (
					job_id, security_id, title, company, salary, city, summary,
					detail_json, source, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.job_id,
					record.security_id,
					record.title,
					record.company,
					record.salary,
					record.city,
					record.summary,
					self._json(record.detail),
					record.source,
					record.updated_at,
				),
			)
			conn.commit()

	def get_job(self, job_id: str) -> JobRecord | None:
		with self.connect() as conn:
			row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
		if row is None:
			return None
		return JobRecord(
			job_id=str(row["job_id"]),
			security_id=str(row["security_id"] or ""),
			title=str(row["title"] or ""),
			company=str(row["company"] or ""),
			salary=str(row["salary"] or ""),
			city=str(row["city"] or ""),
			summary=str(row["summary"] or ""),
			detail=self._loads(row["detail_json"]),
			source=str(row["source"]),
			updated_at=str(row["updated_at"]),
		)

	def save_recruiter(self, record: RecruiterRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO recruiters (
					recruiter_id, display_name, company, profile_json, updated_at
				) VALUES (?, ?, ?, ?, ?)
				""",
				(
					record.recruiter_id,
					record.display_name,
					record.company,
					self._json(record.profile),
					record.updated_at,
				),
			)
			conn.commit()

	def get_recruiter(self, recruiter_id: str) -> RecruiterRecord | None:
		with self.connect() as conn:
			row = conn.execute(
				"SELECT * FROM recruiters WHERE recruiter_id = ?",
				(recruiter_id,),
			).fetchone()
		if row is None:
			return None
		return RecruiterRecord(
			recruiter_id=str(row["recruiter_id"]),
			display_name=str(row["display_name"] or ""),
			company=str(row["company"] or ""),
			profile=self._loads(row["profile_json"]),
			updated_at=str(row["updated_at"]),
		)

	def list_recruiters(self) -> list[RecruiterRecord]:
		with self.connect() as conn:
			rows = conn.execute(
				"SELECT * FROM recruiters ORDER BY updated_at, recruiter_id"
			).fetchall()
		return [
			RecruiterRecord(
				recruiter_id=str(row["recruiter_id"]),
				display_name=str(row["display_name"] or ""),
				company=str(row["company"] or ""),
				profile=self._loads(row["profile_json"]),
				updated_at=str(row["updated_at"]),
			)
			for row in rows
		]

	def save_conversation(self, record: ConversationRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO conversations (
					conversation_id, source, job_id, recruiter_id, channel,
					last_message_at, state_json, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.conversation_id,
					record.source,
					record.job_id,
					record.recruiter_id,
					record.channel,
					record.last_message_at,
					self._json(record.state),
					record.updated_at,
				),
			)
			conn.commit()

	def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
		with self.connect() as conn:
			row = conn.execute(
				"SELECT * FROM conversations WHERE conversation_id = ?",
				(conversation_id,),
			).fetchone()
		if row is None:
			return None
		return ConversationRecord(
			conversation_id=str(row["conversation_id"]),
			source=str(row["source"]),
			job_id=row["job_id"],
			recruiter_id=row["recruiter_id"],
			channel=str(row["channel"]),
			last_message_at=row["last_message_at"],
			state=self._loads(row["state_json"]),
			updated_at=str(row["updated_at"]),
		)

	def save_message(self, record: MessageRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO messages (
					message_id, conversation_id, job_id, recruiter_id, direction,
					message_text, message_type, source, raw_json, import_batch_id, created_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.message_id,
					record.conversation_id,
					record.job_id,
					record.recruiter_id,
					record.direction,
					record.message_text,
					record.message_type,
					record.source,
					self._json(record.raw),
					record.import_batch_id,
					record.created_at,
				),
			)
			conn.commit()

	def get_message(self, message_id: str) -> MessageRecord | None:
		with self.connect() as conn:
			row = conn.execute(
				"SELECT * FROM messages WHERE message_id = ?",
				(message_id,),
			).fetchone()
		if row is None:
			return None
		return MessageRecord(
			message_id=str(row["message_id"]),
			conversation_id=str(row["conversation_id"]),
			message_text=str(row["message_text"]),
			direction=str(row["direction"]),
			message_type=str(row["message_type"]),
			job_id=row["job_id"],
			recruiter_id=row["recruiter_id"],
			source=str(row["source"]),
			raw=self._loads(row["raw_json"]),
			import_batch_id=row["import_batch_id"],
			created_at=str(row["created_at"]),
		)

	def list_messages(self, conversation_id: str | None = None) -> list[MessageRecord]:
		sql = "SELECT * FROM messages"
		params: tuple[Any, ...] = ()
		if conversation_id is not None:
			sql += " WHERE conversation_id = ?"
			params = (conversation_id,)
		sql += " ORDER BY created_at, message_id"
		with self.connect() as conn:
			rows = conn.execute(sql, params).fetchall()
		return [
			MessageRecord(
				message_id=str(row["message_id"]),
				conversation_id=str(row["conversation_id"]),
				message_text=str(row["message_text"]),
				direction=str(row["direction"]),
				message_type=str(row["message_type"]),
				job_id=row["job_id"],
				recruiter_id=row["recruiter_id"],
				source=str(row["source"]),
				raw=self._loads(row["raw_json"]),
				import_batch_id=row["import_batch_id"],
				created_at=str(row["created_at"]),
			)
			for row in rows
		]

	def save_draft(self, record: DraftRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO drafts (
					draft_id, conversation_id, source_message_id, draft_text, intent,
					risk_labels_json, evidence_json, approval_required, send_allowed,
					audit_status, rag_session_id, created_at, updated_at
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.draft_id,
					record.conversation_id,
					record.source_message_id,
					record.draft_text,
					record.intent,
					self._json(record.risk_labels),
					self._json(record.evidence),
					int(record.approval_required),
					int(record.send_allowed),
					record.audit_status,
					record.rag_session_id,
					record.created_at,
					record.updated_at,
				),
			)
			conn.commit()

	def get_draft(self, draft_id: str) -> DraftRecord | None:
		with self.connect() as conn:
			row = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
		return None if row is None else self._row_to_draft(row)

	def list_drafts(self) -> list[DraftRecord]:
		with self.connect() as conn:
			rows = conn.execute("SELECT * FROM drafts ORDER BY created_at, draft_id").fetchall()
		return [self._row_to_draft(row) for row in rows]

	def save_approval_event(self, record: ApprovalEventRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO approval_events (
					event_id, draft_id, action, notes, copied_to_clipboard, created_at
				) VALUES (?, ?, ?, ?, ?, ?)
				""",
				(
					record.event_id,
					record.draft_id,
					record.action,
					record.notes,
					int(record.copied_to_clipboard),
					record.created_at,
				),
			)
			conn.commit()

	def list_approval_events(self, draft_id: str | None = None) -> list[ApprovalEventRecord]:
		sql = "SELECT * FROM approval_events"
		params: tuple[Any, ...] = ()
		if draft_id is not None:
			sql += " WHERE draft_id = ?"
			params = (draft_id,)
		sql += " ORDER BY created_at, event_id"
		with self.connect() as conn:
			rows = conn.execute(sql, params).fetchall()
		return [
			ApprovalEventRecord(
				event_id=str(row["event_id"]),
				draft_id=str(row["draft_id"]),
				action=str(row["action"]),
				notes=row["notes"],
				copied_to_clipboard=bool(row["copied_to_clipboard"]),
				created_at=str(row["created_at"]),
			)
			for row in rows
		]

	def append_audit_log(self, record: AuditLogRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO audit_logs (
					log_id, event_type, entity_type, entity_id, payload_json, created_at
				) VALUES (?, ?, ?, ?, ?, ?)
				""",
				(
					record.log_id,
					record.event_type,
					record.entity_type,
					record.entity_id,
					self._json(record.payload),
					record.created_at,
				),
			)
			conn.commit()

	def list_audit_logs(self, entity_id: str | None = None) -> list[AuditLogRecord]:
		sql = "SELECT * FROM audit_logs"
		params: tuple[Any, ...] = ()
		if entity_id is not None:
			sql += " WHERE entity_id = ?"
			params = (entity_id,)
		sql += " ORDER BY created_at, log_id"
		with self.connect() as conn:
			rows = conn.execute(sql, params).fetchall()
		return [
			AuditLogRecord(
				log_id=str(row["log_id"]),
				event_type=str(row["event_type"]),
				entity_type=str(row["entity_type"]),
				entity_id=str(row["entity_id"]),
				payload=self._loads(row["payload_json"]),
				created_at=str(row["created_at"]),
			)
			for row in rows
		]

	def save_rag_call(self, record: RagCallRecord) -> None:
		with self.connect() as conn:
			conn.execute(
				"""
				INSERT OR REPLACE INTO rag_calls (
					call_id, draft_id, conversation_id, request_json, response_json, status, created_at
				) VALUES (?, ?, ?, ?, ?, ?, ?)
				""",
				(
					record.call_id,
					record.draft_id,
					record.conversation_id,
					self._json(record.request),
					None if record.response is None else self._json(record.response),
					record.status,
					record.created_at,
				),
			)
			conn.commit()

	def list_rag_calls(self, conversation_id: str | None = None) -> list[RagCallRecord]:
		sql = "SELECT * FROM rag_calls"
		params: tuple[Any, ...] = ()
		if conversation_id is not None:
			sql += " WHERE conversation_id = ?"
			params = (conversation_id,)
		sql += " ORDER BY created_at, call_id"
		with self.connect() as conn:
			rows = conn.execute(sql, params).fetchall()
		return [
			RagCallRecord(
				call_id=str(row["call_id"]),
				draft_id=row["draft_id"],
				conversation_id=str(row["conversation_id"]),
				request=self._loads(row["request_json"]),
				status=str(row["status"]),
				response=None if row["response_json"] is None else self._loads(row["response_json"]),
				created_at=str(row["created_at"]),
			)
			for row in rows
		]

	def _row_to_draft(self, row: sqlite3.Row) -> DraftRecord:
		return DraftRecord(
			draft_id=str(row["draft_id"]),
			conversation_id=str(row["conversation_id"]),
			source_message_id=str(row["source_message_id"]),
			draft_text=str(row["draft_text"]),
			intent=str(row["intent"]),
			risk_labels=list(self._loads(row["risk_labels_json"])),
			evidence=dict(self._loads(row["evidence_json"])),
			approval_required=bool(row["approval_required"]),
			send_allowed=bool(row["send_allowed"]),
			audit_status=str(row["audit_status"]),
			rag_session_id=row["rag_session_id"],
			created_at=str(row["created_at"]),
			updated_at=str(row["updated_at"]),
		)

	@staticmethod
	def _json(value: Any) -> str:
		return json.dumps(value, ensure_ascii=False, sort_keys=True)

	@staticmethod
	def _loads(value: str) -> Any:
		return json.loads(value)
