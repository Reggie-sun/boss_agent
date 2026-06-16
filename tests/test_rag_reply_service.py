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


class _FakeAgentAnswerAdapter:
	def __init__(self, result: _FakeRagResult) -> None:
		self.result = result
		self.calls: list[dict[str, object]] = []

	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_answer: str,
		citations: list[dict] | None = None,
	) -> _FakeRagResult:
		self.calls.append(
			{
				"message_text": message_text,
				"intent": intent,
				"job_summary": job_summary,
				"rag_answer": rag_answer,
				"citations": list(citations or []),
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


def test_draft_command_uses_agent_answer_adapter_when_rag_succeeds(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍下你做的 RAG。",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(
		_FakeRagResult(
			ok=True,
			answer="候选人负责企业级 RAG 项目的检索链路和问答编排。",
			citations=[{"title": "企业级RAG面试参考文档"}],
			reasoning_summary={"mode": "grounded"},
		)
	)
	agent_adapter = _FakeAgentAnswerAdapter(
		_FakeRagResult(
			ok=True,
			answer="我在这个企业级 RAG 项目里主要负责检索链路和问答编排，也做了引用溯源和多轮问答优化。",
			citations=[],
			reasoning_summary={"strategy": "改写成第一人称"},
			raw_response={"answer_text": "rewritten"},
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
		agent_answer_adapter=agent_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "draft_created"
	assert draft.draft_text.startswith("我在这个企业级 RAG 项目里")
	assert draft.evidence["source"] == "boss_agent_ai"
	assert draft.evidence["upstream_source"] == "enterprise_rag"
	assert draft.evidence["grounded_answer"] == "候选人负责企业级 RAG 项目的检索链路和问答编排。"
	assert draft.evidence["reasoning_summary"] == {
		"grounding": {"mode": "grounded"},
		"agent_strategy": {"strategy": "改写成第一人称"},
	}
	assert agent_adapter.calls[0]["rag_answer"] == "候选人负责企业级 RAG 项目的检索链路和问答编排。"


def test_draft_command_falls_back_to_grounded_answer_when_agent_rewrite_fails(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="介绍下你做的 RAG。",
			direction="inbound",
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=_FakeRagAdapter(
			_FakeRagResult(
				ok=True,
				answer="候选人负责企业级 RAG 项目的检索链路和问答编排。",
				citations=[{"title": "企业级RAG面试参考文档"}],
				reasoning_summary={"mode": "grounded"},
			)
		),
		agent_answer_adapter=_FakeAgentAnswerAdapter(
			_FakeRagResult(
				ok=False,
				answer="",
				citations=[],
				error_message="llm unavailable",
				audit_status="agent_answer_failed",
			)
		),
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.draft_text == "候选人负责企业级 RAG 项目的检索链路和问答编排。"
	assert draft.evidence["source"] == "enterprise_rag"
	assert draft.evidence["agent_error_message"] == "llm unavailable"


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


def test_draft_command_uses_agent_answer_fallback_when_rag_fails_and_no_ai_fallback(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你平时和产品、算法、后端是怎么协作的？",
			direction="inbound",
		)
	)
	agent_adapter = _FakeAgentAnswerAdapter(
		_FakeRagResult(
			ok=True,
			answer="我平时会把协作拆成业务场景、检索策略和工程交付三个层面。",
			citations=[],
			reasoning_summary={"strategy": "命中本地候选人面试回答模板"},
			raw_response={"mode": "local_interview_template"},
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
		agent_answer_adapter=agent_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.audit_status == "draft_created"
	assert draft.evidence["source"] == "boss_agent_ai_fallback"
	assert draft.evidence["fallback_from"] == "enterprise_rag"
	assert draft.evidence["rag_error_message"] == "timed out"
	assert draft.draft_text.startswith("我平时会把协作拆成业务场景")
	assert agent_adapter.calls[0]["rag_answer"] == ""


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
	assert "附件简历" in draft.draft_text
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert rag_adapter.calls == []


def test_salary_question_uses_rag_answer_when_available(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="为什么离职，期望薪资多少。",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(
		_FakeRagResult(ok=True, answer="当前薪资是已上传材料里的 X，期望薪资是 Y。", citations=[])
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.intent == "salary_or_offer"
	assert draft.draft_text == "当前薪资是已上传材料里的 X，期望薪资是 Y。"
	assert draft.evidence["source"] == "enterprise_rag"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert len(rag_adapter.calls) == 1
	assert "当前薪资和期望薪资" in rag_adapter.calls[0]["rag_question"]


def test_salary_question_falls_back_to_agent_handoff_when_rag_fails(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="期望薪资多少？",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(
		_FakeRagResult(
			ok=False,
			answer="",
			citations=[],
			error_message="salary facts not available",
			audit_status="rag_failed",
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.intent == "salary_or_offer"
	assert "我是候选人的求职助理 Agent" in draft.draft_text
	assert "薪资相关问题需要候选人本人确认后回复" in draft.draft_text
	assert draft.evidence["fallback_from"] == "enterprise_rag"
	assert draft.evidence["rag_error_message"] == "salary facts not available"
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert len(rag_adapter.calls) == 1


def test_job_location_question_generates_safe_local_draft(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="这个工作地点可以接受吗。",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(_FakeRagResult(ok=True, answer="unused", citations=[]))
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.intent == "job_location_acceptance"
	assert "这个工作地点可以接受" in draft.draft_text
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert rag_adapter.calls == []


def test_resignation_question_generates_safe_local_draft(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="为什么离职？",
			direction="inbound",
		)
	)
	rag_adapter = _FakeRagAdapter(_FakeRagResult(ok=True, answer="unused", citations=[]))
	service = BossRagReplyService(
		store=store,
		rag_adapter=rag_adapter,
	)

	draft = service.create_draft_for_message("msg_001")

	assert draft.intent == "resignation_status"
	assert "AI 应用落地" in draft.draft_text
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
