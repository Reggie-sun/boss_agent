# Boss Commercial Profile RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留当前 `BOSS_AGENT` reply、watcher、Boss 自动开聊、自动投简历、CLI、MCP、Docker 和 demo conversation 的前提下，新增 commercial-ready 的 tenant/user/profile/RAG 资料层、会话 profile binding、真实 usage/quota gate，以及可被 Product Design 插件重构的前端数据面。

**Architecture:** `BOSS_AGENT` 继续拥有业务状态和安全 gate：tenant、user、profile、upload、binding、usage、audit、reply/outreach policy 都落在本地 SQLite。外部 Enterprise RAG 继续负责检索和回答；新增 `RagProfileConnector` 作为薄适配层，暴露 profile-aware contract，但当前 `/api/v1/chat/ask` fallback 不发送上游 schema 不支持的 `metadata` 字段。前端先稳定 bridge/API contract，再通过 Product Design workflow 做视觉和交互重构。

**Tech Stack:** Python 3.10+, Click, sqlite3, dataclasses, httpx, pytest, React 19, Vite 6, existing Boss bridge/CDP delivery helpers, Product Design plugin.

---

## Scope Check

这份 spec 横跨 persistence、RAG contract、reply path、outreach path、frontend 和 commercial gates。实现时仍保持一个 MVP，因为每个 task 都能产生可测试的工作切片，且旧能力不被删除。

必须保留的现有能力：

- `demo/interview-simulator` 的前端测试对话和 demo conversation。
- `/api/agent/ask`、`/api/agent/send`、watcher status/run/control。
- `Boss 自动开聊`、搜索预览、目标选择、`Agent 全自动`。
- 自动投简历、附件 PDF 简历发送，以及官方 Boss UI/CDP fail-closed 约束。
- `boss agent` / `boss rag` alias、MCP server、Docker 启动方式。

第一版明确不做：

- Stripe、微信、支付宝等真实支付回调。
- 在 `BOSS_AGENT` 内实现向量检索。
- 绕过 Boss 登录、风控、官方 UI 或附件上传路径。
- 把 Boss 原始对话、招聘者完整信息或职位完整详情批量上传到 RAG。

## Current Code Map

当前代码现状决定了实现边界：

- `src/boss_agent_cli/rag_reply/schema.py` 只有 `jobs/recruiters/conversations/messages/drafts/approval_events/audit_logs/rag_calls`。
- `src/boss_agent_cli/rag_reply/store.py` 已提供 `RagReplyStore.connect()`、JSON encode/decode 和现有 record CRUD，适合复用同一个 SQLite 文件。
- `src/boss_agent_cli/rag_reply/service.py` 负责 message -> classify -> RAG/direct -> draft -> audit，目前用 per-conversation `rag_session_id`。
- `src/boss_agent_cli/rag_reply/adapters/rag_http.py` 只调用 `POST /api/v1/chat/ask`，现有测试断言 payload 没有 `metadata`。
- `src/boss_agent_cli/rag_reply/adapters/agent_answer.py` 仍有本地候选人事实模板，后期必须收缩成通用 answer shaping。
- `src/boss_agent_cli/rag_reply/watcher_config.py`、`auto_actions.py`、`agent_tools.py` 承担 watcher 自动回复、联系方式、面试时间、附件简历 gate。
- `src/boss_agent_cli/commands/rag.py` 是 `agent`/`rag` CLI 中心，也负责构造 service、watcher 和真实发送。
- `demo/interview-simulator/vite.config.mjs` 已经很大，内含本地 bridge endpoints；新增 profile API 时要优先抽小模块，避免继续膨胀。
- `demo/interview-simulator/src/App.jsx` 已经接近 2000 行；Product Design 前端重构应拆 view/component/api，而不是继续堆在单文件。

## Product Design Handoff

已按 `product-design:index` 和 `product-design:get-context` 处理本次插件调用。当前不是 UI build 阶段，所以不运行 ideation/prototype/image-to-code；计划中只锁定后续前端重构的 Product Design gate。

前端重构 brief playback：

- Product: `BOSS_AGENT` commercial console。
- Workflows: `/agent/reply` 管会话回复、draft、evidence、watcher、profile binding；`/agent/outreach` 管搜索、预览、自动开聊、自动投简历。
- Visual source: 现有 `demo/interview-simulator`、当前 design tokens/styles，以及后续 Product Design 生成或选定的 visual target。
- Interactivity: full interactivity，本地 bridge controls 必须可用，profile/create/upload/bind/usage/watcher/outreach 状态都要真实接 API。

后续开始视觉重构前，必须重新运行 `product-design:get-context` playback。如果没有现成截图、Figma、URL 或选定 mock，先走 `product-design:ideate` 产出 3 个 visual options，等用户选定后再进入 `prototype` 或 `image-to-code`。

## File Structure

- Create `src/boss_agent_cli/rag_reply/profile_models.py`  
  commercial/profile dataclasses、status constants、metric names。

- Create `src/boss_agent_cli/rag_reply/profile_service.py`  
  使用现有 `RagReplyStore` SQLite connection 管 tenant、user、profile、config、upload、binding、usage。

- Create `src/boss_agent_cli/rag_reply/profile_policy.py`  
  license/subscription/quota/profile config gate 决策，不做外部支付。

- Create `src/boss_agent_cli/rag_reply/adapters/rag_profile.py`  
  profile-aware RAG connector。当前 chat/ask fallback 不发送 unsupported `metadata`；profile identity 写入本地 `rag_calls` 和 connector result。

- Modify `src/boss_agent_cli/rag_reply/schema.py`  
  追加 profile/commercial tables，不改旧表名，不迁移删除旧数据。

- Modify `src/boss_agent_cli/rag_reply/service.py`  
  支持可选 `ProfileService` 和 `RagProfileConnector`，事实类问题要求 conversation binding，draft evidence 写入 `profile_context`。

- Modify `src/boss_agent_cli/rag_reply/question_builder.py`  
  保持 prompt 最小化，只接受 HR 问题、岗位摘要、objective；不把 tenant/user/profile 当自然语言 stuffing。

- Modify `src/boss_agent_cli/rag_reply/adapters/rag_http.py`
  保持 `/api/v1/chat/ask` contract 稳定；不能为了 profile context 添加 `metadata` payload。

- Modify `src/boss_agent_cli/rag_reply/watcher_config.py`, `auto_actions.py`, `agent_tools.py`
  从 `ProfileConfig` 生成 effective watcher config，并将 reply/outreach/proactive resume gates 分开。

- Modify `src/boss_agent_cli/commands/rag.py`  
  增加 profile/upload/binding/usage commands，并在 `_build_service()` 注入 profile 层。

- Create `demo/interview-simulator/server/profileBridge.mjs`
  从巨大的 `vite.config.mjs` 抽出 profile/usage/binding bridge handlers。

- Modify `demo/interview-simulator/vite.config.mjs`
  注册 profile bridge handlers，保留现有 ask/send/watcher/auto-greet endpoints。

