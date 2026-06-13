from boss_agent_cli.rag_reply.policy import build_approval_decision


def test_policy_blocks_sensitive_intents_from_send():
	decision = build_approval_decision(
		intent="salary_or_offer",
		risk_labels=["human_approval_required"],
	)
	assert decision.approval_required is True
	assert decision.send_allowed is False
	assert decision.audit_status == "draft_created"
	assert "sensitive_intent" in decision.risk_labels


def test_policy_keeps_non_sensitive_drafts_closed_in_v1():
	decision = build_approval_decision(intent="project_question", risk_labels=[])
	assert decision.approval_required is True
	assert decision.send_allowed is False

