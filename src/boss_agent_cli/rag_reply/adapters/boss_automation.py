"""Read-only Boss automation adapter for the local RAG reply workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from boss_agent_cli.api.models import JobDetail, JobItem
from boss_agent_cli.commands.friend_list_pages import collect_friend_list_items
from boss_agent_cli.display import error_contract_for_code
from boss_agent_cli.rag_reply.models import (
	AuditLogRecord,
	ConversationRecord,
	JobRecord,
	MessageRecord,
	RecruiterRecord,
	new_id,
	utc_now_iso,
)
from boss_agent_cli.rag_reply.store import RagReplyStore

_RECENT_FRIEND_LIST_PAGES = 1
_RECENT_CONVERSATION_LIMIT = 5


class BossPlatformProtocol(Protocol):
	def close(self) -> None:
		...

	def is_success(self, response: dict[str, Any]) -> bool:
		...

	def unwrap_data(self, response: dict[str, Any]) -> Any:
		...

	def parse_error(self, response: dict[str, Any]) -> tuple[str, str]:
		...

	def search_jobs(self, query: str, **filters: Any) -> dict[str, Any]:
		...

	def recommend_jobs(self, page: int = 1) -> dict[str, Any]:
		...

	def job_detail(self, job_id: str) -> dict[str, Any]:
		...

	def job_card(self, security_id: str, lid: str = "") -> dict[str, Any]:
		...

	def friend_list(self, page: int = 1) -> dict[str, Any]:
		...

	def chat_history(self, gid: str, security_id: str, page: int = 1, count: int = 20) -> dict[str, Any]:
		...


@dataclass(slots=True)
class SyncJobsResult:
	sync_batch_id: str
	source: str
	synced_job_ids: list[str]
	count: int


@dataclass(slots=True)
class SyncMessagesResult:
	import_batch_id: str
	conversation_ids: list[str]
	message_ids: list[str]
	count: int


@dataclass(slots=True)
class RecentConversationTarget:
	conversation_id: str
	security_id: str
	job_id: str
	recruiter_name: str
	company: str
	title: str
	last_message: str
	last_message_at: str | None
	unread_count: int


class BossAutomationError(Exception):
	"""Structured read-only adapter error."""

	def __init__(
		self,
		code: str,
		message: str,
		*,
		recoverable: bool = False,
		recovery_action: str | None = None,
		hints: dict[str, Any] | None = None,
	) -> None:
		super().__init__(message)
		self.code = code
		self.message = message
		self.recoverable = recoverable
		self.recovery_action = recovery_action
		self.hints = hints


class BossAutomationAdapter:
	"""Bridge upstream Boss read-only capabilities into the local SQLite workflow."""

	def __init__(self, *, platform: BossPlatformProtocol, store: RagReplyStore) -> None:
		self.platform = platform
		self.store = store

	def close(self) -> None:
		self.platform.close()

	def __enter__(self) -> "BossAutomationAdapter":
		return self

	def __exit__(self, exc_type, exc, tb) -> None:
		self.close()

	def sync_jobs(self, *, query: str | None = None) -> SyncJobsResult:
		sync_batch_id = new_id("syncjobs")
		raw = self.platform.search_jobs(query or "", page=1) if query else self.platform.recommend_jobs(page=1)
		data = self._unwrap_or_raise(raw, fallback_message="职位列表获取失败")
		job_list = data.get("jobList") or []
		job_ids: list[str] = []
		for raw_item in job_list:
			if not isinstance(raw_item, dict):
				continue
			record = self._job_record_from_raw(raw_item)
			if record is None:
				continue
			self.store.save_job(record)
			job_ids.append(record.job_id)
		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type="boss_jobs_synced",
				entity_type="sync_batch",
				entity_id=sync_batch_id,
				payload={
					"source": "boss_sync",
					"query": query,
					"job_ids": job_ids,
					"count": len(job_ids),
				},
			)
		)
		return SyncJobsResult(
			sync_batch_id=sync_batch_id,
			source="search_jobs" if query else "recommend_jobs",
			synced_job_ids=job_ids,
			count=len(job_ids),
		)

	def sync_messages(self, *, conversation_id: str | None = None) -> SyncMessagesResult:
		# V1 read-only sync is intentionally scoped to recent conversations.
		# The BOSS friend-list endpoint does not reliably expose hasMore, and
		# deep pagination can stall the workflow before any message history is read.
		items, error = collect_friend_list_items(self.platform, max_pages=_RECENT_FRIEND_LIST_PAGES)
		if error is not None:
			self._raise_platform_error(error, fallback_message="沟通列表获取失败")

		import_batch_id = new_id("bosssync")
		conversation_ids: list[str] = []
		message_ids: list[str] = []
		seen_message_ids: set[str] = set()
		selected_items = self._select_friend_items(items, conversation_id)
		if conversation_id is None:
			selected_items = selected_items[:_RECENT_CONVERSATION_LIMIT]

		for raw_item in selected_items:
			if not isinstance(raw_item, dict):
				continue
			conversation = self._save_conversation_from_friend_item(raw_item)
			if conversation.conversation_id not in conversation_ids:
				conversation_ids.append(conversation.conversation_id)

			gid = str(conversation.state.get("gid", ""))
			security_id = str(conversation.state.get("security_id", ""))
			if not gid or not security_id:
				continue

			raw_history = self.platform.chat_history(gid, security_id, page=1, count=50)
			history = self._unwrap_or_raise(raw_history, fallback_message="聊天记录获取失败")
			messages = history.get("messages") or history.get("historyMsgList") or []
			for index, raw_message in enumerate(messages):
				record = self._message_record_from_raw(
					raw_message,
					conversation=conversation,
					gid=gid,
					import_batch_id=import_batch_id,
					index=index,
				)
				if record is None:
					continue
				if record.message_id in seen_message_ids:
					continue
				seen_message_ids.add(record.message_id)
				self.store.save_message(record)
				message_ids.append(record.message_id)

		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type="boss_messages_synced",
				entity_type="sync_batch",
				entity_id=import_batch_id,
				payload={
					"source": "boss_sync",
					"conversation_ids": conversation_ids,
					"message_ids": message_ids,
					"count": len(message_ids),
				},
			)
		)
		return SyncMessagesResult(
			import_batch_id=import_batch_id,
			conversation_ids=conversation_ids,
			message_ids=message_ids,
			count=len(message_ids),
		)

	def list_recent_targets(self, *, limit: int = _RECENT_CONVERSATION_LIMIT) -> list[RecentConversationTarget]:
		"""Return recent Boss conversation targets without pulling full chat history."""
		items, error = collect_friend_list_items(self.platform, max_pages=_RECENT_FRIEND_LIST_PAGES)
		if error is not None:
			self._raise_platform_error(error, fallback_message="沟通列表获取失败")

		targets: list[RecentConversationTarget] = []
		for raw_item in items[: max(limit, 0)]:
			if not isinstance(raw_item, dict):
				continue
			conversation = self._save_conversation_from_friend_item(raw_item)
			targets.append(
				RecentConversationTarget(
					conversation_id=conversation.conversation_id,
					security_id=str(conversation.state.get("security_id") or ""),
					job_id=str(conversation.job_id or ""),
					recruiter_name=str(raw_item.get("name") or raw_item.get("friendName") or ""),
					company=str(raw_item.get("brandName") or raw_item.get("companyName") or ""),
					title=str(raw_item.get("title") or ""),
					last_message=str(raw_item.get("lastMsg") or ""),
					last_message_at=conversation.last_message_at,
					unread_count=int(raw_item.get("unreadMsgCount") or 0),
				)
			)
		return targets

	def _job_record_from_raw(self, raw_item: dict[str, Any]) -> JobRecord | None:
		job_item = JobItem.from_api(raw_item)
		if not job_item.job_id:
			return None

		detail_payload = self._load_job_detail(job_item.job_id, job_item.security_id)
		job_detail = JobDetail.from_api(detail_payload) if detail_payload else None

		title = (job_detail.title if job_detail else "") or job_item.title
		company = (job_detail.company if job_detail else "") or job_item.company
		salary = (job_detail.salary if job_detail else "") or job_item.salary
		city = (job_detail.city if job_detail else "") or job_item.city
		description = (job_detail.description if job_detail else "") or ""

		return JobRecord(
			job_id=job_item.job_id,
			security_id=job_item.security_id,
			title=title,
			company=company,
			salary=salary,
			city=city,
			summary=self._build_job_summary(title, company, salary, city, description),
			detail=detail_payload or raw_item,
			source="boss_sync",
		)

	def _load_job_detail(self, job_id: str, security_id: str) -> dict[str, Any]:
		try:
			raw = self.platform.job_detail(job_id)
		except NotImplementedError:
			raw = None
		if isinstance(raw, dict) and self.platform.is_success(raw):
			data = self.platform.unwrap_data(raw) or {}
			if data.get("jobInfo"):
				return data

		if not security_id:
			return {}
		try:
			card_raw = self.platform.job_card(security_id)
		except (AttributeError, NotImplementedError):
			return {}
		if not self.platform.is_success(card_raw):
			return {}
		card_data = self.platform.unwrap_data(card_raw) or {}
		job_card = card_data.get("jobCard") or {}
		if not job_card:
			return {}
		return {
			"jobInfo": job_card,
			"brandComInfo": {"brandName": job_card.get("brandName", "")},
			"jobDetail": job_card.get("postDescription", ""),
			"bossInfo": {
				"name": job_card.get("bossName", ""),
				"title": job_card.get("bossTitle", ""),
				"activeTimeDesc": job_card.get("activeTimeDesc", "离线"),
			},
		}

	def _save_conversation_from_friend_item(self, raw_item: dict[str, Any]) -> ConversationRecord:
		security_id = str(raw_item.get("securityId") or "")
		uid = str(raw_item.get("uid") or "")
		friend_id = str(raw_item.get("friendId") or raw_item.get("friend_id") or uid)
		gid = str(raw_item.get("uid") or raw_item.get("friendId") or raw_item.get("encryptUid") or "")
		job_id = str(raw_item.get("encryptJobId") or raw_item.get("jobId") or "")
		encrypt_boss_id = str(raw_item.get("encryptBossId") or raw_item.get("bossId") or "")
		recruiter_id = self._recruiter_id(raw_item)
		recruiter_name = str(raw_item.get("name") or raw_item.get("friendName") or "")
		company = str(raw_item.get("brandName") or raw_item.get("companyName") or "")
		title = str(raw_item.get("title") or "")

		recruiter = RecruiterRecord(
			recruiter_id=recruiter_id,
			display_name=recruiter_name,
			company=company,
			profile=dict(raw_item),
		)
		self.store.save_recruiter(recruiter)

		conversation = ConversationRecord(
			conversation_id=self._conversation_id(raw_item),
			source="boss_sync",
			job_id=job_id or None,
			recruiter_id=recruiter_id,
			channel="boss",
			last_message_at=self._iso_from_millis(raw_item.get("lastTS")),
			state={
				"security_id": security_id,
				"gid": gid,
				"uid": uid,
				"friend_id": friend_id,
				"encrypt_boss_id": encrypt_boss_id,
				"recruiter_name": recruiter_name,
				"recruiter_id": recruiter_id,
				"last_msg": raw_item.get("lastMsg"),
				"title": title,
				"company": company,
				"unread_count": raw_item.get("unreadMsgCount") or 0,
			},
			updated_at=utc_now_iso(),
		)
		self.store.save_conversation(conversation)
		return conversation

	def _message_record_from_raw(
		self,
		raw_message: Any,
		*,
		conversation: ConversationRecord,
		gid: str,
		import_batch_id: str,
		index: int,
	) -> MessageRecord | None:
		if not isinstance(raw_message, dict):
			return None
		from_uid = str((raw_message.get("from") or {}).get("uid", ""))
		direction = "inbound" if from_uid == gid else "outbound"
		if direction != "inbound":
			return None

		body = raw_message.get("body") if isinstance(raw_message.get("body"), dict) else {}
		message_text = str(raw_message.get("text") or body.get("text") or body.get("content") or "")
		if not message_text.strip():
			return None
		raw_id = raw_message.get("id") or raw_message.get("msgId") or raw_message.get("messageId")
		message_id_suffix = self._message_identity_suffix(raw_message, fallback_index=index)
		return MessageRecord(
			message_id=f"boss_msg_{conversation.state.get('security_id', 'unknown')}_{message_id_suffix}",
			conversation_id=conversation.conversation_id,
			message_text=message_text,
			direction=direction,
			message_type=str(raw_message.get("type") or "text"),
			job_id=conversation.job_id,
			recruiter_id=conversation.recruiter_id,
			source="boss_sync",
			raw=dict(raw_message),
			import_batch_id=import_batch_id,
			created_at=self._iso_from_millis(raw_message.get("time")),
		)

	def _message_identity_suffix(self, raw_message: dict[str, Any], *, fallback_index: int) -> str:
		raw_id = raw_message.get("id") or raw_message.get("msgId") or raw_message.get("messageId")
		if raw_id not in (None, ""):
			return str(raw_id)
		payload = json.dumps(raw_message, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
		digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
		return f"{raw_message.get('time') or fallback_index}_{digest}"

	def _select_friend_items(self, items: list[dict[str, Any]], conversation_id: str | None) -> list[dict[str, Any]]:
		if conversation_id is None:
			return items
		matched = [
			item
			for item in items
			if self._conversation_id(item) == conversation_id or str(item.get("securityId") or "") == conversation_id
		]
		if matched:
			return matched

		stored = self.store.get_conversation(conversation_id)
		if stored is not None:
			target_security_id = str(stored.state.get("security_id") or "")
			matched = [
				item
				for item in items
				if str(item.get("securityId") or "") == target_security_id
			]
		if not matched:
			raise BossAutomationError(
				"CONVERSATION_NOT_FOUND",
				f"Unknown conversation_id={conversation_id}",
				recoverable=False,
			)
		return matched

	def _unwrap_or_raise(self, response: dict[str, Any], *, fallback_message: str) -> dict[str, Any]:
		if not self.platform.is_success(response):
			self._raise_platform_error(response, fallback_message=fallback_message)
		data = self.platform.unwrap_data(response) or {}
		return data if isinstance(data, dict) else {}

	def _raise_platform_error(self, response: dict[str, Any], *, fallback_message: str) -> None:
		code, message = self.platform.parse_error(response)
		recoverable, recovery_action = error_contract_for_code(code)
		raise BossAutomationError(
			code,
			message or fallback_message,
			recoverable=recoverable,
			recovery_action=recovery_action,
		)

	@staticmethod
	def _conversation_id(raw_item: dict[str, Any]) -> str:
		security_id = str(raw_item.get("securityId") or "")
		if security_id:
			return f"boss_conv_{security_id}"
		gid = str(raw_item.get("uid") or raw_item.get("encryptUid") or "")
		return f"boss_conv_{gid or 'unknown'}"

	@staticmethod
	def _recruiter_id(raw_item: dict[str, Any]) -> str:
		gid = str(raw_item.get("uid") or raw_item.get("encryptUid") or "")
		security_id = str(raw_item.get("securityId") or "")
		return f"boss_recruiter_{gid or security_id or 'unknown'}"

	@staticmethod
	def _build_job_summary(title: str, company: str, salary: str, city: str, description: str) -> str:
		parts = [part for part in (title, company, salary, city) if part]
		prefix = " | ".join(parts)
		if not description:
			return prefix
		snippet = " ".join(str(description).split())
		if len(snippet) > 160:
			snippet = f"{snippet[:157]}..."
		return f"{prefix} | {snippet}" if prefix else snippet

	@staticmethod
	def _iso_from_millis(value: Any) -> str:
		if isinstance(value, (int, float)):
			return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
		return utc_now_iso()