- Product Design frontend refactor files:
  - Create `demo/interview-simulator/src/api/agentClient.js`
  - Create `demo/interview-simulator/src/views/ReplyWorkspace.jsx`
  - Create `demo/interview-simulator/src/views/OutreachWorkspace.jsx`
  - Create `demo/interview-simulator/src/views/ProfileHub.jsx`
  - Create `demo/interview-simulator/src/components/profile/ProfileSelector.jsx`
  - Create `demo/interview-simulator/src/components/profile/ProfileConfigPanel.jsx`
  - Modify `demo/interview-simulator/src/App.jsx`
  - Modify `demo/interview-simulator/src/styles.css`

## Task 1: Commercial Schema And Models

**Files:**
- Create: `src/boss_agent_cli/rag_reply/profile_models.py`
- Modify: `src/boss_agent_cli/rag_reply/schema.py`
- Test: `tests/test_commercial_profile_schema.py`

- [ ] **Step 1: Write failing schema/model tests**

Create `tests/test_commercial_profile_schema.py`:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.profile_models import (
    ConversationProfileBindingRecord,
    ProfileConfigRecord,
    ProfileUploadRecord,
    TenantRecord,
    UsageCounterRecord,
    UserProfileRecord,
    UserRecord,
)
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_commercial_profile_tables_are_created(tmp_path: Path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()

    assert {
        "tenants",
        "users",
        "user_profiles",
        "profile_configs",
        "profile_uploads",
        "conversation_profile_bindings",
        "usage_counters",
    }.issubset(set(store.list_tables()))


def test_profile_model_defaults_are_safe():
    tenant = TenantRecord(tenant_id="tenant_001", display_name="Demo Tenant")
    user = UserRecord(tenant_id="tenant_001", user_id="user_001", display_name="Reggie", email="r@example.com")
    profile = UserProfileRecord(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        display_name="AI 应用工程师",
        target_title="AI Application Engineer",
    )
    config = ProfileConfigRecord(tenant_id="tenant_001", profile_id="profile_ai")
    upload = ProfileUploadRecord(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        upload_id="upload_001",
        source_filename="resume.pdf",
        source_type="resume",
    )
    binding = ConversationProfileBindingRecord(
        tenant_id="tenant_001",
        conversation_id="conv_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
    )
    usage = UsageCounterRecord(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        metric_name="rag_calls",
        period_start="2026-06-01",
        period_end="2026-07-01",
    )

    assert tenant.plan_code == "free"
    assert tenant.subscription_status == "trial"
    assert user.role == "owner"
    assert profile.status == "active"
    assert config.reply_auto_send_enabled is False
    assert config.outreach_auto_send_enabled is False
    assert config.proactive_resume_enabled is False
    assert upload.status == "queued"
    assert binding.binding_source == "manual"
    assert usage.used_count == 0
    assert usage.limit_count == -1
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/test_commercial_profile_schema.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `boss_agent_cli.rag_reply.profile_models`.

- [ ] **Step 3: Add dataclasses**

Create `src/boss_agent_cli/rag_reply/profile_models.py` with these records:

```python
"""Commercial profile domain models for Boss Agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from boss_agent_cli.rag_reply.models import new_id, utc_now_iso


PLAN_CODES = {"free", "pro", "team", "enterprise"}
SUBSCRIPTION_STATUSES = {"trial", "active", "past_due", "suspended", "canceled"}
PROFILE_STATUSES = {"active", "archived"}
UPLOAD_STATUSES = {"queued", "uploaded", "indexed", "failed"}
BINDING_SOURCES = {"manual", "default", "imported"}

METRIC_PROFILE_COUNT = "profile_count"
METRIC_UPLOAD_COUNT = "profile_upload_count"
METRIC_UPLOAD_BYTES = "profile_upload_bytes"
METRIC_RAG_CALLS = "rag_calls"
METRIC_REPLY_AUTO_SEND = "reply_auto_send"
METRIC_OUTREACH_AUTO_GREET = "outreach_auto_greet"
METRIC_ATTACHMENT_RESUME_SEND = "attachment_resume_send"


@dataclass(slots=True)
class TenantRecord:
    tenant_id: str
    display_name: str
    plan_code: str = "free"
    subscription_status: str = "trial"
    license_key_hash: str = ""
    payment_provider: str = ""
    provider_customer_id: str = ""
    provider_subscription_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UserRecord:
    tenant_id: str
    user_id: str
    display_name: str
    email: str
    role: str = "owner"
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UserProfileRecord:
    tenant_id: str
    user_id: str
    profile_id: str
    display_name: str
    target_title: str
    knowledge_base_id: str = ""
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def new(cls, *, tenant_id: str, user_id: str, display_name: str, target_title: str, knowledge_base_id: str = ""):
        return cls(
            tenant_id=tenant_id,
            user_id=user_id,
            profile_id=new_id("profile"),
            display_name=display_name,
            target_title=target_title,
            knowledge_base_id=knowledge_base_id,
        )


@dataclass(slots=True)
class ProfileConfigRecord:
    tenant_id: str
    profile_id: str
    contact_phone: str = ""
    contact_wechat: str = ""
    interview_windows: str = ""
    salary_reply_policy: str = ""
    resume_attachment_path: str = ""
    reply_auto_send_enabled: bool = False
    outreach_auto_send_enabled: bool = False
    proactive_resume_enabled: bool = False
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ProfileUploadRecord:
    tenant_id: str
    user_id: str
    profile_id: str
    upload_id: str
    source_filename: str
    source_type: str
    source_size_bytes: int = 0
    rag_document_id: str = ""
    status: str = "queued"
    error_message: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ConversationProfileBindingRecord:
    tenant_id: str
    conversation_id: str
    user_id: str
    profile_id: str
    knowledge_base_id: str
    binding_source: str = "manual"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class UsageCounterRecord:
    tenant_id: str
    user_id: str
    profile_id: str
    metric_name: str
    period_start: str
    period_end: str
    used_count: int = 0
    limit_count: int = -1
    updated_at: str = field(default_factory=utc_now_iso)
```

- [ ] **Step 4: Add schema tables**

Append `CREATE TABLE IF NOT EXISTS` statements to `CREATE_TABLE_STATEMENTS` in `src/boss_agent_cli/rag_reply/schema.py` for:

```sql
tenants(tenant_id PRIMARY KEY, display_name, plan_code, subscription_status, license_key_hash, payment_provider, provider_customer_id, provider_subscription_id, created_at, updated_at)
users(user_id PRIMARY KEY, tenant_id, display_name, email, role, status, created_at, updated_at)
user_profiles(profile_id PRIMARY KEY, tenant_id, user_id, display_name, target_title, knowledge_base_id, status, created_at, updated_at)
profile_configs(profile_id PRIMARY KEY, tenant_id, contact_phone, contact_wechat, interview_windows, salary_reply_policy, resume_attachment_path, reply_auto_send_enabled, outreach_auto_send_enabled, proactive_resume_enabled, updated_at)
profile_uploads(upload_id PRIMARY KEY, tenant_id, user_id, profile_id, source_filename, source_type, source_size_bytes, rag_document_id, status, error_message, created_at, updated_at)
conversation_profile_bindings(conversation_id PRIMARY KEY, tenant_id, user_id, profile_id, knowledge_base_id, binding_source, created_at, updated_at)
usage_counters(tenant_id, user_id, profile_id, metric_name, period_start, period_end, used_count, limit_count, updated_at, PRIMARY KEY(tenant_id, user_id, profile_id, metric_name, period_start, period_end))
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest tests/test_commercial_profile_schema.py tests/test_rag_reply_store.py -v
git add src/boss_agent_cli/rag_reply/profile_models.py src/boss_agent_cli/rag_reply/schema.py tests/test_commercial_profile_schema.py
git commit -m "feat: add commercial profile schema"
```

Expected: pytest PASS, then one focused commit.

## Task 2: Profile Service Persistence

**Files:**
- Create: `src/boss_agent_cli/rag_reply/profile_service.py`
- Test: `tests/test_commercial_profile_service.py`

- [ ] **Step 1: Write service round-trip tests**

Create `tests/test_commercial_profile_service.py`:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.profile_models import (
    ConversationProfileBindingRecord,
    ProfileConfigRecord,
    ProfileUploadRecord,
    TenantRecord,
    UsageCounterRecord,
    UserProfileRecord,
    UserRecord,
)
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _service(tmp_path: Path) -> ProfileService:
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return ProfileService(store)


def test_profile_service_round_trips_core_records(tmp_path: Path):
    service = _service(tmp_path)
    service.save_tenant(TenantRecord(tenant_id="tenant_001", display_name="Demo"))
    service.save_user(UserRecord(tenant_id="tenant_001", user_id="user_001", display_name="Reggie", email="r@example.com"))
    service.save_profile(
        UserProfileRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="profile_ai",
            display_name="AI 应用工程师",
            target_title="AI Application Engineer",
            knowledge_base_id="kb_ai",
        )
    )
    service.save_profile_config(
        ProfileConfigRecord(
            tenant_id="tenant_001",
            profile_id="profile_ai",
            contact_phone="13800138000",
            contact_wechat="reggie-ai",
            interview_windows="工作日 20:00 后",
            salary_reply_policy="薪资本人确认",
            resume_attachment_path="/tmp/resume.pdf",
            reply_auto_send_enabled=True,
        )
    )
    service.bind_conversation(
        ConversationProfileBindingRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            conversation_id="conv_001",
            profile_id="profile_ai",
            knowledge_base_id="kb_ai",
        )
    )

    assert service.get_tenant("tenant_001").display_name == "Demo"
    assert service.list_profiles("tenant_001", "user_001")[0].profile_id == "profile_ai"
    assert service.get_profile_config("profile_ai").contact_wechat == "reggie-ai"
    assert service.get_conversation_binding("conv_001").knowledge_base_id == "kb_ai"


