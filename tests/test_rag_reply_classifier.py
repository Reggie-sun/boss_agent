import pytest

from boss_agent_cli.rag_reply.classifier import classify_message


@pytest.mark.parametrize(
	("message_text", "expected_intent"),
	[
		("期望薪资多少？", "salary_or_offer"),
		("什么时候方便面试？", "interview_time"),
		("现在是在职吗？", "personal_status"),
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

