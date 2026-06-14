from boss_agent_cli.rag_reply.langchain_memory import (
	LANGCHAIN_MEMORY_AVAILABLE,
	RagConversationHistory,
	build_agent_state_messages,
	build_thread_payload,
)
from boss_agent_cli.rag_reply.models import MessageRecord
from boss_agent_cli.rag_reply.store import RagReplyStore

if LANGCHAIN_MEMORY_AVAILABLE:
	from langchain_core.messages import AIMessage, HumanMessage


def test_build_agent_state_messages_returns_user_assistant_pairs(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你好，介绍一下项目。",
			direction="inbound",
			source="frontend_prompt",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="msg_002",
			conversation_id="conv_001",
			message_text="我最近主要在做企业级 RAG。",
			direction="outbound",
			source="rag_draft_memory",
		)
	)

	messages = build_agent_state_messages(store=store, conversation_id="conv_001")

	assert messages == [
		{"role": "user", "content": "你好，介绍一下项目。"},
		{"role": "assistant", "content": "我最近主要在做企业级 RAG。"},
	]


def test_build_thread_payload_preserves_metadata(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你好，介绍一下项目。",
			direction="inbound",
			source="frontend_prompt",
		)
	)

	payload = build_thread_payload(store=store, conversation_id="conv_001")

	assert payload[0]["message_id"] == "msg_001"
	assert payload[0]["role"] == "user"
	assert payload[0]["source"] == "frontend_prompt"


def test_rag_conversation_history_reads_and_writes_store(tmp_path):
	if not LANGCHAIN_MEMORY_AVAILABLE:
		return
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	history = RagConversationHistory(store=store, conversation_id="conv_001")

	history.add_messages(
		[
			HumanMessage(content="你好，介绍一下项目。"),
			AIMessage(content="我最近主要在做企业级 RAG。"),
		]
	)

	messages = history.messages

	assert len(messages) == 2
	assert getattr(messages[0], "type", "") == "human"
	assert getattr(messages[1], "type", "") == "ai"
	assert store.list_messages("conv_001")[0].source == "langchain_agent"