def test_profile_service_tracks_uploads_and_usage(tmp_path: Path):
    service = _service(tmp_path)
    service.save_upload(
        ProfileUploadRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="profile_ai",
            upload_id="upload_001",
            source_filename="resume.pdf",
            source_type="resume",
            source_size_bytes=1200,
            rag_document_id="doc_001",
            status="indexed",
        )
    )
    service.save_usage_counter(
        UsageCounterRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="profile_ai",
            metric_name="rag_calls",
            period_start="2026-06-01",
            period_end="2026-07-01",
            used_count=3,
            limit_count=50,
        )
    )

    usage = service.increment_usage(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        metric_name="rag_calls",
        period_start="2026-06-01",
        period_end="2026-07-01",
    )

    assert service.list_uploads("profile_ai")[0].status == "indexed"
    assert usage.used_count == 4
    assert usage.limit_count == 50
```

- [ ] **Step 2: Implement `ProfileService`**

Create `src/boss_agent_cli/rag_reply/profile_service.py` using `RagReplyStore.connect()` and the same JSON-free row mapping style as `store.py`. Required methods:

- `__init__(self, store: RagReplyStore) -> None`
- `save_tenant(self, record: TenantRecord) -> None`
- `get_tenant(self, tenant_id: str) -> TenantRecord | None`
- `save_user(self, record: UserRecord) -> None`
- `save_profile(self, record: UserProfileRecord) -> None`
- `get_profile(self, profile_id: str) -> UserProfileRecord | None`
- `list_profiles(self, tenant_id: str, user_id: str) -> list[UserProfileRecord]`
- `save_profile_config(self, record: ProfileConfigRecord) -> None`
- `get_profile_config(self, profile_id: str) -> ProfileConfigRecord | None`
- `save_upload(self, record: ProfileUploadRecord) -> None`
- `list_uploads(self, profile_id: str) -> list[ProfileUploadRecord]`
- `bind_conversation(self, record: ConversationProfileBindingRecord) -> None`
- `get_conversation_binding(self, conversation_id: str) -> ConversationProfileBindingRecord | None`
- `save_usage_counter(self, record: UsageCounterRecord) -> None`
- `get_usage_counter(self, tenant_id: str, user_id: str, profile_id: str, metric_name: str, period_start: str, period_end: str) -> UsageCounterRecord | None`
- `increment_usage(self, *, tenant_id: str, user_id: str, profile_id: str, metric_name: str, period_start: str, period_end: str, amount: int = 1) -> UsageCounterRecord`

All writes use `INSERT OR REPLACE`. `increment_usage()` must preserve an existing `limit_count`; if no record exists, create one with `limit_count=-1`.

- [ ] **Step 3: Verify and commit**

Run:

```bash
pytest tests/test_commercial_profile_service.py tests/test_commercial_profile_schema.py -v
git add src/boss_agent_cli/rag_reply/profile_service.py tests/test_commercial_profile_service.py
git commit -m "feat: add commercial profile service"
```

Expected: pytest PASS.

## Task 3: Commercial Gate Policy

**Files:**
- Create: `src/boss_agent_cli/rag_reply/profile_policy.py`
- Test: `tests/test_commercial_profile_policy.py`

- [ ] **Step 1: Write gate tests**

Create `tests/test_commercial_profile_policy.py`:

```python
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


def test_gate_blocks_suspended_tenant():
    decision = evaluate_commercial_gate(
        tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="suspended"),
        metric_name="outreach_auto_greet",
        usage=None,
    )

    assert decision.allowed is False
    assert decision.status == "tenant_suspended"
    assert "Reactivate" in decision.recovery_action


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
```

- [ ] **Step 2: Implement policy**

Create `profile_policy.py` with:

```python
@dataclass(frozen=True, slots=True)
class CommercialGateDecision:
    allowed: bool
    status: str
    metric_name: str = ""
    error_message: str = ""
    recovery_action: str = ""


