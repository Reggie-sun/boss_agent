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


class FallbackAdapterProtocol(Protocol):
	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_error: str | None,
	) -> RagAnswerProtocol:
		...


class AgentAnswerAdapterProtocol(Protocol):
	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_answer: str,
		citations: list[dict[str, object]] | None = None,
	) -> RagAnswerProtocol:
		...


@dataclass(slots=True)
class ApprovalResult:
	event: ApprovalEventRecord
	copied_to_clipboard: bool
	draft: DraftRecord


class BossRagReplyService:
	"""Run the local message -> draft -> approval pipeline."""

	def __init__(
		self,
		*,
		store: RagReplyStore,
		rag_adapter: RagAdapterProtocol,
		fallback_adapter: FallbackAdapterProtocol | None = None,
		agent_answer_adapter: AgentAnswerAdapterProtocol | None = None,
	) -> None:
		self.store = store
		self.rag_adapter = rag_adapter
		self.fallback_adapter = fallback_adapter
		self.agent_answer_adapter = agent_answer_adapter

	def create_draft_for_message(self, message_id: str) -> DraftRecord:
		message = self.store.get_message(message_id)
		if message is None:
			raise LookupError(f"Unknown message_id={message_id}")
		classification = classify_message(message.message_text)
		decision = build_approval_decision(classification.intent, classification.risk_labels)
		draft = self._build_draft(message, classification, decision)
		self.store.save_draft(draft)
		self._save_assistant_memory_message(draft)
		self.store.append_audit_log(
			AuditLogRecord.new(
				event_type=draft.audit_status,
				entity_type="draft",
				entity_id=draft.draft_id,
				payload={
					"message_id": message.message_id,
					"intent": draft.intent,
					"risk_labels": draft.risk_labels,
					"evidence_source": draft.evidence.get("source"),
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
		job_summary = self._resolve_job_summary(message)
		rag_session_id = self._build_rag_session_id(message)
		rag_question = build_rag_question(
			message.message_text,
			job_summary,
			build_answer_objective(classification.intent, message.message_text),
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
			fallback_draft = self._build_fallback_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=job_summary,
				rag_session_id=rag_session_id,
				rag_error_message=rag_result.error_message,
			)
			if fallback_draft is not None:
				return fallback_draft
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
		agent_answer = self._build_agent_answer(
			message=message,
			classification=classification,
			job_summary=job_summary,
			rag_answer=rag_result.answer,
			citations=rag_result.citations,
		)
		draft_text = rag_result.answer
		evidence_source = "enterprise_rag"
		reasoning_summary = rag_result.reasoning_summary
		evidence: dict[str, object] = {
			"source": evidence_source,
			"citations": rag_result.citations,
			"reasoning_summary": reasoning_summary,
		}
		if agent_answer is not None and agent_answer.ok and agent_answer.answer.strip():
			draft_text = agent_answer.answer
			evidence_source = "boss_agent_ai"
			reasoning_summary = self._merge_reasoning_summaries(
				rag_reasoning=rag_result.reasoning_summary,
				agent_reasoning=agent_answer.reasoning_summary,
			)
			evidence = {
				"source": evidence_source,
				"upstream_source": "enterprise_rag",
				"grounded_answer": rag_result.answer,
				"citations": rag_result.citations,
				"reasoning_summary": reasoning_summary,
				"agent_raw_response": agent_answer.raw_response,
			}
		elif agent_answer is not None and agent_answer.error_message:
			evidence["agent_error_message"] = agent_answer.error_message
		draft = DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=draft_text,
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence=evidence,
			approval_required=decision.approval_required,
			send_allowed=False,
			audit_status="draft_created",
			rag_session_id=rag_session_id,
		)
		return draft

	def _build_agent_answer(
		self,
		*,
		message: MessageRecord,
		classification: ClassificationResult,
		job_summary: str | None,
		rag_answer: str,
		citations: list[dict[str, object]],
	) -> RagAnswerProtocol | None:
		if self.agent_answer_adapter is None:
			return None
		return self.agent_answer_adapter.answer(
			message_text=message.message_text,
			intent=classification.intent,
			job_summary=job_summary,
			rag_answer=rag_answer,
			citations=citations,
		)

	def _build_fallback_draft(
		self,
		*,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
		job_summary: str | None,
		rag_session_id: str,
		rag_error_message: str | None,
	) -> DraftRecord | None:
		if self.fallback_adapter is None:
			return self._build_agent_template_fallback_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=job_summary,
				rag_session_id=rag_session_id,
				rag_error_message=rag_error_message,
			)
		fallback_result = self.fallback_adapter.answer(
			message_text=message.message_text,
			intent=classification.intent,
			job_summary=job_summary,
			rag_error=rag_error_message,
		)
		if not fallback_result.ok:
			return self._build_agent_template_fallback_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=job_summary,
				rag_session_id=rag_session_id,
				rag_error_message=rag_error_message,
			)
		draft = DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=fallback_result.answer,
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={
				"source": "ai_fallback",
				"fallback_from": "enterprise_rag",
				"rag_error_message": rag_error_message,
				"reasoning_summary": fallback_result.reasoning_summary,
				"raw_response": fallback_result.raw_response,
			},
			approval_required=True,
			send_allowed=False,
			audit_status="draft_created",
			rag_session_id=rag_session_id,
		)
		return draft

	def _build_agent_template_fallback_draft(
		self,
		*,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
		job_summary: str | None,
		rag_session_id: str,
		rag_error_message: str | None,
	) -> DraftRecord | None:
		if self.agent_answer_adapter is None:
			return None
		agent_result = self.agent_answer_adapter.answer(
			message_text=message.message_text,
			intent=classification.intent,
			job_summary=job_summary,
			rag_answer="",
			citations=[],
		)
		if not agent_result.ok or not agent_result.answer.strip():
			return None
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=agent_result.answer,
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={
				"source": "boss_agent_ai_fallback",
				"fallback_from": "enterprise_rag",
				"rag_error_message": rag_error_message,
				"reasoning_summary": agent_result.reasoning_summary,
				"raw_response": agent_result.raw_response,
			},
			approval_required=decision.approval_required,
			send_allowed=False,
			audit_status="draft_created",
			rag_session_id=rag_session_id,
		)

	def _resolve_job_summary(self, message: MessageRecord) -> str | None:
		if not message.job_id:
			return None
		job = self.store.get_job(message.job_id)
		return None if job is None else job.summary

	@staticmethod
	def _merge_reasoning_summaries(
		*,
		rag_reasoning: dict[str, object] | None,
		agent_reasoning: dict[str, object] | None,
	) -> dict[str, object] | None:
		if rag_reasoning and agent_reasoning:
			return {
				"grounding": rag_reasoning,
				"agent_strategy": agent_reasoning,
			}
		return agent_reasoning or rag_reasoning

	@staticmethod
	def _build_rag_session_id(message: MessageRecord) -> str:
		"""Keep remote session ids compact to avoid upstream protocol issues."""
		conversation_key = hashlib.sha1(message.conversation_id.encode("utf-8")).hexdigest()[:12]
		return f"boss-rag-{conversation_key}"

	def _save_assistant_memory_message(self, draft: DraftRecord) -> None:
		if not draft.draft_text.strip():
			return
		source_message = self.store.get_message(draft.source_message_id)
		self.store.save_message(
			MessageRecord(
				message_id=f"draftmsg_{draft.source_message_id}",
				conversation_id=draft.conversation_id,
				message_text=draft.draft_text,
				direction="outbound",
				message_type="draft",
				job_id=source_message.job_id if source_message else None,
				recruiter_id=source_message.recruiter_id if source_message else None,
				source="rag_draft_memory",
				raw={
					"draft_id": draft.draft_id,
					"audit_status": draft.audit_status,
					"approval_required": draft.approval_required,
					"evidence_source": draft.evidence.get("source"),
				},
				created_at=draft.updated_at,
			)
		)

	@staticmethod
	def _local_draft_text(message: MessageRecord, intent: str) -> str:
		if intent == "job_detail_question":
			return "我想进一步了解这个岗位的核心职责、团队协作方式，以及前 3 个月的重点目标。"
		if intent == "smalltalk":
			return "您好，已收到您的消息，感谢联系。"
		if intent == "resume_share_request":
			return "可以的，我现在通过 BOSS 直聘官方页面发送在线简历；如果您希望我补充特定项目经历或作品，也欢迎告诉我。"
		if intent == "resignation_status":
			return "我目前主要是希望寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。当前项目让我积累了企业级 RAG 从架构到落地的完整经验，下一步希望进入更成熟的 AI 团队或更有 AI 产品化空间的环境，把这类系统继续做深。"
		if intent == "personal_status":
			return "我目前是在职看机会，简历里到岗时间是一个月内。如果双方匹配，我会按流程做好交接，保证入职安排稳定可控。"
		if intent == "availability_or_schedule":
			return "我可以配合安排沟通时间，工作日晚上或周末通常更方便；如果您这边有明确时间，我也可以尽量协调。"
		if intent == "interview_time":
			return "可以的，我这边可以配合面试安排。您方便给我几个可选时间吗？我确认后会尽快回复。"
		if intent in {"contact_exchange", "salary_or_offer", "unsafe_or_unclear"}:
			return ""
		return message.message_text
