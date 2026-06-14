from boss_agent_cli.ai.service import AIServiceError
from boss_agent_cli.rag_reply.adapters.ai_fallback import AIFallbackAdapter


class _FakeAIService:
	def __init__(self, response: str | Exception) -> None:
		self.response = response
		self.calls: list[list[dict[str, str]]] = []

	def chat(self, messages):
		self.calls.append(messages)
		if isinstance(self.response, Exception):
			raise self.response
		return self.response


def test_ai_fallback_adapter_returns_reply_from_json():
	adapter = AIFallbackAdapter(
		ai_service=_FakeAIService(
			"""```json
			{"reply_text":"您好，我最近主要在做企业级 RAG 相关项目，如您关注具体模块我可以进一步展开。","strategy":"保守总结"}
			```"""
		)
	)

	result = adapter.answer(
		message_text="你这个RAG项目具体做了什么？",
		intent="project_question",
		job_summary="企业级 RAG 平台",
		rag_error="timed out",
	)

	assert result.ok is True
	assert "企业级 RAG" in result.answer
	assert result.reasoning_summary == {"strategy": "保守总结"}


def test_ai_fallback_adapter_returns_closed_result_on_parse_error():
	adapter = AIFallbackAdapter(ai_service=_FakeAIService("plain text"))

	result = adapter.answer(
		message_text="你这个RAG项目具体做了什么？",
		intent="project_question",
		job_summary=None,
		rag_error="timed out",
	)

	assert result.ok is False
	assert result.audit_status == "ai_fallback_failed"


def test_ai_fallback_adapter_returns_closed_result_on_ai_error():
	adapter = AIFallbackAdapter(ai_service=_FakeAIService(AIServiceError("API 500")))

	result = adapter.answer(
		message_text="你这个RAG项目具体做了什么？",
		intent="project_question",
		job_summary=None,
		rag_error="timed out",
	)

	assert result.ok is False
	assert result.audit_status == "ai_fallback_failed"