def evaluate_commercial_gate(*, tenant: TenantRecord | None, metric_name: str, usage: UsageCounterRecord | None) -> CommercialGateDecision:
    if tenant is None:
        return CommercialGateDecision(False, "tenant_missing", metric_name, "No tenant is configured.", "Create or select a tenant before retrying.")
    if tenant.subscription_status in {"past_due", "suspended", "canceled"}:
        return CommercialGateDecision(False, f"tenant_{tenant.subscription_status}", metric_name, f"Tenant subscription_status={tenant.subscription_status} blocks new actions.", "Reactivate the tenant before starting new automated actions.")
    if usage is not None and usage.limit_count >= 0 and usage.used_count >= usage.limit_count:
        return CommercialGateDecision(False, "quota_exhausted", usage.metric_name, f"Quota exhausted for {usage.metric_name}: {usage.used_count}/{usage.limit_count}.", "Raise the plan limit or wait for the next quota period.")
    return CommercialGateDecision(True, "allowed", metric_name)
```

- [ ] **Step 3: Verify and commit**

Run:

```bash
pytest tests/test_commercial_profile_policy.py -v
git add src/boss_agent_cli/rag_reply/profile_policy.py tests/test_commercial_profile_policy.py
git commit -m "feat: add commercial profile gates"
```

Expected: pytest PASS.

## Task 4: Profile-Aware RAG Connector

**Files:**
- Create: `src/boss_agent_cli/rag_reply/adapters/rag_profile.py`
- Modify: `tests/test_rag_reply_rag_http.py`
- Test: `tests/test_rag_profile_connector.py`

- [ ] **Step 1: Write connector tests**

Create `tests/test_rag_profile_connector.py`:

```python
from types import SimpleNamespace

from boss_agent_cli.rag_reply.adapters.rag_profile import RagProfileConnector


def test_ask_profile_requires_complete_identity():
    connector = RagProfileConnector(rag_adapter=SimpleNamespace(answer=lambda **kwargs: None))

    result = connector.ask_profile(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="",
        knowledge_base_id="kb_ai",
        question="介绍一下项目。",
        conversation_id="conv_001",
    )

    assert result.ok is False
    assert result.audit_status == "profile_context_invalid"
    assert result.send_allowed is False


def test_ask_profile_wraps_current_chat_ask_without_metadata():
    captured = {}

    def fake_answer(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            ok=True,
            answer="我负责企业级 RAG 项目。",
            citations=[{"id": "c1"}],
            reasoning_summary={},
            raw_response={"answer": "我负责企业级 RAG 项目。"},
            error_message=None,
            audit_status="draft_created",
            send_allowed=False,
            approval_required=True,
        )

    connector = RagProfileConnector(rag_adapter=SimpleNamespace(answer=fake_answer))
    result = connector.ask_profile(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
        question="介绍一下项目。",
        conversation_id="conv_001",
    )

    assert result.ok is True
    assert captured["rag_question"] == "介绍一下项目。"
    assert captured["session_id"].startswith("boss-profile-")
    assert "metadata" not in captured
    assert result.profile_context["profile_id"] == "profile_ai"
```

- [ ] **Step 2: Implement connector**

Create `rag_profile.py` with:

```python
@dataclass(slots=True)
class RagProfileAnswerResult:
    ok: bool
    answer: str
    citations: list[dict[str, object]]
    profile_context: dict[str, str]
    reasoning_summary: dict[str, object] | None = None
    raw_response: dict[str, object] | None = None
    error_message: str | None = None
    audit_status: str = "draft_created"
    send_allowed: bool = False
    approval_required: bool = True


class RagProfileConnector:
    def __init__(self, *, rag_adapter) -> None:
        self.rag_adapter = rag_adapter

    def ask_profile(self, *, tenant_id: str, user_id: str, profile_id: str, knowledge_base_id: str, question: str, conversation_id: str, mode: str = "accurate") -> RagProfileAnswerResult:
        profile_context = {
            "tenant_id": tenant_id.strip(),
            "user_id": user_id.strip(),
            "profile_id": profile_id.strip(),
            "knowledge_base_id": knowledge_base_id.strip(),
        }
        if not all(profile_context.values()):
            return RagProfileAnswerResult(False, "", [], profile_context, error_message="tenant_id/user_id/profile_id/knowledge_base_id are required.", audit_status="profile_context_invalid")
        session_hash = hashlib.sha1(f"{conversation_id}:{profile_id}:{knowledge_base_id}".encode("utf-8")).hexdigest()[:16]
        result = self.rag_adapter.answer(
            rag_question=question,
            session_id=f"boss-profile-{session_hash}",
            mode=mode,
        )
        return RagProfileAnswerResult(
            ok=bool(result.ok),
            answer=str(result.answer or ""),
            citations=list(result.citations or []),
            profile_context=profile_context,
            reasoning_summary=result.reasoning_summary,
            raw_response=result.raw_response,
            error_message=result.error_message,
            audit_status=result.audit_status,
            send_allowed=False,
            approval_required=True,
        )
```

Add import for `hashlib`. Keep upload/status methods as explicit future-facing methods when the external RAG exposes endpoints; do not route upload through `/api/v1/chat/ask`.

- [ ] **Step 3: Preserve `RagHttpAdapter` chat/ask contract**

Do not add `metadata`, `tenant_id`, `user_id`, `profile_id`, or `knowledge_base_id` into `RagHttpAdapter.answer()` payload for current `/api/v1/chat/ask`.

Keep this assertion in `tests/test_rag_reply_rag_http.py`:

```python
assert "metadata" not in captured["json"]
```

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest tests/test_rag_profile_connector.py tests/test_rag_reply_rag_http.py -v
git add src/boss_agent_cli/rag_reply/adapters/rag_profile.py tests/test_rag_profile_connector.py tests/test_rag_reply_rag_http.py
git commit -m "feat: add profile-aware RAG connector"
```

Expected: pytest PASS.

## Task 5: Reply Path Profile Binding

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/service.py`
- Modify: `src/boss_agent_cli/rag_reply/question_builder.py`
- Test: `tests/test_rag_reply_profile_binding.py`

- [ ] **Step 1: Write binding tests**

Create `tests/test_rag_reply_profile_binding.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.profile_models import ConversationProfileBindingRecord
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _store(tmp_path: Path) -> RagReplyStore:
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return store


def test_fact_question_without_profile_binding_is_blocked(tmp_path: Path):
    store = _store(tmp_path)
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
    store.save_message(MessageRecord(message_id="msg_001", conversation_id="conv_001", message_text="介绍一下你的 RAG 项目。", direction="inbound"))
    service = BossRagReplyService(
        store=store,
        rag_adapter=SimpleNamespace(answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("legacy RAG should not be called"))),
        profile_service=ProfileService(store),
    )

    draft = service.create_draft_for_message("msg_001")

    assert draft.audit_status == "profile_binding_required"
    assert draft.send_allowed is False
    assert "profile_binding_required" in draft.risk_labels


