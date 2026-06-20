import pytest

from boss_agent_cli.rag_reply.classifier import classify_message


@pytest.mark.parametrize(
	("message_text", "expected_intent"),
	[
		("期望薪资多少？", "salary_or_offer"),
		("方便发一份简历过来吗？", "resume_share_request"),
		("什么时候方便面试？", "interview_time"),
		("现在是在职吗？", "personal_status"),
		("为什么离职？", "resignation_status"),
		("这个工作地点可以接受吗？", "job_location_acceptance"),
		("方便加微信吗？", "contact_exchange"),
		("把手机号发我", "contact_exchange"),
		("邮箱给我一下", "contact_exchange"),
	],
)
def test_sensitive_rules_win(message_text: str, expected_intent: str):
	result = classify_message(message_text)
	assert result.intent == expected_intent
	assert "human_approval_required" in result.risk_labels
	assert "sensitive_intent" in result.risk_labels


def test_project_question_uses_non_sensitive_path():
	result = classify_message("你这个RAG项目具体做了什么？")
	assert result.intent == "project_question"
	assert result.classifier_source == "heuristic"


@pytest.mark.parametrize(
	("message_text", "expected_intent"),
	[
		("请介绍一下你做的企业级 RAG 项目，重点说职责、技术方案和结果。", "project_question"),
		("如果让你设计检索、重排和引用溯源，你会怎么做？", "project_question"),
		("你平时和产品、算法、后端是怎么协作的？", "resume_question"),
		("你为什么觉得自己适合这个岗位？", "resume_question"),
		("你做过哪些后端性能优化？", "resume_question"),
		("你怎么优化接口性能和查询延迟？", "resume_question"),
	],
)
def test_hr_interview_questions_map_to_expected_intents(message_text: str, expected_intent: str):
	result = classify_message(message_text)
	assert result.intent == expected_intent
