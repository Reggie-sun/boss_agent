from boss_agent_cli.ai.service import AIServiceError
from boss_agent_cli.rag_reply.adapters.agent_answer import AgentAnswerAdapter


class _FakeAIService:
	def __init__(self, response: str | Exception) -> None:
		self.response = response
		self.calls: list[list[dict[str, str]]] = []

	def chat(self, messages):
		self.calls.append(messages)
		if isinstance(self.response, Exception):
			raise self.response
		return self.response


def test_agent_answer_adapter_rewrites_grounded_answer_into_candidate_voice():
	adapter = AgentAnswerAdapter(
		ai_service=_FakeAIService(
			"""```json
			{"answer_text":"我在这个企业级 RAG 项目里主要负责检索链路和问答编排，覆盖索引策略、引用溯源和多轮问答效果优化。","strategy":"把第三人称 grounded answer 改写成候选人第一人称，并保留可追问细节"}
			```"""
		)
	)

	result = adapter.answer(
		message_text="介绍下你做的 RAG。",
		intent="project_question",
		job_summary="企业级 RAG 平台",
		rag_answer="候选人主要负责企业级 RAG 项目的检索链路和问答编排。",
		citations=[{"title": "企业级RAG面试参考文档", "snippet": "负责检索链路、引用溯源和多轮问答"}],
	)

	assert result.ok is True
	assert result.answer.startswith("我在这个企业级 RAG 项目里")
	assert result.reasoning_summary == {
		"strategy": "把第三人称 grounded answer 改写成候选人第一人称，并保留可追问细节"
	}


def test_agent_answer_adapter_returns_closed_result_on_parse_error():
	adapter = AgentAnswerAdapter(ai_service=_FakeAIService("plain text"))

	result = adapter.answer(
		message_text="介绍下你做的 RAG。",
		intent="project_question",
		job_summary=None,
		rag_answer="候选人主要负责企业级 RAG 项目的检索链路和问答编排。",
		citations=[],
	)

	assert result.ok is False
	assert result.audit_status == "agent_answer_failed"


def test_agent_answer_adapter_returns_closed_result_on_ai_error():
	adapter = AgentAnswerAdapter(ai_service=_FakeAIService(AIServiceError("API 500")))

	result = adapter.answer(
		message_text="介绍下你做的 RAG。",
		intent="project_question",
		job_summary=None,
		rag_answer="候选人主要负责企业级 RAG 项目的检索链路和问答编排。",
		citations=[],
	)

	assert result.ok is False
	assert result.audit_status == "agent_answer_failed"
