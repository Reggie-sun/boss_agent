"""Approval policy for Boss RAG draft replies."""

from __future__ import annotations

from dataclasses import dataclass

from boss_agent_cli.rag_reply.classifier import SENSITIVE_INTENTS


@dataclass(slots=True)
class ApprovalDecision:
	approval_required: bool
	send_allowed: bool
	audit_status: str
	risk_labels: list[str]


def build_approval_decision(intent: str, risk_labels: list[str] | None = None) -> ApprovalDecision:
	"""Build a fail-safe approval decision for a draft."""
	labels = list(risk_labels or [])
	if intent in SENSITIVE_INTENTS and "human_approval_required" not in labels:
		labels.insert(0, "human_approval_required")
	if intent in SENSITIVE_INTENTS and "sensitive_intent" not in labels:
		labels.append("sensitive_intent")
	return ApprovalDecision(
		approval_required=True,
		send_allowed=False,
		audit_status="draft_created",
		risk_labels=labels,
	)

