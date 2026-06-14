"""LangChain-compatible memory helpers backed by the local Boss RAG store."""

from __future__ import annotations

import hashlib
from typing import Any

from boss_agent_cli.rag_reply.models import MessageRecord, utc_now_iso
from boss_agent_cli.rag_reply.store import RagReplyStore

try:
	from langchain_core.chat_history import BaseChatMessageHistory
	from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
except ImportError:  # pragma: no cover - optional dependency
	BaseChatMessageHistory = object  # type: ignore[assignment]
	AIMessage = HumanMessage = BaseMessage = None  # type: ignore[assignment]


LANGCHAIN_MEMORY_AVAILABLE = BaseChatMessageHistory is not object


if LANGCHAIN_MEMORY_AVAILABLE:

	class RagConversationHistory(BaseChatMessageHistory):
		"""Expose one Boss conversation as LangChain chat history."""

		def __init__(
			self,
			*,
			store: RagReplyStore,
			conversation_id: str,
			source: str = "langchain_agent",
		) -> None:
			self.store = store
			self.conversation_id = conversation_id
			self.source = source

		@property
		def messages(self) -> list[BaseMessage]:
			return [
				self._record_to_message(record)
				for record in self.store.list_messages(self.conversation_id)
				if record.message_text.strip()
			]

		def add_messages(self, messages: list[BaseMessage]) -> None:
			for index, message in enumerate(messages):
				self.store.save_message(
					MessageRecord(
						message_id=self._message_id(message, index=index),
						conversation_id=self.conversation_id,
						message_text=str(message.content),
						direction=self._direction_for_message(message),
						message_type="text",
						source=self.source,
						raw={"memory_role": self._role_for_message(message)},
						created_at=utc_now_iso(),
					)
				)

		def clear(self) -> None:
			return None

		@staticmethod
		def _record_to_message(record: MessageRecord) -> BaseMessage:
			payload = {
				"source": record.source,
				"created_at": record.created_at,
				"message_id": record.message_id,
			}
			if record.direction == "outbound":
				return AIMessage(content=record.message_text, additional_kwargs=payload)
			return HumanMessage(content=record.message_text, additional_kwargs=payload)

		@staticmethod
		def _direction_for_message(message: BaseMessage) -> str:
			return "outbound" if RagConversationHistory._role_for_message(message) == "assistant" else "inbound"

		@staticmethod
		def _role_for_message(message: BaseMessage) -> str:
			msg_type = getattr(message, "type", "")
			return "assistant" if msg_type == "ai" else "user"

		def _message_id(self, message: BaseMessage, *, index: int) -> str:
			digest = hashlib.sha1(str(message.content).encode("utf-8")).hexdigest()[:12]
			return f"lcmsg_{self.conversation_id}_{index}_{digest}"
else:  # pragma: no cover - optional dependency fallback
	RagConversationHistory = None  # type: ignore[assignment]


def build_agent_state_messages(
	*,
	store: RagReplyStore,
	conversation_id: str,
	limit: int = 20,
) -> list[dict[str, str]]:
	"""Return LangChain-style user/assistant messages for one conversation."""
	records = store.list_messages(conversation_id)[-limit:]
	return [
		{
			"role": "assistant" if record.direction == "outbound" else "user",
			"content": record.message_text,
		}
		for record in records
		if record.message_text.strip()
	]


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
