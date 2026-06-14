"""LangChain-style conversation memory backed by the local Boss RAG store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from boss_agent_cli.rag_reply.models import MessageRecord, utc_now_iso
from boss_agent_cli.rag_reply.store import RagReplyStore

try:
	from langchain_core.chat_history import BaseChatMessageHistory
	from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
except ImportError:  # pragma: no cover - guarded at runtime
	BaseChatMessageHistory = object  # type: ignore[assignment]
	AIMessage = HumanMessage = BaseMessage = None  # type: ignore[assignment]


LANGCHAIN_MEMORY_AVAILABLE = BaseChatMessageHistory is not object


@dataclass(slots=True)
class MemoryTurn:
	role: str
	content: str
	source: str
	created_at: str


if LANGCHAIN_MEMORY_AVAILABLE:

	class RagConversationHistory(BaseChatMessageHistory):
		"""Expose local Boss conversation state through LangChain's history interface."""

		def __init__(self, *, store: RagReplyStore, conversation_id: str) -> None:
			self.store = store
			self.conversation_id = conversation_id

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
						source="langchain_memory",
						raw={"memory_role": self._role_for_message(message)},
						created_at=utc_now_iso(),
					)
				)

		def clear(self) -> None:
			return None

		@staticmethod
		def _record_to_message(record: MessageRecord) -> BaseMessage:
			if record.direction == "outbound":
				return AIMessage(
					content=record.message_text,
					additional_kwargs={
						"source": record.source,
						"created_at": record.created_at,
						"message_id": record.message_id,
					},
				)
			return HumanMessage(
				content=record.message_text,
				additional_kwargs={
					"source": record.source,
					"created_at": record.created_at,
					"message_id": record.message_id,
				},
			)

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


def build_history_context(
	*,
	store: RagReplyStore,
	conversation_id: str,
	current_message_id: str | None = None,
	limit: int = 6,
) -> list[MemoryTurn]:
	"""Return recent turns suitable for prompt injection or frontend display."""
	if LANGCHAIN_MEMORY_AVAILABLE:
		history = RagConversationHistory(store=store, conversation_id=conversation_id)
		messages = history.messages
		if current_message_id is not None:
			messages = [
				message
				for message in messages
				if getattr(message, "additional_kwargs", {}).get("message_id") != current_message_id
			]
		selected = messages[-limit:]
		return [
			MemoryTurn(
				role="assistant" if getattr(message, "type", "") == "ai" else "user",
				content=str(message.content),
				source=str(getattr(message, "additional_kwargs", {}).get("source", "langchain_memory")),
				created_at=str(getattr(message, "additional_kwargs", {}).get("created_at", "")),
			)
			for message in selected
			if str(message.content).strip()
		]
	records = store.list_messages(conversation_id)
	filtered = [
		record
		for record in records
		if record.message_text.strip() and record.message_id != current_message_id
	]
	selected = filtered[-limit:]
	return [
		MemoryTurn(
			role="assistant" if record.direction == "outbound" else "user",
			content=record.message_text,
			source=record.source,
			created_at=record.created_at,
		)
		for record in selected
	]


def format_history_context(turns: list[MemoryTurn]) -> str:
	"""Render recent conversation turns into a compact prompt block."""
	if not turns:
		return ""
	lines = ["Conversation memory:"]
	for turn in turns:
		role_label = "Candidate reply draft" if turn.role == "assistant" else "Recruiter message"
		lines.append(f"- {role_label}: {turn.content}")
	return "\n".join(lines)


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
