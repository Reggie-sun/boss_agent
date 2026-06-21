from pathlib import Path

from boss_agent_cli.rag_reply.adapters.agent_answer import AgentAnswerAdapter


def test_agent_answer_source_has_no_personal_candidate_facts():
	source = Path("src/boss_agent_cli/rag_reply/adapters/agent_answer.py").read_text(
		encoding="utf-8"
	)
	for token in (
		"宁波伟立",
		"89 个 API",
		"26 个核心 schema",
		"企业级 RAG 知识库与智能问答平台",
	):
		assert token not in source


def test_personal_answer_without_ai_or_profile_grounding_fails_closed():
	adapter = AgentAnswerAdapter(ai_service=None)

	result = adapter.answer(
		message_text="请做一个简短的自我介绍。",
		intent="resume_question",
		job_summary=None,
		rag_answer="",
		citations=[],
	)

	assert result.ok is False
	assert result.audit_status == "agent_answer_failed"
	assert result.raw_response == {"mode": "profile_required"}
