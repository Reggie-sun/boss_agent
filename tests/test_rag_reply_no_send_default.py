from boss_agent_cli.rag_reply.models import ApprovalEventRecord, DraftRecord
from boss_agent_cli.rag_reply.policy import build_approval_decision


def test_no_automatic_sending_is_possible_by_default():
	decision = build_approval_decision(intent="project_question", risk_labels=[])
	assert decision.send_allowed is False

	draft = DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="candidate draft",
		intent="project_question",
		send_allowed=False,
	)
	event = ApprovalEventRecord.new(draft_id=draft.draft_id, action="approved", copied_to_clipboard=True)
	assert draft.send_allowed is False
	assert event.action == "approved"

