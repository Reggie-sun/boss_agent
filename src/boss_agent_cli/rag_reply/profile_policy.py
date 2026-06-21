"""Commercial profile access gates."""

from __future__ import annotations

from dataclasses import dataclass

from boss_agent_cli.rag_reply.profile_models import TenantRecord, UsageCounterRecord


_ALLOWED_SUBSCRIPTION_STATUSES = {"trial", "active"}
_BLOCKED_SUBSCRIPTION_STATUSES = {"past_due", "suspended", "canceled"}


@dataclass(frozen=True, slots=True)
class CommercialGateDecision:
	allowed: bool
	status: str
	metric_name: str = ""
	error_message: str = ""
	recovery_action: str = ""


def evaluate_commercial_gate(
	*,
	tenant: TenantRecord | None,
	metric_name: str,
	usage: UsageCounterRecord | None,
) -> CommercialGateDecision:
	if tenant is None:
		return CommercialGateDecision(
			False,
			"tenant_missing",
			metric_name,
			"No tenant is configured.",
			"Create or select a tenant before retrying.",
		)
	subscription_status = tenant.subscription_status.strip().lower()
	if subscription_status in _BLOCKED_SUBSCRIPTION_STATUSES:
		return CommercialGateDecision(
			False,
			f"tenant_{subscription_status}",
			metric_name,
			f"Tenant subscription_status={subscription_status} blocks new actions.",
			"Reactivate the tenant before starting new automated actions.",
		)
	if subscription_status not in _ALLOWED_SUBSCRIPTION_STATUSES:
		return CommercialGateDecision(
			False,
			"tenant_status_unknown",
			metric_name,
			f"Unknown tenant subscription_status={tenant.subscription_status!r} blocks new actions.",
			"Fix the tenant subscription status before retrying.",
		)
	if usage is not None and usage.limit_count >= 0 and usage.used_count >= usage.limit_count:
		return CommercialGateDecision(
			False,
			"quota_exhausted",
			usage.metric_name,
			f"Quota exhausted for {usage.metric_name}: {usage.used_count}/{usage.limit_count}.",
			"Raise the plan limit or wait for the next quota period.",
		)
	return CommercialGateDecision(True, "allowed", metric_name)
