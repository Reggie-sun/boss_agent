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

	assert result.ok is True
	assert result.raw_response == {"mode": "rule_based"}
	assert result.answer.startswith("我主要负责企业级 RAG 项目的检索链路和问答编排。")


def test_agent_answer_adapter_returns_closed_result_on_ai_error():
	adapter = AgentAnswerAdapter(ai_service=_FakeAIService(AIServiceError("API 500")))

	result = adapter.answer(
		message_text="介绍下你做的 RAG。",
		intent="project_question",
		job_summary=None,
		rag_answer="候选人主要负责企业级 RAG 项目的检索链路和问答编排。",
		citations=[],
	)

	assert result.ok is True
	assert result.raw_response == {"mode": "rule_based"}
	assert result.reasoning_summary == {
		"strategy": "在无可用 AI 改写服务时，基于 grounded answer 做本地规则改写"
	}


def test_agent_answer_adapter_uses_rule_based_rewrite_when_ai_service_missing():
	adapter = AgentAnswerAdapter(ai_service=None)

	result = adapter.answer(
		message_text="请介绍一下你做的 RAG。",
		intent="project_question",
		job_summary=None,
		rag_answer="""## 1. 核心结论

我最有代表性的项目是企业级 RAG 知识库与智能问答平台。

### 2.1 项目背景与目标
该项目旨在解决制造业企业内部制度文档和 SOP 检索、问答及追溯问题。

### 2.2 核心技术方案
- 文档摄取与处理：支持 OCR、解析和结构化切块。
- 检索与问答：采用混合检索、重排序和多轮问答。

### 2.3 项目成果
该项目实现了 89 个 API 路由和 26 个核心 schema 模块。

## 3. 补充说明
在该项目中，我主要负责核心架构的设计与落地开发工作。
""",
		citations=[],
	)

	assert result.ok is True
	assert result.answer.startswith("我最有代表性的项目是企业级 RAG 知识库与智能问答平台。")
	assert "这个项目旨在解决制造业企业内部制度文档和 SOP 检索、问答及追溯问题。" in result.answer
	assert "在这个项目中，我主要负责核心架构的设计与落地开发工作。" in result.answer
	assert result.raw_response == {"mode": "rule_based"}


def test_agent_answer_rule_based_rewrite_filters_unrelated_profile_details():
	adapter = AgentAnswerAdapter(ai_service=None)

	result = adapter.answer(
		message_text="请你做一个简短的自我介绍，重点说和企业级 RAG 相关的经历。",
		intent="project_question",
		job_summary=None,
		rag_answer="孙瑞杰在企业级 RAG 项目中负责检索链路和问答编排。孙瑞杰，23岁，目前在推进企业级知识库问答平台建设。",
		citations=[],
	)

	assert result.ok is True
	assert "我目前在宁波伟立机器人科技股份有限公司做 AI 开发工程师" in result.answer
	assert "23岁" not in result.answer
	assert result.raw_response == {"mode": "local_interview_template"}


def test_agent_answer_uses_local_template_for_hr_fit_question():
	adapter = AgentAnswerAdapter(ai_service=None)

	result = adapter.answer(
		message_text="你为什么觉得自己适合这个岗位？",
		intent="resume_question",
		job_summary=None,
		rag_answer="资料未明确覆盖。",
		citations=[],
	)

	assert result.ok is True
	assert "我觉得自己比较适合 AI 应用工程师" in result.answer
	assert result.raw_response == {"mode": "local_interview_template"}