def test_fact_question_uses_bound_profile_connector(tmp_path: Path):
    store = _store(tmp_path)
    profile_service = ProfileService(store)
    profile_service.bind_conversation(
        ConversationProfileBindingRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            conversation_id="conv_001",
            profile_id="profile_ai",
            knowledge_base_id="kb_ai",
        )
    )
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
    store.save_message(MessageRecord(message_id="msg_001", conversation_id="conv_001", message_text="介绍一下你的 RAG 项目。", direction="inbound"))
    captured = {}

    def fake_ask_profile(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            ok=True,
            answer="我负责企业级 RAG 项目。",
            citations=[{"id": "c1"}],
            profile_context={
                "tenant_id": kwargs["tenant_id"],
                "user_id": kwargs["user_id"],
                "profile_id": kwargs["profile_id"],
                "knowledge_base_id": kwargs["knowledge_base_id"],
            },
            reasoning_summary={},
            raw_response={},
            error_message=None,
            audit_status="draft_created",
            send_allowed=False,
            approval_required=True,
        )

    service = BossRagReplyService(
        store=store,
        rag_adapter=SimpleNamespace(answer=lambda **kwargs: None),
        profile_service=profile_service,
        profile_rag_connector=SimpleNamespace(ask_profile=fake_ask_profile),
    )

    draft = service.create_draft_for_message("msg_001")

    assert captured["profile_id"] == "profile_ai"
    assert captured["knowledge_base_id"] == "kb_ai"
    assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"
    assert store.list_rag_calls("conv_001")[0].request["profile_context"]["tenant_id"] == "tenant_001"
```

- [ ] **Step 2: Extend service constructor**

Add optional dependencies to `BossRagReplyService.__init__`:

```python
profile_service: object | None = None
profile_rag_connector: object | None = None
```

Save them as `self.profile_service` and `self.profile_rag_connector`.

- [ ] **Step 3: Resolve profile binding**

Add `_resolve_profile_context(message)` that returns `{tenant_id,user_id,profile_id,knowledge_base_id}` from `profile_service.get_conversation_binding(message.conversation_id)`. If `profile_service` is present and binding is missing, `_build_rag_backed_draft()` returns a draft with:

```python
audit_status="profile_binding_required"
send_allowed=False
approval_required=True
risk_labels=[*decision.risk_labels, "profile_binding_required"]
evidence={"source": "profile_policy", "reason": "profile_binding_required"}
```

- [ ] **Step 4: Call profile connector and record evidence**

When `profile_context` exists, call:

```python
profile_result = self.profile_rag_connector.ask_profile(
    tenant_id=profile_context["tenant_id"],
    user_id=profile_context["user_id"],
    profile_id=profile_context["profile_id"],
    knowledge_base_id=profile_context["knowledge_base_id"],
    question=rag_question,
    conversation_id=message.conversation_id,
)
```

Save `RagCallRecord.request` with:

```python
{
    "question": rag_question,
    "message_id": message.message_id,
    "profile_context": profile_context,
}
```

Do not put profile identity inside the natural-language `rag_question`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest tests/test_rag_reply_profile_binding.py tests/test_rag_reply_service.py tests/test_rag_reply_question_builder.py -v
git add src/boss_agent_cli/rag_reply/service.py src/boss_agent_cli/rag_reply/question_builder.py tests/test_rag_reply_profile_binding.py
git commit -m "feat: bind RAG replies to commercial profiles"
```

Expected: pytest PASS.

## Task 6: Profile CLI Surface

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_commercial_profile_commands.py`

- [ ] **Step 1: Write CLI tests**

Create `tests/test_commercial_profile_commands.py`:

```python
import json
from pathlib import Path

from click.testing import CliRunner

from boss_agent_cli.main import cli


def _json(output: str) -> dict:
    return json.loads(output)["data"]


def test_agent_profile_create_list_config_and_bind(tmp_path: Path):
    runner = CliRunner()
    create = runner.invoke(
        cli,
        [
            "--json", "--data-dir", str(tmp_path),
            "agent", "profile", "create",
            "--tenant-id", "tenant_001",
            "--user-id", "user_001",
            "--name", "AI 应用工程师",
            "--target-title", "AI Application Engineer",
            "--knowledge-base-id", "kb_ai",
        ],
    )
    assert create.exit_code == 0
    profile_id = _json(create.output)["profile"]["profile_id"]

    config = runner.invoke(
        cli,
        [
            "--json", "--data-dir", str(tmp_path),
            "agent", "profile", "config", "set",
            "--tenant-id", "tenant_001",
            "--profile-id", profile_id,
            "--contact-phone", "13800138000",
            "--contact-wechat", "reggie-ai",
            "--interview-windows", "工作日 20:00 后",
            "--reply-auto-send-enabled",
        ],
    )
    assert config.exit_code == 0

    bind = runner.invoke(
        cli,
        [
            "--json", "--data-dir", str(tmp_path),
            "agent", "conversation", "bind-profile",
            "--conversation-id", "conv_001",
            "--tenant-id", "tenant_001",
            "--user-id", "user_001",
            "--profile-id", profile_id,
        ],
    )
    assert bind.exit_code == 0
    assert _json(bind.output)["binding"]["knowledge_base_id"] == "kb_ai"
```

- [ ] **Step 2: Add CLI helpers and groups**

In `commands/rag.py`, add:

```python
def _resolve_profile_service(ctx: click.Context) -> ProfileService:
    store = _resolve_store(ctx)
    store.initialize()
    return ProfileService(store)
```

Add groups under existing `rag_group`:

```python
@rag_group.group("profile")
def rag_profile_group() -> None:
    """Manage commercial profiles."""

@rag_group.group("conversation")
def rag_conversation_group() -> None:
    """Manage conversation profile bindings."""

@rag_group.group("usage")
def rag_usage_group() -> None:
    """Inspect commercial usage counters."""
