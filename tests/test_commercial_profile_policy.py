from boss_agent_cli.rag_reply.profile_models import TenantRecord, UsageCounterRecord
from boss_agent_cli.rag_reply.profile_policy import (
	CommercialGateDecision,
	evaluate_commercial_gate,
)


def test_gate_allows_active_tenant_under_quota():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="active"),
		metric_name="rag_calls",
		usage=UsageCounterRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="profile_ai",
			metric_name="rag_calls",
			period_start="2026-06-01",
			period_end="2026-07-01",
			used_count=9,
			limit_count=10,
		),
	)

	assert decision == CommercialGateDecision(allowed=True, status="allowed", metric_name="rag_calls")


def test_gate_allows_normalized_active_status():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status=" ACTIVE "),
		metric_name="rag_calls",
		usage=None,
	)

	assert decision == CommercialGateDecision(allowed=True, status="allowed", metric_name="rag_calls")


def test_gate_blocks_missing_tenant():
	decision = evaluate_commercial_gate(
		tenant=None,
		metric_name="rag_calls",
		usage=None,
	)

	assert decision.allowed is False
	assert decision.status == "tenant_missing"
	assert "tenant" in decision.error_message


def test_gate_blocks_suspended_tenant():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status=" Suspended "),
		metric_name="outreach_auto_greet",
		usage=None,
	)

	assert decision.allowed is False
	assert decision.status == "tenant_suspended"
	assert "Reactivate" in decision.recovery_action


def test_gate_blocks_empty_tenant_status():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status=" "),
		metric_name="rag_calls",
		usage=None,
	)

	assert decision.allowed is False
	assert decision.status == "tenant_status_unknown"


def test_gate_blocks_unknown_tenant_status():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="paused"),
		metric_name="rag_calls",
		usage=None,
	)

	assert decision.allowed is False
	assert decision.status == "tenant_status_unknown"
	assert "paused" in decision.error_message


def test_gate_blocks_quota_exhaustion():
	decision = evaluate_commercial_gate(
		tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="active"),
		metric_name="profile_count",
		usage=UsageCounterRecord(
			tenant_id="tenant_001",
			user_id="user_001",
			profile_id="",
			metric_name="profile_count",
			period_start="2026-06-01",
			period_end="2026-07-01",
			used_count=1,
			limit_count=1,
		),
	)

	assert decision.allowed is False
	assert decision.status == "quota_exhausted"
