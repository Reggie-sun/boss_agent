from boss_agent_cli.rag_reply.adapters.mock_envelope import ingest_mock_envelope
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_mock_envelope_ingest_maps_chatmsg_payload(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	payload = {
		"ok": True,
		"command": "chatmsg",
		"data": [
			{
				"message_id": "msg_001",
				"from": "张HR",
				"type": "文本",
				"text": "方便加微信吗？",
				"security_id": "sec_001",
				"job_id": "job_001",
			}
		],
	}

	result = ingest_mock_envelope(payload, store=store)

	assert result.count == 1
	stored = store.get_message("msg_001")
	assert stored is not None
	assert stored.source == "mock_envelope"
	assert stored.direction == "inbound"
	assert stored.job_id == "job_001"

