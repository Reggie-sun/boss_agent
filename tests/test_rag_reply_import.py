import json
from pathlib import Path

from boss_agent_cli.rag_reply.adapters.manual_import import import_messages
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_import_messages_json_writes_message_and_conversation(tmp_path: Path):
	payload = {
		"conversation_id": "conv_001",
		"messages": [
			{
				"message_id": "msg_001",
				"message_text": "你这个RAG项目具体做了什么？",
				"direction": "inbound",
			}
		],
	}
	path = tmp_path / "messages.json"
	path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()

	result = import_messages(path, "json", store)

	assert result.count == 1
	assert store.get_message("msg_001") is not None
	assert store.get_conversation("conv_001") is not None
	assert store.get_message("msg_001").message_text == "你这个RAG项目具体做了什么？"

