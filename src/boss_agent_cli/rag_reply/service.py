"""Orchestration service for the Boss RAG draft workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from boss_agent_cli.rag_reply.classifier import ClassificationResult, classify_message_with_context
from boss_agent_cli.rag_reply.clipboard import copy_text
from boss_agent_cli.rag_reply.models import (
	ApprovalEventRecord,
	AuditLogRecord,
	DraftRecord,
	MessageRecord,
	RagCallRecord,
)
from boss_agent_cli.rag_reply.policy import ApprovalDecision, build_approval_decision
from boss_agent_cli.rag_reply.question_builder import build_answer_objective, build_rag_question
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import (
	interview_window_reply,
	salary_preset_reply,
)


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
		profile_service: object | None = None,
		profile_rag_connector: object | None = None,
		profile_binding_required: bool = True,
		salary_reply: str = "",
		interview_windows: str = "",
	) -> None:
		self.store = store
		self.rag_adapter = rag_adapter
		self.fallback_adapter = fallback_adapter
		self.agent_answer_adapter = agent_answer_adapter
		self.profile_service: Any = profile_service
		self.profile_rag_connector: Any = profile_rag_connector
		self.profile_binding_required = profile_binding_required
		self.salary_reply = salary_reply.strip()
		self.interview_windows = interview_windows.strip()

	def create_draft_for_message(self, message_id: str) -> DraftRecord:
		message = self.store.get_message(message_id)
		if message is None:
			raise LookupError(f"Unknown message_id={message_id}")
		classification = classify_message_with_context(
			message.message_text,
			self._conversation_memory_messages(message),
		)
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
		if classification.requires_direct_agent_answer:
			return self._build_direct_agent_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=self._resolve_job_summary(message),
			)
		if classification.requires_rag:
			return self._build_rag_backed_draft(message, classification, decision)
		if classification.intent == "salary_or_offer":
			return self._build_salary_preset_draft(
				message=message,
				classification=classification,
				decision=decision,
			)
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=self._local_draft_text(message, classification.intent),
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={
				"source": "local_policy",
				"reason": self._local_policy_reason(classification.intent, classification.classifier_source),
			},
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
		profile_context = None
		if self.profile_service is not None:
			profile_context = self._resolve_profile_context(message)
			if profile_context is None and self.profile_binding_required:
				return DraftRecord.new(
					conversation_id=message.conversation_id,
					source_message_id=message.message_id,
					draft_text="",
					intent=classification.intent,
					risk_labels=[*decision.risk_labels, "profile_binding_required"],
					evidence={"source": "profile_policy", "reason": "profile_binding_required"},
					approval_required=True,
					send_allowed=False,
					audit_status="profile_binding_required",
					rag_session_id=rag_session_id,
				)
			if profile_context is not None and self.profile_rag_connector is None:
				return DraftRecord.new(
					conversation_id=message.conversation_id,
					source_message_id=message.message_id,
					draft_text="",
					intent=classification.intent,
					risk_labels=[*decision.risk_labels, "profile_rag_connector_required"],
					evidence={"source": "profile_policy", "reason": "profile_rag_connector_required"},
					approval_required=True,
					send_allowed=False,
					audit_status="profile_rag_connector_required",
					rag_session_id=rag_session_id,
				)
		rag_question = build_rag_question(
			message.message_text,
			job_summary,
			build_answer_objective(classification.intent, message.message_text),
		)
		if profile_context is None:
			rag_result = self.rag_adapter.answer(
				rag_question=rag_question,
				session_id=rag_session_id,
			)
			rag_request = {"question": rag_question, "session_id": rag_session_id, "message_id": message.message_id}
			profile_evidence_context = None
		else:
			rag_auth_binding = self.profile_service.get_profile_rag_auth_binding(profile_context["profile_id"])
			rag_result = self.profile_rag_connector.ask_profile(
				tenant_id=profile_context["tenant_id"],
				user_id=profile_context["user_id"],
				profile_id=profile_context["profile_id"],
				knowledge_base_id=profile_context["knowledge_base_id"],
				question=rag_question,
				conversation_id=message.conversation_id,
				rag_auth_binding=rag_auth_binding,
			)
			profile_evidence_context = getattr(rag_result, "profile_context", None) or profile_context
			rag_request = {
				"question": rag_question,
				"message_id": message.message_id,
				"profile_context": profile_context,
				"rag_auth": self._rag_auth_request_context(rag_auth_binding),
			}
		self.store.save_rag_call(
			RagCallRecord.new(
				conversation_id=message.conversation_id,
				draft_id=None,
				request=rag_request,
				status=rag_result.audit_status,
				response=rag_result.raw_response or {"error_message": rag_result.error_message},
			)
		)
		if not rag_result.ok:
			if profile_context is not None:
				audit_status = str(rag_result.audit_status or "profile_rag_failed")
				return DraftRecord.new(
					conversation_id=message.conversation_id,
					source_message_id=message.message_id,
					draft_text="",
					intent=classification.intent,
					risk_labels=[*decision.risk_labels, audit_status],
					evidence={
						"source": "profile_rag",
						"profile_context": profile_evidence_context,
						"rag_auth": rag_request["rag_auth"],
						"error_message": rag_result.error_message,
					},
					approval_required=True,
					send_allowed=False,
					audit_status=audit_status,
					rag_session_id=rag_session_id,
				)
			fallback_draft = self._build_fallback_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=job_summary,
				rag_session_id=rag_session_id,
				rag_error_message=rag_result.error_message,
			)
			if fallback_draft is not None:
				if profile_evidence_context is not None:
					fallback_draft.evidence["profile_context"] = profile_evidence_context
				return fallback_draft
			evidence = {
				"source": "enterprise_rag",
				"error_message": rag_result.error_message,
			}
			if profile_evidence_context is not None:
				evidence["profile_context"] = profile_evidence_context
			return DraftRecord.new(
				conversation_id=message.conversation_id,
				source_message_id=message.message_id,
				draft_text="",
				intent=classification.intent,
				risk_labels=decision.risk_labels,
				evidence=evidence,
				approval_required=True,
				send_allowed=False,
				audit_status="rag_failed",
				rag_session_id=rag_session_id,
			)
		if not self._rag_result_has_high_confidence(rag_result):
			if profile_context is not None:
				audit_status = "profile_rag_low_confidence"
				return DraftRecord.new(
					conversation_id=message.conversation_id,
					source_message_id=message.message_id,
					draft_text="",
					intent=classification.intent,
					risk_labels=[*decision.risk_labels, audit_status],
					evidence={
						"source": "profile_rag",
						"reason": audit_status,
						"profile_context": profile_evidence_context,
						"rag_auth": rag_request["rag_auth"],
						"citations": rag_result.citations,
						"reasoning_summary": rag_result.reasoning_summary,
					},
					approval_required=True,
					send_allowed=False,
					audit_status=audit_status,
					rag_session_id=rag_session_id,
				)
			direct_draft = self._build_direct_agent_draft(
				message=message,
				classification=classification,
				decision=decision,
				job_summary=job_summary,
				rag_session_id=rag_session_id,
				fallback_from="enterprise_rag_low_confidence",
				rag_result=rag_result,
			)
			if direct_draft.draft_text.strip():
				if profile_evidence_context is not None:
					direct_draft.evidence["profile_context"] = profile_evidence_context
				return direct_draft
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
		if profile_evidence_context is not None:
			evidence["profile_context"] = profile_evidence_context
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
			if profile_evidence_context is not None:
				evidence["profile_context"] = profile_evidence_context
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

	def _resolve_profile_context(self, message: MessageRecord) -> dict[str, str] | None:
		binding = self.profile_service.get_conversation_binding(message.conversation_id)
		if binding is None:
			return None
		return {
			"tenant_id": binding.tenant_id,
			"user_id": binding.user_id,
			"profile_id": binding.profile_id,
			"knowledge_base_id": binding.knowledge_base_id,
		}

	@staticmethod
	def _rag_auth_request_context(rag_auth_binding: object | None) -> dict[str, str]:
		if rag_auth_binding is None:
			return {
				"auth_mode": "inherit",
				"credential_ref": "",
				"scope_type": "none",
				"scope_id": "",
			}
		return {
			"auth_mode": rag_auth_binding.auth_mode,
			"credential_ref": rag_auth_binding.credential_ref,
			"scope_type": rag_auth_binding.scope_type,
			"scope_id": rag_auth_binding.scope_id,
		}

	def _build_direct_agent_draft(
		self,
		*,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
		job_summary: str | None,
		rag_session_id: str | None = None,
		fallback_from: str | None = None,
		rag_result: RagAnswerProtocol | None = None,
	) -> DraftRecord:
		agent_result = self._build_agent_answer(
			message=message,
			classification=classification,
			job_summary=job_summary,
			rag_answer="",
			citations=[],
		)
		evidence: dict[str, object] = {
			"source": "boss_agent_ai",
			"route": "direct_agent",
		}
		if fallback_from:
			evidence.update(
				{
					"fallback_from": fallback_from,
					"grounded_answer": "" if rag_result is None else rag_result.answer,
					"citations": [] if rag_result is None else rag_result.citations,
					"rag_reasoning_summary": None if rag_result is None else rag_result.reasoning_summary,
					"rag_raw_response": None if rag_result is None else rag_result.raw_response,
					"rag_error_message": None if rag_result is None else rag_result.error_message,
				}
			)
		if agent_result is not None and agent_result.ok and agent_result.answer.strip():
			evidence["reasoning_summary"] = agent_result.reasoning_summary
			evidence["agent_raw_response"] = agent_result.raw_response
			return DraftRecord.new(
				conversation_id=message.conversation_id,
				source_message_id=message.message_id,
				draft_text=agent_result.answer,
				intent=classification.intent,
				risk_labels=decision.risk_labels,
				evidence=evidence,
				approval_required=decision.approval_required,
				send_allowed=False,
				audit_status="draft_created",
				rag_session_id=rag_session_id,
			)
		if agent_result is not None and agent_result.error_message:
			evidence["agent_error_message"] = agent_result.error_message
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text="",
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence=evidence,
			approval_required=decision.approval_required,
			send_allowed=False,
			audit_status="agent_answer_failed",
			rag_session_id=rag_session_id,
		)

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

	@staticmethod
	def _rag_result_has_high_confidence(rag_result: RagAnswerProtocol) -> bool:
		if not rag_result.ok or not rag_result.answer.strip():
			return False
		if BossRagReplyService._reasoning_summary_is_low_confidence(rag_result.reasoning_summary):
			return False
		citations = rag_result.citations or []
		if not citations:
			return False
		return True

	@staticmethod
	def _reasoning_summary_is_low_confidence(reasoning_summary: dict[str, object] | None) -> bool:
		if not isinstance(reasoning_summary, dict):
			return False
		low_confidence_values = {"low", "insufficient", "weak"}
		for key in ("confidence", "confidence_level"):
			value = reasoning_summary.get(key)
			if isinstance(value, str) and value.strip().lower() in low_confidence_values:
				return True
		return False

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

	def _build_salary_preset_draft(
		self,
		*,
		message: MessageRecord,
		classification: ClassificationResult,
		decision: ApprovalDecision,
	) -> DraftRecord:
		draft_text = salary_preset_reply(self.salary_reply)
		return DraftRecord.new(
			conversation_id=message.conversation_id,
			source_message_id=message.message_id,
			draft_text=draft_text,
			intent=classification.intent,
			risk_labels=decision.risk_labels,
			evidence={
				"source": "local_policy",
				"reason": "salary_preset" if self.salary_reply else "salary_handoff",
			},
			approval_required=decision.approval_required,
			send_allowed=False,
			audit_status="draft_created",
		)

	def _resolve_job_summary(self, message: MessageRecord) -> str | None:
		if not message.job_id:
			return None
		job = self.store.get_job(message.job_id)
		return None if job is None else job.summary

	def _conversation_memory_messages(self, message: MessageRecord) -> list[str]:
		return [
			record.message_text
			for record in self.store.list_messages(message.conversation_id)
			if record.message_id != message.message_id and record.message_text.strip()
		][-8:]

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

	def _local_draft_text(self, message: MessageRecord, intent: str) -> str:
		if intent == "job_detail_question":
			return "我想进一步了解这个岗位的核心职责、团队协作方式，以及前 3 个月的重点目标。"
		if intent == "smalltalk":
			return "您好，已收到您的消息，感谢联系。"
		if intent == "resume_share_request":
			return "可以的，我这边通过 BOSS 直聘发送附件简历给您。"
		if intent == "resignation_status":
			return "我目前主要是希望寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。当前项目让我积累了企业级 RAG 从架构到落地的完整经验，下一步希望进入更成熟的 AI 团队或更有 AI 产品化空间的环境，把这类系统继续做深。"
		if intent == "personal_status":
			return "我目前是在职看机会，简历里到岗时间是一个月内。如果双方匹配，我会按流程做好交接，保证入职安排稳定可控。"
		if intent == "job_location_acceptance":
			return "这个工作地点可以接受，具体办公地点、到岗安排和通勤细节可以继续沟通确认。"
		if intent == "availability_or_schedule":
			return self._interview_window_text()
		if intent == "interview_time":
			return self._interview_window_text()
		if intent == "salary_or_offer":
			return salary_preset_reply("")
		if intent == "contact_exchange":
			return "可以先在 BOSS 直聘上沟通，后续如果流程需要，我再配合补充联系方式。"
		if intent == "unsafe_or_unclear":
			return "这条信息我需要先确认一下，稍后再回复您。"
		return message.message_text

	def _interview_window_text(self) -> str:
		if self.interview_windows:
			return interview_window_reply(self.interview_windows)
		return "我可以配合安排沟通时间，工作日晚上或周末通常更方便；如果您这边有明确时间，我也可以尽量协调。"

	def _local_policy_reason(self, intent: str, classifier_source: str) -> str:
		if intent in {"availability_or_schedule", "interview_time"} and self.interview_windows:
			return "interview_windows_preset"
		return classifier_source
