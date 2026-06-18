from pathlib import Path

from boss_agent_cli.rag_reply.models import (
	ApprovalEventRecord,
	AuditLogRecord,
	ConversationRecord,
	DraftRecord,
	MessageRecord,
)
import boss_agent_cli.rag_reply.store as store_module
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_store_creates_expected_tables(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	assert set(store.list_tables()) >= {
		"messages",
		"drafts",
		"approval_events",
		"audit_logs",
		"rag_calls",
	}


def test_store_configures_sqlite_for_concurrent_frontend_and_watcher_access(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()

	with store.connect() as conn:
		busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
		journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

	assert busy_timeout == store_module._SQLITE_BUSY_TIMEOUT_MS
	assert str(journal_mode).lower() == "wal"


def test_store_round_trips_message_draft_and_audit(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你这个RAG项目具体做了什么？",
			direction="inbound",
		)
	)
	draft = DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="这是候选草稿",
		intent="project_question",
		evidence={"source": "test"},
	)
	store.save_draft(draft)
	store.save_approval_event(ApprovalEventRecord.new(draft_id=draft.draft_id, action="approved"))
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="draft_created",
			entity_type="draft",
			entity_id=draft.draft_id,
			payload={"status": "ok"},
		)
	)

	assert store.get_message("msg_001") is not None
	assert store.get_draft(draft.draft_id) is not None
	assert len(store.list_drafts()) == 1
	assert len(store.list_approval_events(draft.draft_id)) == 1
	assert len(store.list_audit_logs(draft.draft_id)) == 1
