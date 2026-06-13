from boss_agent_cli.rag_reply.models import DraftRecord


def test_draft_record_defaults_to_no_send():
	draft = DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="draft text",
		intent="project_question",
	)
	assert draft.send_allowed is False
	assert draft.approval_required is True
	assert draft.audit_status == "draft_created"
	assert draft.risk_labels == []
	assert draft.evidence == {}

