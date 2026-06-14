from dataclasses import dataclass

from boss_agent_cli.rag_reply.models import ConversationRecord, DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


@dataclass
class _FakeRagResult:
	ok: bool
	answer: str
	citations: list[dict]
	reasoning_summary: dict | None = None
	raw_response: dict | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True


class _FakeRagAdapter:
	def __init__(self, result: _FakeRagResult) -> None:
		self.result = result
		self.calls: list[dict[str, str]] = []

	def answer(self, *, rag_question: str, session_id: str, mode: str = "accurate") -> _FakeRagResult:
		self.calls.append({"rag_question": rag_question, "session_id": session_id, "mode": mode})
		return self.result


class _FakeFallbackAdapter:
	def __init__(self, result: _FakeRagResult) -> None:
		self.result = result
		self.calls: list[dict[str, str | None]] = []

	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_error: str | None,
	) -> _FakeRagResult:
		self.calls.append(
			{
				"message_text": message_text,
				"intent": intent,
				"job_summary": job_summary,
				"rag_error": rag_error,
			}
		)
		return self.result


def test_draft_command_saves_draft_and_audit_log(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_000",
			conversation_id="conv_001",
			message_text="你好，方便介绍一下项目吗？",
			direction="inbound",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="draftmsg_msg_000",
			conversation_id="conv_001",
			message_text="您好，我最近主要在做企业级 RAG 项目。",
			direction="outbound",
			message_type="draft",
			source="rag_draft_memory",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你这个RAG项目具体做了什么？",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(_FakeRagResult(ok=True, answer="这是候选草稿", citations=[{"id": "c1"}]))
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.draft_text == "这是候选草稿"
	assert draft.audit_status == "draft_created"
	assert rag_adapter.calls[0]["session_id"].startswith("boss-rag-")
	assert len(rag_adapter.calls[0]["session_id"]) <= 24
	assert "Conversation memory:" not in rag_adapter.calls[0]["rag_question"]
	assert "您好，我最近主要在做企业级 RAG 项目。" not in rag_adapter.calls[0]["rag_question"]
	assert store.list_audit_logs()
	messages = store.list_messages("conv_001")
	assert messages[-1].direction == "outbound"
	assert messages[-1].source == "rag_draft_memory"
	assert messages[-1].message_text == "这是候选草稿"


def test_draft_command_persists_closed_record_when_rag_fails(tmp_path):
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
	service = BossRagReplyService(
		store=store,
		rag_adapter=_FakeRagAdapter(
			_FakeRagResult(
				ok=False,
				answer="",
				citations=[],
				error_message="timed out",
				audit_status="rag_failed",
			)
		),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "rag_failed"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert store.list_audit_logs()


def test_draft_command_uses_ai_fallback_when_rag_fails(tmp_path):
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
	fallback_adapter = _FakeFallbackAdapter(
		_FakeRagResult(
			ok=True,
			answer="您好，我近期主要在做企业级 RAG 相关项目，覆盖方案设计、实现与落地，如您关注某块我可以进一步展开。",
			citations=[],
			raw_response={"strategy": "保守总结"},
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=_FakeRagAdapter(
			_FakeRagResult(
				ok=False,
				answer="",
				citations=[],
				error_message="timed out",
				audit_status="rag_failed",
			)
		),
		fallback_adapter=fallback_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "draft_created"
	assert draft.evidence["source"] == "ai_fallback"
	assert draft.evidence["fallback_from"] == "enterprise_rag"
	assert draft.evidence["rag_error_message"] == "timed out"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert fallback_adapter.calls[0]["intent"] == "project_question"
	assert store.list_messages("conv_001")[-1].source == "rag_draft_memory"


def test_resume_share_request_generates_local_approval_draft(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="方便发一份简历过来吗？",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(_FakeRagResult(ok=True, answer="unused", citations=[]))
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.intent == "resume_share_request"
	assert "官方页面发送简历" in draft.draft_text
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert rag_adapter.calls == []


def test_approve_command_persists_event_without_send(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	draft = DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="这是候选草稿",
		intent="project_question",
	)
	store.save_draft(draft)
	service = BossRagReplyService(
		store=store,
		rag_adapter=_FakeRagAdapter(_FakeRagResult(ok=True, answer="unused", citations=[])),
	)

	result = service.approve_draft(draft.draft_id, copy_to_clipboard=False)

	assert result.event.action == "approved"
	assert result.draft.send_allowed is False
	assert len(store.list_approval_events(draft.draft_id)) == 1
	assert len(store.list_audit_logs(draft.draft_id)) == 1
