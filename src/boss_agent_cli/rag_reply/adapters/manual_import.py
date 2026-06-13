"""Manual message import for the Boss RAG workflow."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord, new_id, utc_now_iso
from boss_agent_cli.rag_reply.store import RagReplyStore


@dataclass(slots=True)
class ImportBatchResult:
	import_batch_id: str
	conversation_ids: list[str]
	message_ids: list[str]
	source: str

	@property
	def count(self) -> int:
		return len(self.message_ids)


def import_messages(path: Path, fmt: str, store: RagReplyStore) -> ImportBatchResult:
	"""Import messages from json, markdown, or csv into local SQLite."""
	import_batch_id = new_id("import")
	text = Path(path).read_text(encoding="utf-8")
	if fmt == "json":
		normalized = _normalize_json_payload(json.loads(text), import_batch_id=import_batch_id)
	elif fmt == "csv":
		normalized = _normalize_csv_payload(text, import_batch_id=import_batch_id)
	else:
		normalized = _normalize_markdown_payload(text, import_batch_id=import_batch_id, stem=Path(path).stem)
	conversation_ids = _persist_normalized_messages(normalized, store=store)
	return ImportBatchResult(
		import_batch_id=import_batch_id,
		conversation_ids=conversation_ids,
		message_ids=[item["message_id"] for item in normalized],
		source="manual_import",
	)


def _persist_normalized_messages(messages: list[dict[str, Any]], *, store: RagReplyStore) -> list[str]:
	conversation_ids: list[str] = []
	for item in messages:
		conversation_id = str(item["conversation_id"])
		if conversation_id not in conversation_ids:
			store.save_conversation(
				ConversationRecord(
					conversation_id=conversation_id,
					source=str(item.get("source") or "manual_import"),
					job_id=item.get("job_id"),
					recruiter_id=item.get("recruiter_id"),
					last_message_at=item["created_at"],
				)
			)
			conversation_ids.append(conversation_id)
		store.save_message(
			MessageRecord(
				message_id=str(item["message_id"]),
				conversation_id=conversation_id,
				message_text=str(item["message_text"]),
				direction=str(item["direction"]),
				message_type=str(item.get("message_type") or "text"),
				job_id=item.get("job_id"),
				recruiter_id=item.get("recruiter_id"),
				source=str(item.get("source") or "manual_import"),
				raw=dict(item.get("raw") or {}),
				import_batch_id=item.get("import_batch_id"),
				created_at=str(item["created_at"]),
			)
		)
	return conversation_ids


def _normalize_json_payload(payload: object, *, import_batch_id: str) -> list[dict[str, Any]]:
	if isinstance(payload, dict):
		conversation_id = str(payload.get("conversation_id") or new_id("conv"))
		source = str(payload.get("source") or "manual_import")
		messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
	else:
		conversation_id = new_id("conv")
		source = "manual_import"
		messages = payload if isinstance(payload, list) else []
	return [
		_normalize_message_item(
			item if isinstance(item, dict) else {},
			conversation_id=str((item or {}).get("conversation_id") or conversation_id) if isinstance(item, dict) else conversation_id,
			import_batch_id=import_batch_id,
			source=source,
		)
		for item in messages
	]


def _normalize_csv_payload(text: str, *, import_batch_id: str) -> list[dict[str, Any]]:
	rows = list(csv.DictReader(text.splitlines()))
	conversation_id = new_id("conv")
	return [
		_normalize_message_item(
			row,
			conversation_id=str(row.get("conversation_id") or conversation_id),
			import_batch_id=import_batch_id,
			source="manual_import",
		)
		for row in rows
	]


def _normalize_markdown_payload(text: str, *, import_batch_id: str, stem: str) -> list[dict[str, Any]]:
	conversation_id = f"md::{stem}"
	items: list[dict[str, Any]] = []
	for raw_line in text.splitlines():
		line = raw_line.strip()
		if not line:
			continue
		if line.startswith(("HR:", "HR：")):
			items.append(
				_normalize_message_item(
					{"message_text": line.split(":", 1)[-1].split("：", 1)[-1].strip(), "direction": "inbound"},
					conversation_id=conversation_id,
					import_batch_id=import_batch_id,
					source="manual_import",
				)
			)
		elif line.startswith(("ME:", "ME：", "我:", "我：")):
			items.append(
				_normalize_message_item(
					{"message_text": line.split(":", 1)[-1].split("：", 1)[-1].strip(), "direction": "outbound"},
					conversation_id=conversation_id,
					import_batch_id=import_batch_id,
					source="manual_import",
				)
			)
	return items


def _normalize_message_item(
	item: dict[str, Any],
	*,
	conversation_id: str,
	import_batch_id: str,
	source: str,
) -> dict[str, Any]:
	return {
		"message_id": str(item.get("message_id") or new_id("msg")),
		"conversation_id": conversation_id,
		"message_text": str(item.get("message_text") or item.get("text") or ""),
		"direction": str(item.get("direction") or "inbound"),
		"message_type": str(item.get("message_type") or item.get("type") or "text"),
		"job_id": item.get("job_id"),
		"recruiter_id": item.get("recruiter_id"),
		"source": source,
		"raw": dict(item),
		"import_batch_id": import_batch_id,
		"created_at": str(item.get("created_at") or utc_now_iso()),
	}
