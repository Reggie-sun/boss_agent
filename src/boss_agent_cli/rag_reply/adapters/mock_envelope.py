"""Ingest structured mock boss-agent-cli envelopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from boss_agent_cli.rag_reply.adapters.manual_import import ImportBatchResult, _persist_normalized_messages
from boss_agent_cli.rag_reply.models import new_id, utc_now_iso
from boss_agent_cli.rag_reply.store import RagReplyStore


def ingest_mock_envelope(payload: dict[str, Any], store: RagReplyStore) -> ImportBatchResult:
	"""Persist a success-envelope payload from boss-agent-cli into local state."""
	import_batch_id = new_id("mock")
	items = payload.get("data")
	if not payload.get("ok") or not isinstance(items, list):
		raise ValueError("Mock envelope must contain ok=true and a list data payload.")
	normalized = [_normalize_envelope_item(item, import_batch_id=import_batch_id) for item in items if isinstance(item, dict)]
	conversation_ids = _persist_normalized_messages(normalized, store=store)
	return ImportBatchResult(
		import_batch_id=import_batch_id,
		conversation_ids=conversation_ids,
		message_ids=[item["message_id"] for item in normalized],
		source="mock_envelope",
	)


def load_and_ingest_mock_envelope(path: Path, store: RagReplyStore) -> ImportBatchResult:
	"""Load a JSON file and ingest it as a mock envelope."""
	import json

	payload = json.loads(Path(path).read_text(encoding="utf-8"))
	if not isinstance(payload, dict):
		raise ValueError("Mock envelope must be a JSON object.")
	return ingest_mock_envelope(payload, store=store)


def _normalize_envelope_item(item: dict[str, Any], *, import_batch_id: str) -> dict[str, Any]:
	security_id = str(item.get("security_id") or item.get("job_id") or "unknown")
	conversation_id = str(item.get("conversation_id") or f"mock::{security_id}")
	from_name = str(item.get("from") or "")
	return {
		"message_id": str(item.get("message_id") or new_id("msg")),
		"conversation_id": conversation_id,
		"message_text": str(item.get("text") or ""),
		"direction": "outbound" if from_name == "我" else "inbound",
		"message_type": str(item.get("type") or "text"),
		"job_id": item.get("job_id"),
		"recruiter_id": item.get("recruiter_id") or item.get("security_id"),
		"source": "mock_envelope",
		"raw": dict(item),
		"import_batch_id": import_batch_id,
		"created_at": str(item.get("time") or utc_now_iso()),
	}

