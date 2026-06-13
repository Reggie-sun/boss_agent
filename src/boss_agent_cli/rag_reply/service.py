"""Orchestration service for the Boss RAG draft workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from boss_agent_cli.rag_reply.classifier import ClassificationResult, classify_message
from boss_agent_cli.rag_reply.clipboard import copy_text
from boss_agent_cli.rag_reply.models import (
	ApprovalEventRecord,
	AuditLogRecord,
	DraftRecord,
	MessageRecord,
	RagCallRecord,
	new_id,
)
from boss_agent_cli.rag_reply.policy import ApprovalDecision, build_approval_decision
from boss_agent_cli.rag_reply.question_builder import build_answer_objective, build_rag_question
from boss_agent_cli.rag_reply.store import RagReplyStore


class RagAnswerProtocol(Protocol):
	ok: bool
	answer: str
	citations: list[dict[str, object]]
	reasoning_summary: dict[str, object] | None
	raw_response: dict[str, object] | None
	error_message: str | None
	audit_status: str
	send_allowed: bool
	approval_required: bool


class RagAdapterProtocol(Protocol):
	def answer(self, *, rag_question: str, session_id: str, mode: str = "accurate") -> RagAnswerProtocol:
		...


@dataclass(slots=True)
class ApprovalResult:
	event: ApprovalEventRecord
	copied_to_clipboard: bool
	draft: DraftRecord


class BossRagReplyService:
	"""Run the local message -> draft -> approval pipeline."""

	def __init__(self, *, store: RagReplyStore, rag_adapter: RagAdapterProtocol) -> None:
		self.store = store
		self.rag_adapter = rag_adapter

	def create_draft_for_message(self, message_id: str) -> DraftRecord:
		message = self.store.get_message(message_id)
		if message is None:
			raise LookupError(f"Unknown message_id={message_id}")
		classification = classify_message(message.message_text)
		decision = build_approval_decision(classification.intent, classification.risk_labels)
		draft = self._build_draft(message, classification, decision)
		self.store.save_draft(draft)
		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type=draft.audit_status,
				entity_type="draft",
				entity_id=draft.draft_id,
				payload={
					"message_id": message.message_id,
					"intent": draft.intent,
					"risk_labels": draft.risk_labels,
				},
			)
		)
		return draft

	def create_drafts_for_all_messages(self) -> list[DraftRecord]:
		return [self.create_draft_for_message(message.message_id) for message in self.store.list_messages()]

	def approve_draft(self, draft_id: str, *, copy_to_clipboard: bool = False) -> ApprovalResult:
		draft = self.store.get_draft(draft_id)
		if draft is None:
			raise LookupError(f"Unknown draft_id={draft_id}")
		copied = copy_text(draft.draft_text) if copy_to_clipboard and draft.draft_text else False
		event = ApprovalEventRecord.new(
			draft_id=draft_id,
			action="approved",
			copied_to_clipboard=copied,
		)
		self.store.save_approval_event(event)
		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type="approved",
				entity_type="draft",
				entity_id=draft_id,
				payload={"copied_to_clipboard": copied},
			)
		)
		return ApprovalResult(event=event, copied_to_clipboard=copied, draft=draft)

	def _build_draft(
		self,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
	) -> DraftRecord:
		if classification.requires_rag:
			return self._build_rag_backed_draft(message, classification, decision)
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=self._local_draft_text(message, classification.intent),
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={"source": "local_policy", "reason": classification.classifier_source},
			approval_required=decision.approval_required,
			send_allowed=decision.send_allowed,
			audit_status=decision.audit_status,
		)

	def _build_rag_backed_draft(
		self,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
	) -> DraftRecord:
		job_summary = None
		if message.job_id:
			job = self.store.get_job(message.job_id)
			job_summary = None if job is None else job.summary
		rag_session_id = self._build_rag_session_id(message)
		rag_question = build_rag_question(
			message.message_text,
			job_summary,
			build_answer_objective(classification.intent),
		)
		rag_result = self.rag_adapter.answer(
			rag_question=rag_question,
			session_id=rag_session_id,
		)
		self.store.save_rag_call(
			RagCallRecord.new(
				conversation_id=message.conversation_id,
				draft_id=None,
				request={"question": rag_question, "session_id": rag_session_id, "message_id": message.message_id},
				status=rag_result.audit_status,
				response=rag_result.raw_response or {"error_message": rag_result.error_message},
			)
		)
		if not rag_result.ok:
			return DraftRecord.new(
				conversation_id=message.conversation_id,
				source_message_id=message.message_id,
				draft_text="",
				intent=classification.intent,
				risk_labels=decision.risk_labels,
				evidence={
					"source": "enterprise_rag",
					"error_message": rag_result.error_message,
				},
				approval_required=True,
				send_allowed=False,
				audit_status="rag_failed",
				rag_session_id=rag_session_id,
			)
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=rag_result.answer,
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={
				"source": "enterprise_rag",
				"citations": rag_result.citations,
				"reasoning_summary": rag_result.reasoning_summary,
			},
			approval_required=decision.approval_required,
			send_allowed=False,
			audit_status="draft_created",
			rag_session_id=rag_session_id,
		)

	@staticmethod
	def _build_rag_session_id(message: MessageRecord) -> str:
		"""Keep remote session ids compact to avoid upstream protocol issues."""
		conversation_key = hashlib.sha1(message.conversation_id.encode("utf-8")).hexdigest()[:12]
		message_key = hashlib.sha1(message.message_id.encode("utf-8")).hexdigest()[:12]
		return f"boss-rag-{conversation_key}-{message_key}"

	@staticmethod
	def _local_draft_text(message: MessageRecord, intent: str) -> str:
		if intent == "job_detail_question":
			return "我想进一步了解这个岗位的核心职责、团队协作方式，以及前 3 个月的重点目标。"
		if intent == "smalltalk":
			return "您好，已收到您的消息，感谢联系。"
		if intent in {"contact_exchange", "salary_or_offer", "availability_or_schedule", "interview_time", "resignation_status", "personal_status", "unsafe_or_unclear"}:
			return ""
		return message.message_text