```

Required commands:

- `agent profile create --tenant-id --user-id --name --target-title [--knowledge-base-id]`
- `agent profile list --tenant-id --user-id`
- `agent profile config set --tenant-id --profile-id [--contact-phone] [--contact-wechat] [--interview-windows] [--salary-reply-policy] [--resume-attachment-path] [--reply-auto-send-enabled/--no-reply-auto-send-enabled] [--outreach-auto-send-enabled/--no-outreach-auto-send-enabled] [--proactive-resume-enabled/--no-proactive-resume-enabled]`
- `agent profile upload --tenant-id --user-id --profile-id --type --file`
- `agent profile upload-status --profile-id`
- `agent conversation bind-profile --conversation-id --tenant-id --user-id --profile-id [--binding-source manual|default|imported]`
- `agent conversation profile --conversation-id`
- `agent usage summary --tenant-id [--user-id] [--profile-id]`

- [ ] **Step 3: Verify and commit**

Run:

```bash
pytest tests/test_commercial_profile_commands.py tests/test_rag_reply_commands.py::test_agent_group_alias_is_registered -v
git add src/boss_agent_cli/commands/rag.py tests/test_commercial_profile_commands.py
git commit -m "feat: add commercial profile CLI"
```

Expected: pytest PASS.

## Task 7: Wire CLI Ask To Profile Layer

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Add ask wiring test**

Add a test to `tests/test_rag_reply_commands.py` that:

- creates a profile with `knowledge_base_id="kb_ai"`,
- binds `demo-session-001`,
- monkeypatches `RagProfileConnector.ask_profile`,
- runs `boss --json --data-dir <tmp> agent ask --conversation-id demo-session-001 --question "介绍一下你的 RAG 项目。"`,
- asserts captured `profile_id` and `knowledge_base_id`.

Use this assertion block:

```python
assert captured["profile_id"] == profile_id
assert captured["knowledge_base_id"] == "kb_ai"
assert payload["data"]["draft"]["evidence"]["profile_context"]["profile_id"] == profile_id
```

- [ ] **Step 2: Inject profile dependencies**

Modify `_build_service(ctx)`:

```python
store = _resolve_store(ctx)
config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
rag_adapter = RagHttpAdapter(
    base_url=config.get("boss_rag_rag_base_url"),
    timeout_seconds=int(config.get("boss_rag_rag_timeout_seconds", 20)),
    api_key=config.get("boss_rag_rag_api_key"),
    auth_mode=str(config.get("boss_rag_rag_auth_mode", "none")),
)
profile_service = ProfileService(store)
return BossRagReplyService(
    store=store,
    rag_adapter=rag_adapter,
    fallback_adapter=_build_ai_fallback_adapter(ctx),
    agent_answer_adapter=_build_agent_answer_adapter(ctx),
    profile_service=profile_service,
    profile_rag_connector=RagProfileConnector(rag_adapter=rag_adapter),
    salary_reply=str(config.get("boss_rag_salary_reply") or ""),
    interview_windows=str(config.get("boss_rag_interview_windows") or ""),
)
```

- [ ] **Step 3: Verify and commit**

Run:

```bash
pytest tests/test_rag_reply_commands.py tests/test_rag_reply_profile_binding.py -v
git add src/boss_agent_cli/commands/rag.py tests/test_rag_reply_commands.py
git commit -m "feat: wire agent ask to profile RAG"
```

Expected: pytest PASS.

## Task 8: Watcher And Outreach Gates

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/watcher_config.py`
- Modify: `src/boss_agent_cli/rag_reply/auto_actions.py`
- Modify: `src/boss_agent_cli/rag_reply/agent_tools.py`
- Modify: `demo/interview-simulator/vite.config.mjs`
- Test: `tests/test_passive_watcher.py`
- Test: `tests/test_rag_reply_agent_tools.py`

- [ ] **Step 1: Add effective config tests**

Add tests proving:

- `ProfileConfig.reply_auto_send_enabled=False` blocks live watcher send but still allows draft creation.
- `ProfileConfig.outreach_auto_send_enabled=False` blocks `/api/boss/auto-greet` commercial path.
- `ProfileConfig.proactive_resume_enabled=False` prevents optional proactive resume attachment.
- missing contact, interview windows, salary policy, or resume path stays blocked/manual for matching intents.

Core expectation:

```python
assert result.ok is False
assert result.error_code in {"SEND_DISABLED", "PROFILE_CONFIG_DISABLED", "INVALID_PARAM"}
```

- [ ] **Step 2: Add effective config resolver**

In `watcher_config.py`, add a pure function:

```python
def with_profile_config(base: WatcherConfig, profile_config: ProfileConfigRecord | None) -> WatcherConfig:
    if profile_config is None:
        return base
    return WatcherConfig(
        enabled=base.enabled,
        dry_run=base.dry_run,
        contact_phone=profile_config.contact_phone,
        contact_wechat=profile_config.contact_wechat,
        interview_windows=profile_config.interview_windows,
        resume_attachment_path=profile_config.resume_attachment_path,
        poll_seconds=base.poll_seconds,
        max_failures_per_conversation=base.max_failures_per_conversation,
        read_no_reply_followup_limit_per_cycle=base.read_no_reply_followup_limit_per_cycle,
        live_sync=base.live_sync,
        require_send_enabled=base.require_send_enabled,
        send_enabled=base.send_enabled and profile_config.reply_auto_send_enabled,
        proactive_resume_enabled=profile_config.proactive_resume_enabled,
    )
```

- [ ] **Step 3: Gate outbound sends**

In `BossAgentToolbox.send_boss_reply_guarded()`, return a blocked result when live sending is requested and the effective profile config disables reply auto-send.

For `/api/boss/auto-greet` in `vite.config.mjs`, require `profile_id` from the frontend once profile console exists. Before invoking the existing `batch-greet` command, call a new bridge helper that checks `agent conversation profile` or `agent profile list` and blocks when `outreach_auto_send_enabled` is false.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest tests/test_passive_watcher.py tests/test_rag_reply_agent_tools.py -v
npm --prefix demo/interview-simulator run build
git add src/boss_agent_cli/rag_reply/watcher_config.py src/boss_agent_cli/rag_reply/auto_actions.py src/boss_agent_cli/rag_reply/agent_tools.py demo/interview-simulator/vite.config.mjs tests/test_passive_watcher.py tests/test_rag_reply_agent_tools.py
git commit -m "feat: apply profile gates to watcher and outreach"
```

Expected: pytest PASS and Vite build success.

## Task 9: Frontend Bridge Contract

**Files:**
- Create: `demo/interview-simulator/server/profileBridge.mjs`
- Modify: `demo/interview-simulator/vite.config.mjs`
- Test: `tests/test_interview_simulator_contract.py`

- [ ] **Step 1: Add text contract tests**

Extend `tests/test_interview_simulator_contract.py`:

```python
def test_interview_simulator_exposes_profile_bridge_without_removing_existing_flows():
    repo_root = Path(__file__).resolve().parents[1]
    vite = (repo_root / "demo" / "interview-simulator" / "vite.config.mjs").read_text(encoding="utf-8")
    profile_bridge = (repo_root / "demo" / "interview-simulator" / "server" / "profileBridge.mjs").read_text(encoding="utf-8")
    app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")

    for token in ("/api/agent/profiles", "/api/agent/profile-binding", "/api/agent/usage"):
        assert token in profile_bridge
    for existing in ("/api/agent/ask", "/api/agent/send", "/api/boss/auto-greet", "Boss 自动开聊", "Agent 全自动"):
        assert existing in vite or existing in app
```

- [ ] **Step 2: Extract bridge module**

Create `server/profileBridge.mjs` exporting:

```js
function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function responseData(payload) {
  return payload && typeof payload === "object" && "data" in payload ? payload.data : payload;
}

function appendTextOption(args, flag, value) {
  const normalized = String(value || "").trim();
  if (normalized) args.push(flag, normalized);
}

function appendBooleanOption(args, enabledFlag, disabledFlag, value) {
  if (value === true) args.push(enabledFlag);
  if (value === false) args.push(disabledFlag);
}

function profileIdFromPath(pathname, suffix) {
  return decodeURIComponent(pathname.slice("/api/agent/profiles/".length, -suffix.length));
}

