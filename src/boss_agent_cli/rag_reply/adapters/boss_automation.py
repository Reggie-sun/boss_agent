"""Read-only Boss automation adapter for the local RAG reply workflow."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from boss_agent_cli.api.models import JobDetail, JobItem
from boss_agent_cli.commands.friend_list_pages import MAX_FRIEND_LIST_PAGES, collect_friend_list_items
from boss_agent_cli.display import error_contract_for_code
from boss_agent_cli.pipeline_state import build_pipeline_items, select_read_no_reply_candidates
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
_CONVERSATION_SYNC_BATCH_SIZE = 5
_SYNC_PRIORITY_VERSION = 2
_CANDIDATE_OUTBOUND_LAST_MESSAGE_PREFIXES = (
	"我是候选人的求职助理 Agent",
	"您好，我是候选人的agent",
	"您好，我是候选人的 Agent",
	"您好，我对这份工作非常感兴趣",
	"您好，我对这个岗位比较感兴趣",
	"可以的，我这边通过 BOSS 直聘发送附件简历给您",
	"您的附件简历",
)


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
		import_batch_id = new_id("bosssync")
		conversation_ids: list[str] = []
		message_ids: list[str] = []
		seen_message_ids: set[str] = set()
		cursor_payload: dict[str, Any] = {}
		if conversation_id is None:
			page, offset, priority = self._message_sync_cursor()
			items, error, page_payload = self._load_friend_list_page(page)
			if error is not None:
				self._raise_platform_error(error, fallback_message="沟通列表获取失败")
			selected_items, cursor_payload = self._select_friend_item_batch(
				items,
				page=page,
				offset=offset,
				has_more=page_payload.get("has_more"),
				priority=priority,
			)
		else:
			items, error = collect_friend_list_items(self.platform, max_pages=MAX_FRIEND_LIST_PAGES)
			if error is not None:
				self._raise_platform_error(error, fallback_message="沟通列表获取失败")
			selected_items = self._select_friend_items(items, conversation_id)

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

		payload: dict[str, Any] = {
			"source": "boss_sync",
			"conversation_ids": conversation_ids,
			"message_ids": message_ids,
			"count": len(message_ids),
		}
		if cursor_payload:
			payload.update(cursor_payload)

		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type="boss_messages_synced",
				entity_type="sync_batch",
				entity_id=import_batch_id,
				payload=payload,
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

		unique_limit = max(limit, 0)
		if unique_limit == 0:
			return []

		targets_by_conversation_id: dict[str, RecentConversationTarget] = {}
		target_order: list[str] = []
		for raw_item in items:
			if not isinstance(raw_item, dict):
				continue
			conversation = self._save_conversation_from_friend_item(raw_item)
			state = conversation.state if isinstance(conversation.state, dict) else {}
			recruiter = self.store.get_recruiter(str(conversation.recruiter_id or "")) if conversation.recruiter_id else None
			if conversation.conversation_id not in targets_by_conversation_id:
				if len(target_order) >= unique_limit:
					continue
				target_order.append(conversation.conversation_id)
			targets_by_conversation_id[conversation.conversation_id] = RecentConversationTarget(
				conversation_id=conversation.conversation_id,
				security_id=str(state.get("security_id") or ""),
				job_id=str(conversation.job_id or ""),
				recruiter_name=str(state.get("recruiter_name") or (recruiter.display_name if recruiter else "") or ""),
				company=str(state.get("company") or (recruiter.company if recruiter else "") or ""),
				title=str(state.get("title") or ""),
				last_message=str(state.get("last_msg") or ""),
				last_message_at=conversation.last_message_at,
				unread_count=int(state.get("unread_count") or 0),
			)
		return [targets_by_conversation_id[conversation_id] for conversation_id in target_order]

	def list_pipeline_candidates(
		self,
		*,
		now_ts_ms: int | None = None,
		stale_days: int = 3,
		limit: int = _RECENT_CONVERSATION_LIMIT,
	) -> list[dict[str, object]]:
		"""Return actionable pipeline candidates derived from the Boss conversation list."""
		items, error = collect_friend_list_items(self.platform, max_pages=_RECENT_FRIEND_LIST_PAGES)
		if error is not None:
			self._raise_platform_error(error, fallback_message="沟通列表获取失败")

		raw_by_security_id = {
			str(item.get("securityId") or ""): item
			for item in items
			if isinstance(item, dict)
		}
		pipeline_items = build_pipeline_items(
			chat_items=[item for item in items if isinstance(item, dict)],
			interview_items=[],
			now_ts_ms=now_ts_ms or int(time.time() * 1000),
			stale_days=stale_days,
		)
		candidates: list[dict[str, object]] = []
		for item in select_read_no_reply_candidates(pipeline_items)[: max(limit, 0)]:
			candidate = dict(item)
			raw_item = raw_by_security_id.get(str(item.get("security_id") or ""))
			if isinstance(raw_item, dict):
				conversation = self._save_conversation_from_friend_item(raw_item)
				candidate.update(
					{
						"conversation_id": conversation.conversation_id,
						"gid": str(conversation.state.get("gid") or ""),
						"friend_id": str(conversation.state.get("friend_id") or ""),
						"uid": str(conversation.state.get("uid") or ""),
						"encrypt_boss_id": str(conversation.state.get("encrypt_boss_id") or ""),
						"recruiter_name": str(conversation.state.get("recruiter_name") or ""),
						"recruiter_id": str(conversation.recruiter_id or ""),
					}
				)
			candidates.append(candidate)
		return candidates

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
		message_text = self._message_text_from_raw(raw_message, body)
		if not message_text.strip():
			return None
		message_id_suffix = self._message_identity_suffix(raw_message, fallback_index=index)
		conversation_key = str(conversation.conversation_id).removeprefix("boss_conv_")
		return MessageRecord(
			message_id=f"boss_msg_{conversation_key or 'unknown'}_{message_id_suffix}",
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
		raw_id = (
			raw_message.get("id")
			or raw_message.get("msgId")
			or raw_message.get("messageId")
			or raw_message.get("mid")
		)
		if raw_id not in (None, ""):
			return str(raw_id)
		payload = json.dumps(raw_message, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
		digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
		return f"{raw_message.get('time') or fallback_index}_{digest}"

	@staticmethod
	def _message_text_from_raw(raw_message: dict[str, Any], body: dict[str, Any]) -> str:
		dialog = body.get("dialog") if isinstance(body.get("dialog"), dict) else {}
		return str(
			raw_message.get("text")
			or body.get("text")
			or body.get("content")
			or dialog.get("text")
			or ""
		)

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

	def _dedupe_friend_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
		selected: list[dict[str, Any]] = []
		seen: set[str] = set()

		for item in items:
			if not isinstance(item, dict):
				continue
			key = self._conversation_id(item)
			if key in seen:
				continue
			seen.add(key)
			selected.append(item)

		return selected

	def _load_friend_list_page(
		self,
		page: int,
	) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
		raw = self.platform.friend_list(page=page)
		if not self.platform.is_success(raw):
			return [], raw, {}
		data = self.platform.unwrap_data(raw) or {}
		if not isinstance(data, dict):
			return [], None, {"page": page, "has_more": False, "page_count": 0}
		raw_items = data.get("result") or data.get("friendList") or []
		items = [item for item in raw_items if isinstance(item, dict)]
		return items, None, {
			"page": page,
			"has_more": data.get("hasMore"),
			"page_count": len(items),
		}

	def _message_sync_cursor(self) -> tuple[int, int, str]:
		for entry in reversed(self.store.list_audit_logs()):
			if entry.event_type != "boss_messages_synced":
				continue
			cursor = entry.payload.get("next_cursor")
			if not isinstance(cursor, dict):
				continue
			page = self._positive_int(cursor.get("page"), default=1)
			if cursor.get("priority_version") != _SYNC_PRIORITY_VERSION:
				offset = 0
				priority = "priority"
			else:
				offset = self._non_negative_int(cursor.get("offset"), default=0)
				priority = str(cursor.get("priority") or "priority")
			if page > MAX_FRIEND_LIST_PAGES:
				return 1, 0, "priority"
			return page, offset, priority
		return 1, 0, "priority"

	def _select_friend_item_batch(
		self,
		items: list[dict[str, Any]],
		*,
		page: int,
		offset: int,
		has_more: Any,
		priority: str,
	) -> tuple[list[dict[str, Any]], dict[str, Any]]:
		unique_items = self._dedupe_friend_items(items)
		priority_items = [item for item in unique_items if self._priority_friend_item(item)]
		if priority_items:
			normal_resume_offset = offset if priority == "normal" else 0
			return self._select_priority_friend_item_batch(
				priority_items,
				page=page,
				offset=0,
				has_more=has_more,
				normal_resume_offset=normal_resume_offset,
			)
		safe_offset = max(offset, 0)
		selected_items = unique_items[safe_offset : safe_offset + _CONVERSATION_SYNC_BATCH_SIZE]
		next_offset = safe_offset + _CONVERSATION_SYNC_BATCH_SIZE
		next_priority = "normal"
		if next_offset < len(unique_items):
			next_page = page
		elif has_more is not False and page < MAX_FRIEND_LIST_PAGES:
			next_page = page + 1
			next_offset = 0
			next_priority = "priority"
		else:
			next_page = 1
			next_offset = 0
			next_priority = "priority"
		return selected_items, {
			"sync_cursor": {
				"page": page,
				"offset": safe_offset,
				"priority": "normal",
				"priority_version": _SYNC_PRIORITY_VERSION,
				"batch_size": _CONVERSATION_SYNC_BATCH_SIZE,
				"page_count": len(unique_items),
				"has_more": has_more,
			},
			"next_cursor": {
				"page": next_page,
				"offset": next_offset,
				"priority": next_priority,
				"priority_version": _SYNC_PRIORITY_VERSION,
			},
		}

	def _select_priority_friend_item_batch(
		self,
		priority_items: list[dict[str, Any]],
		*,
		page: int,
		offset: int,
		has_more: Any,
		normal_resume_offset: int = 0,
	) -> tuple[list[dict[str, Any]], dict[str, Any]]:
		safe_offset = max(offset, 0)
		selected_items = priority_items[safe_offset : safe_offset + _CONVERSATION_SYNC_BATCH_SIZE]
		return selected_items, {
			"sync_cursor": {
				"page": page,
				"offset": safe_offset,
				"priority": "priority",
				"priority_version": _SYNC_PRIORITY_VERSION,
				"batch_size": _CONVERSATION_SYNC_BATCH_SIZE,
				"page_count": len(priority_items),
				"has_more": has_more,
			},
			"next_cursor": {
				"page": page,
				"offset": max(normal_resume_offset, 0),
				"priority": "normal",
				"priority_version": _SYNC_PRIORITY_VERSION,
			},
		}

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
		gid = str(
			raw_item.get("friendId")
			or raw_item.get("friend_id")
			or raw_item.get("uid")
			or raw_item.get("encryptUid")
			or ""
		)
		if gid:
			return f"boss_conv_{gid}"
		security_id = str(raw_item.get("securityId") or "")
		return f"boss_conv_{security_id or 'unknown'}"

	@staticmethod
	def _recruiter_id(raw_item: dict[str, Any]) -> str:
		gid = str(raw_item.get("uid") or raw_item.get("encryptUid") or "")
		security_id = str(raw_item.get("securityId") or "")
		return f"boss_recruiter_{gid or security_id or 'unknown'}"

	@staticmethod
	def _unread_count(raw_item: dict[str, Any]) -> int:
		try:
			return int(raw_item.get("unreadMsgCount") or 0)
		except (TypeError, ValueError):
			return 0

	def _priority_friend_item(self, raw_item: dict[str, Any]) -> bool:
		if self._unread_count(raw_item) > 0 and self._friend_item_last_message_unsynced(raw_item):
			return True
		last_msg = self._friend_item_last_message_text(raw_item)
		if last_msg:
			return (
				not self._looks_like_candidate_outbound_last_message(last_msg)
				and self._friend_item_last_message_unsynced(raw_item)
			)
		return (
			self._friend_item_last_from_recruiter(raw_item)
			and self._friend_item_last_message_unsynced(raw_item)
		)

	def _friend_item_last_message_text(self, raw_item: dict[str, Any]) -> str:
		last_info = raw_item.get("lastMessageInfo") if isinstance(raw_item.get("lastMessageInfo"), dict) else {}
		return str(raw_item.get("lastMsg") or last_info.get("showText") or "").strip()

	def _friend_item_last_message_unsynced(self, raw_item: dict[str, Any]) -> bool:
		last_info = raw_item.get("lastMessageInfo") if isinstance(raw_item.get("lastMessageInfo"), dict) else {}
		message_id = str(last_info.get("msgId") or raw_item.get("msgId") or "").strip()
		if message_id:
			conversation_key = self._conversation_id(raw_item).removeprefix("boss_conv_")
			return self.store.get_message(f"boss_msg_{conversation_key or 'unknown'}_{message_id}") is None
		last_ts = raw_item.get("lastTS") or last_info.get("msgTime")
		if isinstance(last_ts, (int, float)):
			stored = self.store.get_conversation(self._conversation_id(raw_item))
			if stored is None:
				return True
			return stored.last_message_at != self._iso_from_millis(last_ts)
		return True

	@staticmethod
	def _friend_item_last_from_recruiter(raw_item: dict[str, Any]) -> bool:
		last_info = raw_item.get("lastMessageInfo") if isinstance(raw_item.get("lastMessageInfo"), dict) else {}
		from_id = str(last_info.get("fromId") or "")
		if not from_id:
			return False
		recruiter_ids = {
			str(raw_item.get("uid") or ""),
			str(raw_item.get("friendId") or ""),
			str(raw_item.get("friend_id") or ""),
			str(raw_item.get("encryptUid") or ""),
		}
		return from_id in {value for value in recruiter_ids if value}

	@staticmethod
	def _looks_like_candidate_outbound_last_message(last_msg: str) -> bool:
		return any(
			last_msg.startswith(prefix)
			for prefix in _CANDIDATE_OUTBOUND_LAST_MESSAGE_PREFIXES
		)

	@staticmethod
	def _positive_int(value: Any, *, default: int) -> int:
		try:
			parsed = int(value)
		except (TypeError, ValueError):
			return default
		return parsed if parsed > 0 else default

	@staticmethod
	def _non_negative_int(value: Any, *, default: int) -> int:
		try:
			parsed = int(value)
		except (TypeError, ValueError):
			return default
		return parsed if parsed >= 0 else default

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
