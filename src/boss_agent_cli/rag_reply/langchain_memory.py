"""Thread payload helpers backed by the local Boss RAG store."""

from __future__ import annotations

from typing import Any

from boss_agent_cli.rag_reply.store import RagReplyStore


def build_thread_payload(
	*,
	store: RagReplyStore,
	conversation_id: str,
	limit: int = 20,
) -> list[dict[str, Any]]:
	"""Return a frontend-safe thread payload from the local conversation store."""
	records = store.list_messages(conversation_id)[-limit:]
	return [
		{
			"message_id": record.message_id,
			"role": "assistant" if record.direction == "outbound" else "user",
			"content": record.message_text,
			"source": record.source,
			"created_at": record.created_at,
		}
		for record in records
		if record.message_text.strip()
	]