export function createProfileBridgeHandlers({ bridgeConfig, runBossJsonCommand, readBody }) {
  return async function handleProfileBridge(req, res) {
    const url = new URL(req.url, "http://127.0.0.1");
    try {
      if (req.method === "GET" && url.pathname === "/api/agent/profiles") {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "list",
          "--tenant-id",
          String(url.searchParams.get("tenant_id") || "tenant_local"),
          "--user-id",
          String(url.searchParams.get("user_id") || "user_local"),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "POST" && url.pathname === "/api/agent/profiles") {
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "profile",
          "create",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--name",
          String(body.name || body.display_name || ""),
          "--target-title",
          String(body.target_title || ""),
        ];
        appendTextOption(args, "--knowledge-base-id", body.knowledge_base_id);
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "PATCH" && url.pathname.startsWith("/api/agent/profiles/") && url.pathname.endsWith("/config")) {
        const profileId = profileIdFromPath(url.pathname, "/config");
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "profile",
          "config",
          "set",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--profile-id",
          profileId,
        ];
        appendTextOption(args, "--contact-phone", body.contact_phone);
        appendTextOption(args, "--contact-wechat", body.contact_wechat);
        appendTextOption(args, "--interview-windows", body.interview_windows);
        appendTextOption(args, "--salary-reply-policy", body.salary_reply_policy);
        appendTextOption(args, "--resume-attachment-path", body.resume_attachment_path);
        appendBooleanOption(args, "--reply-auto-send-enabled", "--no-reply-auto-send-enabled", body.reply_auto_send_enabled);
        appendBooleanOption(args, "--outreach-auto-send-enabled", "--no-outreach-auto-send-enabled", body.outreach_auto_send_enabled);
        appendBooleanOption(args, "--proactive-resume-enabled", "--no-proactive-resume-enabled", body.proactive_resume_enabled);
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "POST" && url.pathname.startsWith("/api/agent/profiles/") && url.pathname.endsWith("/uploads")) {
        const profileId = profileIdFromPath(url.pathname, "/uploads");
        const body = JSON.parse((await readBody(req)) || "{}");
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "upload",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--profile-id",
          profileId,
          "--type",
          String(body.source_type || "other"),
          "--file",
          String(body.file_path || ""),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "GET" && url.pathname.startsWith("/api/agent/profiles/") && url.pathname.endsWith("/uploads")) {
        const profileId = profileIdFromPath(url.pathname, "/uploads");
        const payload = await runBossJsonCommand(bridgeConfig, ["agent", "profile", "upload-status", "--profile-id", profileId]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "POST" && url.pathname === "/api/agent/profile-binding") {
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "conversation",
          "bind-profile",
          "--conversation-id",
          String(body.conversation_id || ""),
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--profile-id",
          String(body.profile_id || ""),
        ];
        appendTextOption(args, "--binding-source", body.binding_source);
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "GET" && url.pathname === "/api/agent/profile-binding") {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "conversation",
          "profile",
          "--conversation-id",
          String(url.searchParams.get("conversation_id") || ""),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
      if (req.method === "GET" && url.pathname === "/api/agent/usage") {
        const args = ["agent", "usage", "summary", "--tenant-id", String(url.searchParams.get("tenant_id") || "tenant_local")];
        appendTextOption(args, "--user-id", url.searchParams.get("user_id"));
        appendTextOption(args, "--profile-id", url.searchParams.get("profile_id"));
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
    } catch (error) {
      sendJson(res, 500, { ok: false, errorMessage: error instanceof Error ? error.message : "Profile bridge request failed." });
      return true;
    }
    return false;
  };
}
```

Each handler calls the corresponding `boss agent profile`, `boss agent conversation`, or `boss agent usage` command and returns `{ ok: true, data }` or `{ ok: false, errorMessage }`.

- [ ] **Step 3: Register module in Vite**

In `vite.config.mjs`, import `createProfileBridgeHandlers`, construct it beside existing bridge helpers, and call it before existing `isAgentAsk`/`isAgentSend` blocks:

```js
if (await handleProfileBridge(req, res)) return;
```

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest tests/test_interview_simulator_contract.py -v
npm --prefix demo/interview-simulator run build
git add demo/interview-simulator/server/profileBridge.mjs demo/interview-simulator/vite.config.mjs tests/test_interview_simulator_contract.py
git commit -m "feat: expose profile bridge endpoints"
```

Expected: pytest PASS and Vite build success.

## Task 10: Product Design Frontend Refactor

**Files:**
- Create: `demo/interview-simulator/src/api/agentClient.js`
- Create: `demo/interview-simulator/src/views/ReplyWorkspace.jsx`
- Create: `demo/interview-simulator/src/views/OutreachWorkspace.jsx`
- Create: `demo/interview-simulator/src/views/ProfileHub.jsx`
- Create: `demo/interview-simulator/src/components/profile/ProfileSelector.jsx`
- Create: `demo/interview-simulator/src/components/profile/ProfileConfigPanel.jsx`
- Modify: `demo/interview-simulator/src/App.jsx`
- Modify: `demo/interview-simulator/src/styles.css`
- Test: `tests/test_interview_simulator_contract.py`

- [ ] **Step 1: Run Product Design brief gate**

Before editing UI, run Product Design workflow:

```text
Use `product-design:get-context` playback for:
- product: BOSS Agent commercial console
- visual source: existing demo app plus selected Product Design mock/reference
- interactivity: full local bridge controls
```

If no visual target is selected, run `product-design:ideate`, present exactly 3 options, and wait for user selection before code changes.

- [ ] **Step 2: Split data client**

Create `src/api/agentClient.js` with functions:

```js
function query(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) {
      search.set(key, String(value));
    }
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

async function requestJson(path, options = {}) {
  const init = { method: options.method || "GET" };
  if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.errorMessage || `Request failed: ${path}`);
  }
  return payload.data === undefined ? payload : payload.data;
}

export async function fetchProfiles({ tenantId, userId }) {
  return requestJson(`/api/agent/profiles${query({ tenant_id: tenantId, user_id: userId })}`);
}

export async function createProfile(payload) {
  return requestJson("/api/agent/profiles", { method: "POST", body: payload });
}

export async function updateProfileConfig(profileId, payload) {
  return requestJson(`/api/agent/profiles/${encodeURIComponent(profileId)}/config`, { method: "PATCH", body: payload });
}

export async function fetchProfileUploads(profileId) {
  return requestJson(`/api/agent/profiles/${encodeURIComponent(profileId)}/uploads`);
}

export async function bindConversationProfile(payload) {
  return requestJson("/api/agent/profile-binding", { method: "POST", body: payload });
}

export async function fetchConversationProfile(conversationId) {
  return requestJson(`/api/agent/profile-binding${query({ conversation_id: conversationId })}`);
}

export async function fetchUsage(params) {
  return requestJson(`/api/agent/usage${query(params)}`);
}

export async function askAgent(payload) {
  return requestJson("/api/agent/ask", { method: "POST", body: payload });
}

export async function sendAgentDraft(payload) {
  return requestJson("/api/agent/send", { method: "POST", body: payload });
}

export async function fetchWatcherStatus() {
  return requestJson("/api/agent/watcher/status");
}

export async function runWatcherOnce(payload) {
  return requestJson("/api/agent/watcher/run", { method: "POST", body: payload || {} });
}

export async function searchBoss(payload) {
  return requestJson("/api/boss/search", { method: "POST", body: payload });
}

export async function autoGreetBoss(payload) {
  return requestJson("/api/boss/auto-greet", { method: "POST", body: payload });
}
```

- [ ] **Step 3: Split views without removing strings**

Move existing reply/test conversation UI into `ReplyWorkspace.jsx`, existing Boss 自动开聊 UI into `OutreachWorkspace.jsx`, and new profile controls into `ProfileHub.jsx`.

`App.jsx` becomes the shell that owns shared state, selected route/tab, selected profile, selected conversation target, and bridge health. It must still render these user-visible strings:

```text
Boss 自动开聊
Agent 全自动
发送到 Boss
发送附件简历 PDF
watcher
```

- [ ] **Step 4: Chrome MCP QA**

Because this is a frontend behavior/design change, run Chrome MCP or the repo-approved browser QA flow against the local Vite server. Check desktop and mobile widths for:

- profile hub visible and usable,
- `/agent/reply` retains demo/test conversation,
- `/agent/outreach` retains Boss 自动开聊 and Agent 全自动,
- no overlapping text/buttons,
- profile selector does not block existing send/resume controls.

- [ ] **Step 5: Verify and commit**

Run:

```bash
npm --prefix demo/interview-simulator run build
pytest tests/test_interview_simulator_contract.py -v
git add demo/interview-simulator/src/api/agentClient.js demo/interview-simulator/src/views/ReplyWorkspace.jsx demo/interview-simulator/src/views/OutreachWorkspace.jsx demo/interview-simulator/src/views/ProfileHub.jsx demo/interview-simulator/src/components/profile/ProfileSelector.jsx demo/interview-simulator/src/components/profile/ProfileConfigPanel.jsx demo/interview-simulator/src/App.jsx demo/interview-simulator/src/styles.css tests/test_interview_simulator_contract.py
git commit -m "feat: refactor console for profile workflows"
```

Expected: Vite build PASS, pytest PASS, browser QA screenshots acceptable.

## Task 11: Remove Personal Candidate Hardcoding

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/adapters/agent_answer.py`
- Test: `tests/test_agent_answer_no_personal_templates.py`
- Modify: `tests/test_rag_reply_agent_answer.py`

- [ ] **Step 1: Write hardcoding tests**

Create `tests/test_agent_answer_no_personal_templates.py`:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.adapters.agent_answer import AgentAnswerAdapter


def test_agent_answer_source_has_no_personal_candidate_facts():
    source = Path("src/boss_agent_cli/rag_reply/adapters/agent_answer.py").read_text(encoding="utf-8")
    for token in ("宁波伟立", "89 个 API", "26 个核心 schema", "企业级 RAG 知识库与智能问答平台"):
        assert token not in source


def test_personal_answer_without_ai_or_profile_grounding_fails_closed():
    adapter = AgentAnswerAdapter(ai_service=None)

    result = adapter.answer(
        message_text="请做一个简短的自我介绍。",
        intent="resume_question",
        job_summary=None,
        rag_answer="",
        citations=[],
    )

    assert result.ok is False
    assert result.audit_status == "agent_answer_failed"
    assert result.raw_response == {"mode": "profile_required"}
```

- [ ] **Step 2: Remove local personal templates**

In `agent_answer.py`, delete `_template_answer_for_interview_question()` and its call. Keep `_recruiter_invitation_answer()` because it is generic. When `rag_answer` is empty and AI is unavailable for a personal/fact answer, return:

```python
AgentAnswerResult(
    ok=False,
    answer="",
    reasoning_summary={"strategy": "profile_grounding_required"},
    raw_response={"mode": "profile_required"},
    error_message="Personal candidate answers require bound profile RAG grounding.",
    audit_status="agent_answer_failed",
)
```

- [ ] **Step 3: Update old tests**

In `tests/test_rag_reply_agent_answer.py`, replace tests expecting hardcoded self-introduction/project details with profile-required failure expectations. Keep tests for:

- grounded answer first-person rewrite,
- direct general AI answer,
- generic recruiter invitation fallback,
- non-empty grounded answer rule-based cleanup.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest tests/test_agent_answer_no_personal_templates.py tests/test_rag_reply_agent_answer.py tests/test_rag_reply_profile_binding.py -v
git add src/boss_agent_cli/rag_reply/adapters/agent_answer.py tests/test_agent_answer_no_personal_templates.py tests/test_rag_reply_agent_answer.py
git commit -m "refactor: require profile grounding for personal answers"
```

Expected: pytest PASS.

## Task 12: Final Regression And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/boss-agent-current-stage.md`
- Test: focused backend/frontend checks

- [ ] **Step 1: Add durable docs**

In `README.md`, add a short `Commercial Profile Layer` section explaining:

- tenant/user/profile model,
- profile uploads and RAG binding,
- conversation binding,
- profile config as the source for contact/interview/salary/resume/send flags,
- payment provider fields are stored but callbacks are out of scope,
- existing reply/outreach/watcher capabilities remain.

In `docs/boss-agent-current-stage.md`, add current implementation status and live Boss verification boundary.

- [ ] **Step 2: Run focused regression**

Run:

```bash
pytest \
  tests/test_commercial_profile_schema.py \
  tests/test_commercial_profile_service.py \
  tests/test_commercial_profile_policy.py \
  tests/test_rag_profile_connector.py \
  tests/test_rag_reply_profile_binding.py \
  tests/test_commercial_profile_commands.py \
  tests/test_agent_answer_no_personal_templates.py \
  tests/test_rag_reply_agent_answer.py \
  tests/test_rag_reply_rag_http.py \
  tests/test_rag_reply_commands.py \
  tests/test_passive_watcher.py \
  tests/test_rag_reply_agent_tools.py \
  tests/test_interview_simulator_contract.py \
  -v
npm --prefix demo/interview-simulator run build
```

Expected: pytest PASS and Vite build success.

- [ ] **Step 3: Preservation scan**

Run:

```bash
rg -n "Boss 自动开聊|Agent 全自动|/api/boss/auto-greet|/api/agent/ask|/api/agent/send|send_attachment_resume|boss-mcp" demo/interview-simulator src pyproject.toml
```

Expected: output proves old Boss auto-greet, agent ask/send, attachment resume, and MCP surfaces still exist.

- [ ] **Step 4: Live Boss verification rule**

If implementation changed Boss search, auto-greet, browser fetch, CDP, Bridge delivery, or outreach aggregation behavior, run one bounded real Boss verification and report:

```text
total_greeted=<value>
total_failed=<value>
stopped_reason=<value>
platform_error=<value>
```

If only profile persistence, tests, local RAG context, docs, and frontend data wiring changed, report that live Boss verification was not run because no live Boss delivery path changed.

- [ ] **Step 5: Commit docs**

Run:

```bash
git add README.md docs/boss-agent-current-stage.md
git commit -m "docs: document commercial profile layer"
```

Expected: one focused docs commit.
