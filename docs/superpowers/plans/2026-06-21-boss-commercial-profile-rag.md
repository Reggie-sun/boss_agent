# Boss Commercial Profile RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a commercial-ready self-hosted profile layer for `BOSS_AGENT` while preserving current reply, watcher, auto-greet, auto-resume, CLI, MCP, Docker, and frontend demo capabilities.

**Architecture:** Add a profile hub beside the existing `rag_reply` workflow: profile data and commercial state live in the local Boss Agent SQLite store, RAG documents stay in the external RAG service behind a thin connector, and existing reply/outreach flows receive `tenant_id/user_id/profile_id/knowledge_base_id` context through explicit bindings. The first implementation keeps payments as stored metadata only, but makes quota and usage gates real.

**Tech Stack:** Python 3.10+, Click, sqlite3, httpx, dataclasses, pytest, React/Vite, existing Boss Agent bridge, existing CDP fail-closed delivery helpers.

---

## Scope Check

The approved spec spans multiple surfaces: local persistence, RAG request context, reply generation, outreach, frontend, and commercial usage gates. This plan keeps it one MVP because each task produces a working slice and preserves the old product at every step. Payment callbacks, multi-provider RAG migration, and organization-scale candidate pools remain out of scope.

## File Structure

- Create `src/boss_agent_cli/rag_reply/profile_models.py`  
  Owns commercial/profile dataclasses, status constants, and feature names.

- Create `src/boss_agent_cli/rag_reply/profile_service.py`  
  Owns profile/tenant/user/upload/binding/usage SQLite read-write helpers using the existing `RagReplyStore` connection.

- Create `src/boss_agent_cli/rag_reply/profile_policy.py`  
  Owns license/subscription/quota gate decisions and usage consume helpers.

- Create `src/boss_agent_cli/rag_reply/adapters/rag_profile.py`  
  Owns thin profile-aware RAG connector methods for knowledge base creation, upload, status, and ask.

- Modify `src/boss_agent_cli/rag_reply/schema.py`  
  Adds commercial/profile tables without changing existing table names or deleting data.

- Modify `src/boss_agent_cli/rag_reply/service.py`  
  Resolves conversation profile bindings for fact questions and records profile context in RAG requests/evidence.

- Modify `src/boss_agent_cli/rag_reply/adapters/rag_http.py`  
  Accepts optional profile context metadata while preserving existing `/api/v1/chat/ask` behavior.

- Modify `src/boss_agent_cli/rag_reply/question_builder.py`  
  Keeps question text minimal and adds profile context as structured metadata instead of prompt stuffing.

- Modify `src/boss_agent_cli/rag_reply/adapters/agent_answer.py`  
  Removes hardcoded personal candidate templates; keeps only generic answer shaping and conservative fallback.

- Modify `src/boss_agent_cli/rag_reply/watcher_config.py`, `src/boss_agent_cli/rag_reply/agent_tools.py`, and `src/boss_agent_cli/rag_reply/auto_actions.py`  
  Uses profile config for high-risk fields and separates reply/outreach auto-send gates.

- Modify `src/boss_agent_cli/commands/rag.py`  
  Adds profile, binding, upload, usage, and gate commands under the existing `agent`/`rag` workflow alias.

- Modify `demo/interview-simulator/vite.config.mjs`  
  Adds local profile/usage API bridge endpoints and forwards profile context to existing ask/send/outreach endpoints.

- Modify `demo/interview-simulator/src/App.jsx` and `demo/interview-simulator/src/styles.css`  
  Adds a small profile console and route/tab split while preserving the existing test conversation and Boss auto-greet panel.

- Add tests:
  - `tests/test_commercial_profile_store.py`
  - `tests/test_commercial_profile_policy.py`
  - `tests/test_rag_profile_connector.py`
  - `tests/test_rag_reply_profile_binding.py`
  - `tests/test_commercial_profile_commands.py`
  - `tests/test_agent_answer_no_personal_templates.py`
  - Extend `tests/test_rag_reply_commands.py`, `tests/test_passive_watcher.py`, `tests/test_rag_reply_agent_tools.py`, and `tests/test_rag_reply_rag_http.py`.

---

### Task 1: Commercial Profile Persistence

**Files:**
- Create: `src/boss_agent_cli/rag_reply/profile_models.py`
- Create: `src/boss_agent_cli/rag_reply/profile_service.py`
- Modify: `src/boss_agent_cli/rag_reply/schema.py`
- Test: `tests/test_commercial_profile_store.py`

- [ ] **Step 1: Write failing profile persistence tests**

Create `tests/test_commercial_profile_store.py`:

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


def _profile_service(tmp_path: Path) -> ProfileService:
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return ProfileService(store)


def test_profile_service_round_trips_tenant_user_profile_config_and_binding(tmp_path: Path):
    service = _profile_service(tmp_path)
    tenant = TenantRecord(tenant_id="tenant_001", display_name="Demo Tenant")
    user = UserRecord(tenant_id="tenant_001", user_id="user_001", display_name="Reggie", email="r@example.com")
    profile = UserProfileRecord(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        display_name="AI 应用工程师",
        target_title="AI Application Engineer",
        knowledge_base_id="kb_ai",
    )
    config = ProfileConfigRecord(
        tenant_id="tenant_001",
        profile_id="profile_ai",
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        salary_reply_policy="薪资需本人确认",
        resume_attachment_path="/tmp/resume.pdf",
        reply_auto_send_enabled=True,
        outreach_auto_send_enabled=False,
        proactive_resume_enabled=True,
    )
    binding = ConversationProfileBindingRecord(
        tenant_id="tenant_001",
        conversation_id="boss_conv_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
        binding_source="manual",
    )

    service.save_tenant(tenant)
    service.save_user(user)
    service.save_profile(profile)
    service.save_profile_config(config)
    service.bind_conversation(binding)

    assert service.get_tenant("tenant_001").display_name == "Demo Tenant"
    assert service.list_profiles("tenant_001", "user_001")[0].profile_id == "profile_ai"
    assert service.get_profile_config("profile_ai").contact_wechat == "reggie-ai"
    assert service.get_conversation_binding("boss_conv_001").knowledge_base_id == "kb_ai"


def test_profile_service_tracks_upload_status_and_usage(tmp_path: Path):
    service = _profile_service(tmp_path)
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

    assert service.list_uploads("profile_ai")[0].status == "indexed"
    usage = service.get_usage_counter("tenant_001", "profile_ai", "rag_calls", "2026-06-01", "2026-07-01")
    assert usage.used_count == 3
    assert usage.limit_count == 50
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_commercial_profile_store.py -v`

Expected: FAIL with `ModuleNotFoundError` for `boss_agent_cli.rag_reply.profile_models`.

- [ ] **Step 3: Add profile dataclasses**

Create `src/boss_agent_cli/rag_reply/profile_models.py`:

```python
"""Commercial profile domain models for Boss Agent."""

from __future__ import annotations

from dataclasses import dataclass

from boss_agent_cli.rag_reply.models import utc_now_iso


SUBSCRIPTION_STATUSES = {"trial", "active", "past_due", "suspended", "canceled"}
PLAN_CODES = {"free", "pro", "team", "enterprise"}
PROFILE_STATUSES = {"active", "archived"}
UPLOAD_STATUSES = {"queued", "uploaded", "indexed", "failed"}
BINDING_SOURCES = {"manual", "default", "imported"}


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
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


@dataclass(slots=True)
class UserRecord:
    tenant_id: str
    user_id: str
    display_name: str
    email: str
    role: str = "owner"
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


@dataclass(slots=True)
class UserProfileRecord:
    tenant_id: str
    user_id: str
    profile_id: str
    display_name: str
    target_title: str
    knowledge_base_id: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


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
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.updated_at = self.updated_at or utc_now_iso()


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
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


@dataclass(slots=True)
class ConversationProfileBindingRecord:
    tenant_id: str
    conversation_id: str
    user_id: str
    profile_id: str
    knowledge_base_id: str
    binding_source: str = "manual"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now


@dataclass(slots=True)
class UsageCounterRecord:
    tenant_id: str
    user_id: str
    profile_id: str
    metric_name: str
    period_start: str
    period_end: str
    used_count: int = 0
    limit_count: int = 0
    updated_at: str = ""

    def __post_init__(self) -> None:
        self.updated_at = self.updated_at or utc_now_iso()
```

- [ ] **Step 4: Add profile tables to the schema**

Append these SQL statements to `CREATE_TABLE_STATEMENTS` in `src/boss_agent_cli/rag_reply/schema.py`:

```python
    """
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        subscription_status TEXT NOT NULL,
        license_key_hash TEXT NOT NULL,
        payment_provider TEXT NOT NULL,
        provider_customer_id TEXT NOT NULL,
        provider_subscription_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        profile_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        display_name TEXT NOT NULL,
        target_title TEXT NOT NULL,
        knowledge_base_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_configs (
        profile_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        contact_phone TEXT NOT NULL,
        contact_wechat TEXT NOT NULL,
        interview_windows TEXT NOT NULL,
        salary_reply_policy TEXT NOT NULL,
        resume_attachment_path TEXT NOT NULL,
        reply_auto_send_enabled INTEGER NOT NULL,
        outreach_auto_send_enabled INTEGER NOT NULL,
        proactive_resume_enabled INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_uploads (
        upload_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        source_filename TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_size_bytes INTEGER NOT NULL,
        rag_document_id TEXT NOT NULL,
        status TEXT NOT NULL,
        error_message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_profile_bindings (
        conversation_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        knowledge_base_id TEXT NOT NULL,
        binding_source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_counters (
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        profile_id TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        used_count INTEGER NOT NULL,
        limit_count INTEGER NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (tenant_id, profile_id, metric_name, period_start, period_end)
    )
    """,
```

- [ ] **Step 5: Add the profile service**

Create `src/boss_agent_cli/rag_reply/profile_service.py` with these public methods:

```python
"""SQLite service for commercial Boss Agent profiles."""

from __future__ import annotations

import sqlite3

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


class ProfileService:
    def __init__(self, store: RagReplyStore) -> None:
        self.store = store

    def save_tenant(self, record: TenantRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tenants (
                    tenant_id, display_name, plan_code, subscription_status,
                    license_key_hash, payment_provider, provider_customer_id,
                    provider_subscription_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.tenant_id,
                    record.display_name,
                    record.plan_code,
                    record.subscription_status,
                    record.license_key_hash,
                    record.payment_provider,
                    record.provider_customer_id,
                    record.provider_subscription_id,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return None if row is None else _tenant_from_row(row)

    def save_user(self, record: UserRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO users (
                    user_id, tenant_id, display_name, email, role, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.user_id,
                    record.tenant_id,
                    record.display_name,
                    record.email,
                    record.role,
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def save_profile(self, record: UserProfileRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_profiles (
                    profile_id, tenant_id, user_id, display_name, target_title,
                    knowledge_base_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.profile_id,
                    record.tenant_id,
                    record.user_id,
                    record.display_name,
                    record.target_title,
                    record.knowledge_base_id,
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def list_profiles(self, tenant_id: str, user_id: str) -> list[UserProfileRecord]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_profiles
                WHERE tenant_id = ? AND user_id = ?
                ORDER BY updated_at DESC, profile_id
                """,
                (tenant_id, user_id),
            ).fetchall()
        return [_profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: str) -> UserProfileRecord | None:
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE profile_id = ?", (profile_id,)).fetchone()
        return None if row is None else _profile_from_row(row)

    def save_profile_config(self, record: ProfileConfigRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO profile_configs (
                    profile_id, tenant_id, contact_phone, contact_wechat,
                    interview_windows, salary_reply_policy, resume_attachment_path,
                    reply_auto_send_enabled, outreach_auto_send_enabled,
                    proactive_resume_enabled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.profile_id,
                    record.tenant_id,
                    record.contact_phone,
                    record.contact_wechat,
                    record.interview_windows,
                    record.salary_reply_policy,
                    record.resume_attachment_path,
                    int(record.reply_auto_send_enabled),
                    int(record.outreach_auto_send_enabled),
                    int(record.proactive_resume_enabled),
                    record.updated_at,
                ),
            )
            conn.commit()

    def get_profile_config(self, profile_id: str) -> ProfileConfigRecord | None:
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM profile_configs WHERE profile_id = ?", (profile_id,)).fetchone()
        return None if row is None else _config_from_row(row)

    def bind_conversation(self, record: ConversationProfileBindingRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO conversation_profile_bindings (
                    conversation_id, tenant_id, user_id, profile_id, knowledge_base_id,
                    binding_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.conversation_id,
                    record.tenant_id,
                    record.user_id,
                    record.profile_id,
                    record.knowledge_base_id,
                    record.binding_source,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def get_conversation_binding(self, conversation_id: str) -> ConversationProfileBindingRecord | None:
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_profile_bindings WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return None if row is None else _binding_from_row(row)

    def save_upload(self, record: ProfileUploadRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO profile_uploads (
                    upload_id, tenant_id, user_id, profile_id, source_filename, source_type,
                    source_size_bytes, rag_document_id, status, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.upload_id,
                    record.tenant_id,
                    record.user_id,
                    record.profile_id,
                    record.source_filename,
                    record.source_type,
                    record.source_size_bytes,
                    record.rag_document_id,
                    record.status,
                    record.error_message,
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()

    def list_uploads(self, profile_id: str) -> list[ProfileUploadRecord]:
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM profile_uploads WHERE profile_id = ? ORDER BY created_at, upload_id",
                (profile_id,),
            ).fetchall()
        return [_upload_from_row(row) for row in rows]

    def save_usage_counter(self, record: UsageCounterRecord) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO usage_counters (
                    tenant_id, user_id, profile_id, metric_name, period_start, period_end,
                    used_count, limit_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.tenant_id,
                    record.user_id,
                    record.profile_id,
                    record.metric_name,
                    record.period_start,
                    record.period_end,
                    record.used_count,
                    record.limit_count,
                    record.updated_at,
                ),
            )
            conn.commit()

    def get_usage_counter(
        self,
        tenant_id: str,
        profile_id: str,
        metric_name: str,
        period_start: str,
        period_end: str,
    ) -> UsageCounterRecord | None:
        with self.store.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM usage_counters
                WHERE tenant_id = ? AND profile_id = ? AND metric_name = ?
                  AND period_start = ? AND period_end = ?
                """,
                (tenant_id, profile_id, metric_name, period_start, period_end),
            ).fetchone()
        return None if row is None else _usage_from_row(row)
```

Add row helper functions at the bottom of the same file:

```python
def _tenant_from_row(row: sqlite3.Row) -> TenantRecord:
    return TenantRecord(**{key: row[key] for key in row.keys()})


def _profile_from_row(row: sqlite3.Row) -> UserProfileRecord:
    return UserProfileRecord(**{key: row[key] for key in row.keys()})


def _config_from_row(row: sqlite3.Row) -> ProfileConfigRecord:
    return ProfileConfigRecord(
        tenant_id=str(row["tenant_id"]),
        profile_id=str(row["profile_id"]),
        contact_phone=str(row["contact_phone"]),
        contact_wechat=str(row["contact_wechat"]),
        interview_windows=str(row["interview_windows"]),
        salary_reply_policy=str(row["salary_reply_policy"]),
        resume_attachment_path=str(row["resume_attachment_path"]),
        reply_auto_send_enabled=bool(row["reply_auto_send_enabled"]),
        outreach_auto_send_enabled=bool(row["outreach_auto_send_enabled"]),
        proactive_resume_enabled=bool(row["proactive_resume_enabled"]),
        updated_at=str(row["updated_at"]),
    )


def _binding_from_row(row: sqlite3.Row) -> ConversationProfileBindingRecord:
    return ConversationProfileBindingRecord(**{key: row[key] for key in row.keys()})


def _upload_from_row(row: sqlite3.Row) -> ProfileUploadRecord:
    return ProfileUploadRecord(**{key: row[key] for key in row.keys()})


def _usage_from_row(row: sqlite3.Row) -> UsageCounterRecord:
    return UsageCounterRecord(**{key: row[key] for key in row.keys()})
```

- [ ] **Step 6: Run profile persistence tests**

Run: `pytest tests/test_commercial_profile_store.py tests/test_rag_reply_store.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/boss_agent_cli/rag_reply/profile_models.py src/boss_agent_cli/rag_reply/profile_service.py src/boss_agent_cli/rag_reply/schema.py tests/test_commercial_profile_store.py
git commit -m "feat: add commercial profile persistence"
```

---

### Task 2: Commercial Usage And Quota Gates

**Files:**
- Create: `src/boss_agent_cli/rag_reply/profile_policy.py`
- Modify: `src/boss_agent_cli/rag_reply/profile_service.py`
- Test: `tests/test_commercial_profile_policy.py`

- [ ] **Step 1: Write failing gate tests**

Create `tests/test_commercial_profile_policy.py`:

```python
from boss_agent_cli.rag_reply.profile_models import TenantRecord, UsageCounterRecord
from boss_agent_cli.rag_reply.profile_policy import (
    FEATURE_OUTREACH_AUTO_GREET,
    FEATURE_PROFILE_CREATE,
    FEATURE_RAG_ASK,
    CommercialGateDecision,
    evaluate_commercial_gate,
)


def test_gate_allows_active_tenant_under_quota():
    decision = evaluate_commercial_gate(
        tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="active"),
        feature=FEATURE_RAG_ASK,
        usage=UsageCounterRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="profile_ai",
            metric_name=FEATURE_RAG_ASK,
            period_start="2026-06-01",
            period_end="2026-07-01",
            used_count=9,
            limit_count=10,
        ),
    )

    assert decision == CommercialGateDecision(allowed=True, status="allowed")


def test_gate_blocks_suspended_tenant_but_allows_history_read_hint():
    decision = evaluate_commercial_gate(
        tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="suspended"),
        feature=FEATURE_OUTREACH_AUTO_GREET,
        usage=None,
    )

    assert decision.allowed is False
    assert decision.status == "tenant_suspended"
    assert decision.recovery_action == "Reactivate the tenant before starting new automated actions."


def test_gate_blocks_quota_exhaustion():
    decision = evaluate_commercial_gate(
        tenant=TenantRecord(tenant_id="tenant_001", display_name="Demo", subscription_status="active"),
        feature=FEATURE_PROFILE_CREATE,
        usage=UsageCounterRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="",
            metric_name=FEATURE_PROFILE_CREATE,
            period_start="2026-06-01",
            period_end="2026-07-01",
            used_count=1,
            limit_count=1,
        ),
    )

    assert decision.allowed is False
    assert decision.status == "quota_exhausted"
    assert decision.metric_name == FEATURE_PROFILE_CREATE
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_commercial_profile_policy.py -v`

Expected: FAIL with `ModuleNotFoundError` for `boss_agent_cli.rag_reply.profile_policy`.

- [ ] **Step 3: Add gate policy**

Create `src/boss_agent_cli/rag_reply/profile_policy.py`:

```python
"""Commercial feature gates for Boss Agent profiles."""

from __future__ import annotations

from dataclasses import dataclass

from boss_agent_cli.rag_reply.profile_models import TenantRecord, UsageCounterRecord

FEATURE_PROFILE_CREATE = "profile_create"
FEATURE_PROFILE_UPLOAD = "profile_upload"
FEATURE_RAG_ASK = "rag_calls"
FEATURE_REPLY_AUTO_SEND = "reply_auto_send"
FEATURE_OUTREACH_AUTO_GREET = "outreach_auto_greet"
FEATURE_ATTACHMENT_RESUME_SEND = "attachment_resume_send"

BLOCKED_SUBSCRIPTIONS = {"past_due", "suspended", "canceled"}


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
    feature: str,
    usage: UsageCounterRecord | None,
) -> CommercialGateDecision:
    if tenant is None:
        return CommercialGateDecision(
            allowed=False,
            status="tenant_missing",
            metric_name=feature,
            error_message="No tenant is configured for this commercial action.",
            recovery_action="Create or select a tenant before retrying.",
        )
    if tenant.subscription_status in BLOCKED_SUBSCRIPTIONS:
        return CommercialGateDecision(
            allowed=False,
            status=f"tenant_{tenant.subscription_status}",
            metric_name=feature,
            error_message=f"Tenant subscription_status={tenant.subscription_status} blocks new automated actions.",
            recovery_action="Reactivate the tenant before starting new automated actions.",
        )
    if usage is not None and usage.limit_count >= 0 and usage.used_count >= usage.limit_count:
        return CommercialGateDecision(
            allowed=False,
            status="quota_exhausted",
            metric_name=usage.metric_name,
            error_message=f"Quota exhausted for {usage.metric_name}: {usage.used_count}/{usage.limit_count}.",
            recovery_action="Raise the plan limit or wait for the next quota period.",
        )
    return CommercialGateDecision(allowed=True, status="allowed", metric_name=feature)
```

- [ ] **Step 4: Add usage consume helper**

Add this method to `ProfileService` in `src/boss_agent_cli/rag_reply/profile_service.py`:

```python
    def increment_usage(
        self,
        *,
        tenant_id: str,
        profile_id: str,
        metric_name: str,
        period_start: str,
        period_end: str,
        amount: int = 1,
    ) -> UsageCounterRecord:
        existing = self.get_usage_counter(
            tenant_id,
            profile_id,
            metric_name,
            period_start,
            period_end,
        )
        if existing is None:
            existing = UsageCounterRecord(
                tenant_id=tenant_id,
                user_id="",
                profile_id=profile_id,
                metric_name=metric_name,
                period_start=period_start,
                period_end=period_end,
                used_count=0,
                limit_count=-1,
            )
        next_record = UsageCounterRecord(
            tenant_id=existing.tenant_id,
            user_id=existing.user_id,
            profile_id=existing.profile_id,
            metric_name=existing.metric_name,
            period_start=existing.period_start,
            period_end=existing.period_end,
            used_count=existing.used_count + max(amount, 0),
            limit_count=existing.limit_count,
        )
        self.save_usage_counter(next_record)
        return next_record
```

- [ ] **Step 5: Run gate tests**

Run: `pytest tests/test_commercial_profile_policy.py tests/test_commercial_profile_store.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/profile_policy.py src/boss_agent_cli/rag_reply/profile_service.py tests/test_commercial_profile_policy.py
git commit -m "feat: add commercial usage gates"
```

---

### Task 3: Profile-Aware RAG Connector

**Files:**
- Create: `src/boss_agent_cli/rag_reply/adapters/rag_profile.py`
- Modify: `src/boss_agent_cli/rag_reply/adapters/rag_http.py`
- Test: `tests/test_rag_profile_connector.py`
- Test: `tests/test_rag_reply_rag_http.py`

- [ ] **Step 1: Write failing connector tests**

Create `tests/test_rag_profile_connector.py`:

```python
from pathlib import Path

import httpx

from boss_agent_cli.rag_reply.adapters.rag_profile import RagProfileConnector


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_rag_profile_connector_uploads_with_identity(monkeypatch, tmp_path: Path):
    captured = {}
    upload_file = tmp_path / "resume.txt"
    upload_file.write_text("resume text", encoding="utf-8")

    def fake_post(url, *, data=None, files=None, json=None, timeout, headers=None):
        captured["url"] = url
        captured["data"] = data
        captured["has_file"] = bool(files)
        return _Response({"rag_document_id": "doc_001", "status": "uploaded"})

    monkeypatch.setattr(httpx, "post", fake_post)
    connector = RagProfileConnector(base_url="http://127.0.0.1:8020", timeout_seconds=11)

    result = connector.upload_profile_document(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
        file_path=upload_file,
        source_type="resume",
    )

    assert result.ok is True
    assert result.rag_document_id == "doc_001"
    assert captured["url"].endswith("/api/v1/profile-documents")
    assert captured["data"]["tenant_id"] == "tenant_001"
    assert captured["data"]["profile_id"] == "profile_ai"
    assert captured["data"]["knowledge_base_id"] == "kb_ai"
    assert captured["has_file"] is True


def test_rag_profile_connector_fails_closed_when_base_url_missing(tmp_path: Path):
    upload_file = tmp_path / "resume.txt"
    upload_file.write_text("resume text", encoding="utf-8")
    connector = RagProfileConnector(base_url="", timeout_seconds=11)

    result = connector.upload_profile_document(
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
        file_path=upload_file,
        source_type="resume",
    )

    assert result.ok is False
    assert result.status == "failed"
```

- [ ] **Step 2: Extend existing RAG HTTP tests for metadata**

Add this test to `tests/test_rag_reply_rag_http.py`:

```python
def test_rag_http_includes_profile_context_when_provided(monkeypatch):
    captured = {}

    def fake_post(url, *, json, timeout, headers=None):
        captured["json"] = json
        return _Response({"answer": "draft", "citations": [{"id": "c1"}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = RagHttpAdapter(base_url="http://127.0.0.1:8020", timeout_seconds=12)

    result = adapter.answer(
        rag_question="HR question: hi",
        session_id="sess_001",
        tenant_id="tenant_001",
        user_id="user_001",
        profile_id="profile_ai",
        knowledge_base_id="kb_ai",
    )

    assert result.ok is True
    assert captured["json"]["tenant_id"] == "tenant_001"
    assert captured["json"]["user_id"] == "user_001"
    assert captured["json"]["profile_id"] == "profile_ai"
    assert captured["json"]["knowledge_base_id"] == "kb_ai"
```

- [ ] **Step 3: Run failing connector tests**

Run: `pytest tests/test_rag_profile_connector.py tests/test_rag_reply_rag_http.py::test_rag_http_includes_profile_context_when_provided -v`

Expected: FAIL because `RagProfileConnector` does not exist and `RagHttpAdapter.answer()` does not accept profile context.

- [ ] **Step 4: Add profile connector**

Create `src/boss_agent_cli/rag_reply/adapters/rag_profile.py`:

```python
"""Thin connector for profile-aware Enterprise RAG operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass(slots=True)
class RagProfileOperationResult:
    ok: bool
    status: str
    knowledge_base_id: str = ""
    rag_document_id: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


class RagProfileConnector:
    def __init__(self, *, base_url: str | None, timeout_seconds: int = 20, api_key: str | None = None) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = (api_key or "").strip()

    def upload_profile_document(
        self,
        *,
        tenant_id: str,
        user_id: str,
        profile_id: str,
        knowledge_base_id: str,
        file_path: Path,
        source_type: str,
    ) -> RagProfileOperationResult:
        if not self.base_url:
            return RagProfileOperationResult(ok=False, status="failed", error_message="rag_base_url_missing")
        headers = {"X-API-Key": self.api_key} if self.api_key else None
        try:
            with Path(file_path).open("rb") as handle:
                response = httpx.post(
                    f"{self.base_url}/api/v1/profile-documents",
                    data={
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "profile_id": profile_id,
                        "knowledge_base_id": knowledge_base_id,
                        "source_type": source_type,
                    },
                    files={"file": (Path(file_path).name, handle)},
                    timeout=self.timeout_seconds,
                    headers=headers,
                )
            response.raise_for_status()
            data = response.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            return RagProfileOperationResult(ok=False, status="failed", error_message=str(exc))
        return RagProfileOperationResult(
            ok=True,
            status=str(data.get("status") or "uploaded"),
            knowledge_base_id=str(data.get("knowledge_base_id") or knowledge_base_id),
            rag_document_id=str(data.get("rag_document_id") or data.get("document_id") or ""),
            raw_response=data if isinstance(data, dict) else {},
        )
```

- [ ] **Step 5: Extend `RagHttpAdapter.answer` signature**

Modify `src/boss_agent_cli/rag_reply/adapters/rag_http.py` so the method accepts profile context:

```python
    def answer(
        self,
        *,
        rag_question: str,
        session_id: str,
        mode: str = "accurate",
        tenant_id: str | None = None,
        user_id: str | None = None,
        profile_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> RagAnswerResult:
        """Return a closed result when the HTTP call fails."""
        if not self.base_url:
            return RagAnswerResult(
                ok=False,
                answer="",
                error_message="boss_rag_rag_base_url is not configured.",
                audit_status="rag_failed",
            )
        payload = {
            "question": rag_question,
            "session_id": session_id,
            "mode": mode,
        }
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if user_id:
            payload["user_id"] = user_id
        if profile_id:
            payload["profile_id"] = profile_id
        if knowledge_base_id:
            payload["knowledge_base_id"] = knowledge_base_id
```

Keep the existing HTTP call and result parsing below this payload block unchanged.

- [ ] **Step 6: Run connector and HTTP tests**

Run: `pytest tests/test_rag_profile_connector.py tests/test_rag_reply_rag_http.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/boss_agent_cli/rag_reply/adapters/rag_profile.py src/boss_agent_cli/rag_reply/adapters/rag_http.py tests/test_rag_profile_connector.py tests/test_rag_reply_rag_http.py
git commit -m "feat: add profile-aware RAG connector"
```

---

### Task 4: Reply Path Profile Binding

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/service.py`
- Modify: `src/boss_agent_cli/rag_reply/question_builder.py`
- Test: `tests/test_rag_reply_profile_binding.py`

- [ ] **Step 1: Write failing binding tests**

Create `tests/test_rag_reply_profile_binding.py`:

```python
from pathlib import Path
from types import SimpleNamespace

from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.profile_models import ConversationProfileBindingRecord
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_rag_reply_uses_bound_profile_context(tmp_path: Path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
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
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍一下你的 RAG 项目。",
            direction="inbound",
        )
    )
    captured = {}
    service = BossRagReplyService(
        store=store,
        rag_adapter=SimpleNamespace(
            answer=lambda **kwargs: captured.setdefault("kwargs", kwargs)
            or SimpleNamespace(
                ok=True,
                answer="我负责企业级 RAG 项目。",
                citations=[{"id": "c1"}],
                reasoning_summary={},
                raw_response={},
                error_message=None,
                audit_status="draft_created",
                send_allowed=False,
                approval_required=True,
            )
        ),
        profile_service=profile_service,
    )

    draft = service.create_draft_for_message("msg_001")

    assert draft.audit_status == "draft_created"
    assert captured["kwargs"]["tenant_id"] == "tenant_001"
    assert captured["kwargs"]["profile_id"] == "profile_ai"
    assert captured["kwargs"]["knowledge_base_id"] == "kb_ai"
    assert draft.evidence["profile_context"]["profile_id"] == "profile_ai"


def test_fact_question_without_profile_binding_is_blocked(tmp_path: Path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="manual_import"))
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍一下你的 RAG 项目。",
            direction="inbound",
        )
    )
    service = BossRagReplyService(
        store=store,
        rag_adapter=SimpleNamespace(answer=lambda **kwargs: (_ for _ in ()).throw(AssertionError("RAG should not be called"))),
        profile_service=ProfileService(store),
    )

    draft = service.create_draft_for_message("msg_001")

    assert draft.audit_status == "profile_binding_required"
    assert draft.send_allowed is False
    assert draft.approval_required is True
```

- [ ] **Step 2: Run failing binding tests**

Run: `pytest tests/test_rag_reply_profile_binding.py -v`

Expected: FAIL because `BossRagReplyService.__init__()` does not accept `profile_service`.

- [ ] **Step 3: Extend service protocols and constructor**

In `src/boss_agent_cli/rag_reply/service.py`, update `RagAdapterProtocol.answer` and `BossRagReplyService.__init__`:

```python
class RagAdapterProtocol(Protocol):
    def answer(
        self,
        *,
        rag_question: str,
        session_id: str,
        mode: str = "accurate",
        tenant_id: str | None = None,
        user_id: str | None = None,
        profile_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> RagAnswerProtocol:
        ...
```

```python
    def __init__(
        self,
        *,
        store: RagReplyStore,
        rag_adapter: RagAdapterProtocol,
        fallback_adapter: FallbackAdapterProtocol | None = None,
        agent_answer_adapter: AgentAnswerAdapterProtocol | None = None,
        profile_service: object | None = None,
        salary_reply: str = "",
        interview_windows: str = "",
    ) -> None:
        self.store = store
        self.rag_adapter = rag_adapter
        self.fallback_adapter = fallback_adapter
        self.agent_answer_adapter = agent_answer_adapter
        self.profile_service = profile_service
        self.salary_reply = salary_reply.strip()
        self.interview_windows = interview_windows.strip()
```

- [ ] **Step 4: Add profile context resolver**

Add this method to `BossRagReplyService`:

```python
    def _resolve_profile_context(self, message: MessageRecord) -> dict[str, str]:
        service = self.profile_service
        if service is None or not hasattr(service, "get_conversation_binding"):
            return {}
        binding = service.get_conversation_binding(message.conversation_id)
        if binding is None:
            return {}
        return {
            "tenant_id": binding.tenant_id,
            "user_id": binding.user_id,
            "profile_id": binding.profile_id,
            "knowledge_base_id": binding.knowledge_base_id,
        }
```

- [ ] **Step 5: Block fact RAG questions without binding when profile service is enabled**

At the beginning of `_build_rag_backed_draft`, after `job_summary = self._resolve_job_summary(message)`, add:

```python
        profile_context = self._resolve_profile_context(message)
        if self.profile_service is not None and not profile_context:
            return DraftRecord.new(
                conversation_id=message.conversation_id,
                source_message_id=message.message_id,
                draft_text="",
                intent=classification.intent,
                risk_labels=[*decision.risk_labels, "profile_binding_required"],
                evidence={
                    "source": "profile_policy",
                    "reason": "profile_binding_required",
                },
                approval_required=True,
                send_allowed=False,
                audit_status="profile_binding_required",
            )
```

- [ ] **Step 6: Pass profile context into RAG and evidence**

Update the `self.rag_adapter.answer(...)` call:

```python
        rag_result = self.rag_adapter.answer(
            rag_question=rag_question,
            session_id=rag_session_id,
            tenant_id=profile_context.get("tenant_id"),
            user_id=profile_context.get("user_id"),
            profile_id=profile_context.get("profile_id"),
            knowledge_base_id=profile_context.get("knowledge_base_id"),
        )
```

Add profile context to the RAG call request and draft evidence:

```python
request={
    "question": rag_question,
    "session_id": rag_session_id,
    "message_id": message.message_id,
    "profile_context": profile_context,
}
```

```python
evidence: dict[str, object] = {
    "source": evidence_source,
    "citations": rag_result.citations,
    "reasoning_summary": reasoning_summary,
    "profile_context": profile_context,
}
```

- [ ] **Step 7: Run binding tests**

Run: `pytest tests/test_rag_reply_profile_binding.py tests/test_rag_reply_service.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/boss_agent_cli/rag_reply/service.py src/boss_agent_cli/rag_reply/question_builder.py tests/test_rag_reply_profile_binding.py
git commit -m "feat: bind conversations to commercial profiles"
```

---

### Task 5: Profile CLI Commands

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_commercial_profile_commands.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_commercial_profile_commands.py`:

```python
import json
from pathlib import Path

from click.testing import CliRunner

from boss_agent_cli.main import cli


def test_agent_profile_create_list_and_bind(tmp_path: Path):
    runner = CliRunner()

    create = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "profile",
            "create",
            "--tenant-id",
            "tenant_001",
            "--user-id",
            "user_001",
            "--name",
            "AI 应用工程师",
            "--target-title",
            "AI Application Engineer",
            "--knowledge-base-id",
            "kb_ai",
        ],
    )
    assert create.exit_code == 0
    created = json.loads(create.output)
    assert created["data"]["profile"]["profile_id"].startswith("profile_")

    profile_id = created["data"]["profile"]["profile_id"]
    bind = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "conversation",
            "bind-profile",
            "--conversation-id",
            "conv_001",
            "--tenant-id",
            "tenant_001",
            "--user-id",
            "user_001",
            "--profile-id",
            profile_id,
        ],
    )
    assert bind.exit_code == 0
    assert json.loads(bind.output)["data"]["binding"]["profile_id"] == profile_id


def test_agent_usage_summary_reports_empty_usage(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "--data-dir", str(tmp_path), "agent", "usage", "summary", "--tenant-id", "tenant_001"],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["tenant_id"] == "tenant_001"
```

- [ ] **Step 2: Run failing CLI tests**

Run: `pytest tests/test_commercial_profile_commands.py -v`

Expected: FAIL because `agent profile` and `agent conversation` command groups do not exist.

- [ ] **Step 3: Add profile service builder and serializers**

In `src/boss_agent_cli/commands/rag.py`, add imports:

```python
from boss_agent_cli.rag_reply.profile_models import (
    ConversationProfileBindingRecord,
    ProfileConfigRecord,
    ProfileUploadRecord,
    TenantRecord,
    UserProfileRecord,
    UserRecord,
)
from boss_agent_cli.rag_reply.profile_service import ProfileService
```

Add helpers near `_resolve_store`:

```python
def _resolve_profile_service(ctx: click.Context) -> ProfileService:
    return ProfileService(_resolve_store(ctx))


def _profile_payload(profile: UserProfileRecord) -> dict[str, object]:
    return {
        "tenant_id": profile.tenant_id,
        "user_id": profile.user_id,
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "target_title": profile.target_title,
        "knowledge_base_id": profile.knowledge_base_id,
        "status": profile.status,
    }


def _binding_payload(binding: ConversationProfileBindingRecord) -> dict[str, object]:
    return {
        "tenant_id": binding.tenant_id,
        "conversation_id": binding.conversation_id,
        "user_id": binding.user_id,
        "profile_id": binding.profile_id,
        "knowledge_base_id": binding.knowledge_base_id,
        "binding_source": binding.binding_source,
    }
```

- [ ] **Step 4: Add nested CLI groups**

Append these command groups before `rag_audit_cmd`:

```python
@rag_group.group("profile")
@click.pass_context
def rag_profile_group(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


@rag_profile_group.command("create")
@click.option("--tenant-id", required=True)
@click.option("--user-id", required=True)
@click.option("--name", required=True)
@click.option("--target-title", required=True)
@click.option("--knowledge-base-id", default="")
@click.pass_context
def rag_profile_create_cmd(
    ctx: click.Context,
    tenant_id: str,
    user_id: str,
    name: str,
    target_title: str,
    knowledge_base_id: str,
) -> None:
    service = _resolve_profile_service(ctx)
    service.save_tenant(TenantRecord(tenant_id=tenant_id, display_name=tenant_id))
    service.save_user(UserRecord(tenant_id=tenant_id, user_id=user_id, display_name=user_id, email=""))
    profile = UserProfileRecord(
        tenant_id=tenant_id,
        user_id=user_id,
        profile_id=new_id("profile"),
        display_name=name,
        target_title=target_title,
        knowledge_base_id=knowledge_base_id,
    )
    service.save_profile(profile)
    service.save_profile_config(ProfileConfigRecord(tenant_id=tenant_id, profile_id=profile.profile_id))
    handle_output(ctx, _workflow_command(ctx, "profile-create"), {"profile": _profile_payload(profile)})


@rag_profile_group.command("list")
@click.option("--tenant-id", required=True)
@click.option("--user-id", required=True)
@click.pass_context
def rag_profile_list_cmd(ctx: click.Context, tenant_id: str, user_id: str) -> None:
    service = _resolve_profile_service(ctx)
    profiles = [_profile_payload(profile) for profile in service.list_profiles(tenant_id, user_id)]
    handle_output(ctx, _workflow_command(ctx, "profile-list"), {"profiles": profiles, "count": len(profiles)})


@rag_group.group("conversation")
@click.pass_context
def rag_conversation_group(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


@rag_conversation_group.command("bind-profile")
@click.option("--conversation-id", required=True)
@click.option("--tenant-id", required=True)
@click.option("--user-id", required=True)
@click.option("--profile-id", required=True)
@click.option("--binding-source", default="manual")
@click.pass_context
def rag_conversation_bind_profile_cmd(
    ctx: click.Context,
    conversation_id: str,
    tenant_id: str,
    user_id: str,
    profile_id: str,
    binding_source: str,
) -> None:
    service = _resolve_profile_service(ctx)
    profile = service.get_profile(profile_id)
    if profile is None:
        handle_error_output(
            ctx,
            _workflow_command(ctx, "conversation-bind-profile"),
            code="PROFILE_NOT_FOUND",
            message=f"Unknown profile_id={profile_id}",
            recoverable=False,
        )
        return
    binding = ConversationProfileBindingRecord(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        user_id=user_id,
        profile_id=profile_id,
        knowledge_base_id=profile.knowledge_base_id,
        binding_source=binding_source,
    )
    service.bind_conversation(binding)
    handle_output(ctx, _workflow_command(ctx, "conversation-bind-profile"), {"binding": _binding_payload(binding)})


@rag_group.group("usage")
@click.pass_context
def rag_usage_group(ctx: click.Context) -> None:
    ctx.ensure_object(dict)


@rag_usage_group.command("summary")
@click.option("--tenant-id", required=True)
@click.pass_context
def rag_usage_summary_cmd(ctx: click.Context, tenant_id: str) -> None:
    _resolve_profile_service(ctx)
    handle_output(ctx, _workflow_command(ctx, "usage-summary"), {"tenant_id": tenant_id, "usage": []})
```

- [ ] **Step 5: Run CLI tests**

Run: `pytest tests/test_commercial_profile_commands.py tests/test_rag_reply_commands.py::test_agent_group_alias_is_registered -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/commands/rag.py tests/test_commercial_profile_commands.py
git commit -m "feat: add commercial profile CLI commands"
```

---

### Task 6: Wire Profile Context Into CLI Ask And Frontend Bridge

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Modify: `demo/interview-simulator/vite.config.mjs`
- Test: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Add CLI ask test for profile service wiring**

Add this test to `tests/test_rag_reply_commands.py`:

```python
def test_agent_ask_uses_bound_profile_context(monkeypatch, tmp_path: Path):
    captured = {}
    runner = CliRunner()
    create = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "profile",
            "create",
            "--tenant-id",
            "tenant_001",
            "--user-id",
            "user_001",
            "--name",
            "AI 应用工程师",
            "--target-title",
            "AI Application Engineer",
            "--knowledge-base-id",
            "kb_ai",
        ],
    )
    profile_id = json.loads(create.output)["data"]["profile"]["profile_id"]
    runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "conversation",
            "bind-profile",
            "--conversation-id",
            "demo-session-001",
            "--tenant-id",
            "tenant_001",
            "--user-id",
            "user_001",
            "--profile-id",
            profile_id,
        ],
    )

    def fake_answer(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            ok=True,
            answer="我负责企业级 RAG 项目。",
            citations=[{"id": "c1"}],
            reasoning_summary={},
            raw_response={},
            error_message=None,
            audit_status="draft_created",
            send_allowed=False,
            approval_required=True,
        )

    monkeypatch.setattr(
        rag_commands,
        "RagHttpAdapter",
        lambda **kwargs: SimpleNamespace(answer=fake_answer),
    )

    result = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "ask",
            "--conversation-id",
            "demo-session-001",
            "--question",
            "介绍一下你的 RAG 项目。",
        ],
    )

    assert result.exit_code == 0
    assert captured["profile_id"] == profile_id
    assert captured["knowledge_base_id"] == "kb_ai"
```

- [ ] **Step 2: Run failing CLI ask test**

Run: `pytest tests/test_rag_reply_commands.py::test_agent_ask_uses_bound_profile_context -v`

Expected: FAIL because `_build_service()` does not pass `profile_service`.

- [ ] **Step 3: Pass profile service into `_build_service`**

Modify `_build_service()` in `src/boss_agent_cli/commands/rag.py`:

```python
    store = _resolve_store(ctx)
    return BossRagReplyService(
        store=store,
        rag_adapter=rag_adapter,
        fallback_adapter=_build_ai_fallback_adapter(ctx),
        agent_answer_adapter=_build_agent_answer_adapter(ctx),
        profile_service=ProfileService(store),
        salary_reply=str(config.get("boss_rag_salary_reply") or ""),
        interview_windows=str(config.get("boss_rag_interview_windows") or ""),
    )
```

- [ ] **Step 4: Add bridge endpoints for profile list and binding**

In `demo/interview-simulator/vite.config.mjs`, add route flags near other `isAgent...` flags:

```js
    const isAgentProfiles = req.url.startsWith("/api/agent/profiles");
    const isAgentProfileBinding = req.url.startsWith("/api/agent/profile-binding");
```

Add a GET handler before `isAgentAsk`:

```js
    if (req.method === "GET" && isAgentProfiles) {
      const requestUrl = new URL(req.url, "http://127.0.0.1");
      const tenantId = String(requestUrl.searchParams.get("tenant_id") || "tenant_local").trim();
      const userId = String(requestUrl.searchParams.get("user_id") || "user_local").trim();
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "list",
          "--tenant-id",
          tenantId,
          "--user-id",
          userId,
        ]);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, errorMessage: error instanceof Error ? error.message : "读取 profile 失败。" }));
      }
      return true;
    }
```

Add a POST binding handler:

```js
    if (req.method === "POST" && isAgentProfileBinding) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
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
        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(JSON.stringify({ ok: false, errorMessage: error instanceof Error ? error.message : "绑定 profile 失败。" }));
      }
      return true;
    }
```

- [ ] **Step 5: Run CLI and bridge build checks**

Run:

```bash
pytest tests/test_rag_reply_commands.py::test_agent_ask_uses_bound_profile_context tests/test_commercial_profile_commands.py -v
npm --prefix demo/interview-simulator run build
```

Expected: PASS for pytest and successful Vite build.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/commands/rag.py demo/interview-simulator/vite.config.mjs tests/test_rag_reply_commands.py
git commit -m "feat: wire profile context into agent ask"
```

---

### Task 7: Preserve Outreach And Add Commercial Gates

**Files:**
- Modify: `demo/interview-simulator/vite.config.mjs`
- Modify: `src/boss_agent_cli/rag_reply/agent_tools.py`
- Modify: `src/boss_agent_cli/rag_reply/watcher_config.py`
- Test: `tests/test_rag_reply_agent_tools.py`
- Test: `tests/test_passive_watcher.py`

- [ ] **Step 1: Add tests proving profile gates do not remove existing outreach**

Add this test to `tests/test_rag_reply_agent_tools.py`:

```python
def test_reply_auto_send_requires_profile_gate_when_config_is_live(tmp_path):
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        resume_attachment_path=str(tmp_path / "resume.pdf"),
        send_enabled=False,
    )
    result = BossAgentToolbox(
        BossAgentToolContext(
            store=RagReplyStore(tmp_path / "boss-rag.sqlite3"),
            service=SimpleNamespace(create_draft_for_message=lambda message_id: None),
            config=config,
            delivery=SimpleNamespace(send=lambda **kwargs: {}),
        )
    ).send_boss_reply_guarded(
        action={"message": "你好", "status_after_send": "sent"},
        security_id="sec_001",
        target={},
    )

    assert result.ok is False
    assert result.error_code == "SEND_DISABLED"
```

Add this bridge preservation check as a lightweight text test in `tests/test_interview_simulator_bridge.py` if that file exists; otherwise create it:

```python
from pathlib import Path


def test_vite_bridge_preserves_boss_auto_greet_and_search_routes():
    content = Path("demo/interview-simulator/vite.config.mjs").read_text(encoding="utf-8")

    assert 'req.url === "/api/boss/search"' in content
    assert 'req.url === "/api/boss/auto-greet"' in content
    assert '"batch-greet"' in content
    assert 'buildBossDeliveryBlockPayload(browserChannel)' in content
```

- [ ] **Step 2: Run preservation tests**

Run: `pytest tests/test_rag_reply_agent_tools.py::test_reply_auto_send_requires_profile_gate_when_config_is_live tests/test_interview_simulator_bridge.py -v`

Expected: PASS for the existing send-disabled behavior and bridge route preservation. If `tests/test_interview_simulator_bridge.py` is new, the second test should pass immediately because existing routes are present.

- [ ] **Step 3: Split profile send flags in watcher config**

Modify `WatcherConfig` in `src/boss_agent_cli/rag_reply/watcher_config.py` to add:

```python
    reply_auto_send_enabled: bool = False
    outreach_auto_send_enabled: bool = False
```

Update `from_mapping()`:

```python
            reply_auto_send_enabled=bool(
                values.get("boss_rag_reply_auto_send_enabled", values.get("boss_rag_send_enabled", False))
            ),
            outreach_auto_send_enabled=bool(
                values.get("boss_rag_outreach_auto_send_enabled", False)
            ),
```

- [ ] **Step 4: Gate outreach bridge without deleting route**

In `demo/interview-simulator/vite.config.mjs`, keep `/api/boss/auto-greet` unchanged except for passing profile fields through the request body and response metadata. Add this parsing inside the route:

```js
        const tenantId = String(body.tenant_id || "tenant_local").trim();
        const userId = String(body.user_id || "user_local").trim();
        const profileId = String(body.profile_id || "").trim();
```

Add these values to the final JSON response:

```js
          commercialContext: {
            tenant_id: tenantId,
            user_id: userId,
            profile_id: profileId,
            route: "outreach",
          },
```

The route must still call `"batch-greet"` and must still use `buildBossDeliveryBlockPayload(browserChannel)` before delivery.

- [ ] **Step 5: Run focused tests and build**

Run:

```bash
pytest tests/test_rag_reply_agent_tools.py tests/test_passive_watcher.py tests/test_interview_simulator_bridge.py -v
npm --prefix demo/interview-simulator run build
```

Expected: PASS and Vite build succeeds.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/watcher_config.py src/boss_agent_cli/rag_reply/agent_tools.py demo/interview-simulator/vite.config.mjs tests/test_rag_reply_agent_tools.py tests/test_passive_watcher.py tests/test_interview_simulator_bridge.py
git commit -m "feat: preserve outreach behind commercial gates"
```

---

### Task 8: Frontend Profile Console With Existing Demo Preserved

**Files:**
- Modify: `demo/interview-simulator/src/App.jsx`
- Modify: `demo/interview-simulator/src/styles.css`
- Test: `demo/interview-simulator` Vite build

- [ ] **Step 1: Add profile state and loader**

In `demo/interview-simulator/src/App.jsx`, add state near existing `watcherState`:

```jsx
  const [activeAgentRoute, setActiveAgentRoute] = useState("reply");
  const [profiles, setProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [profileError, setProfileError] = useState("");
```

Add loader:

```jsx
  async function loadProfiles() {
    setProfileError("");
    try {
      const response = await fetch("/api/agent/profiles?tenant_id=tenant_local&user_id=user_local");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "读取 profile 失败。");
      }
      const nextProfiles = Array.isArray(payload.data?.profiles) ? payload.data.profiles : [];
      setProfiles(nextProfiles);
      if (!selectedProfileId && nextProfiles.length) {
        setSelectedProfileId(String(nextProfiles[0].profile_id || ""));
      }
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : "读取 profile 失败。");
    }
  }
```

Call `loadProfiles()` in the existing startup `useEffect()` next to `loadChatTargets()`.

- [ ] **Step 2: Pass profile context to ask and auto-greet**

In `handleAsk()`, include profile fields in the `/api/agent/ask` body:

```jsx
          tenant_id: "tenant_local",
          user_id: "user_local",
          profile_id: selectedProfileId,
```

In `handleBossAutoGreet()`, include the same fields in `/api/boss/auto-greet` body:

```jsx
          tenant_id: "tenant_local",
          user_id: "user_local",
          profile_id: selectedProfileId,
```

- [ ] **Step 3: Add route tabs without removing current panels**

Add this JSX above the watcher console section:

```jsx
        <nav className="agent-route-tabs" aria-label="Agent route">
          <button
            type="button"
            className={activeAgentRoute === "reply" ? "is-active" : ""}
            onClick={() => setActiveAgentRoute("reply")}
          >
            对话回复
          </button>
          <button
            type="button"
            className={activeAgentRoute === "outreach" ? "is-active" : ""}
            onClick={() => setActiveAgentRoute("outreach")}
          >
            Boss 自动开聊
          </button>
        </nav>
        <section className="profile-console" aria-label="Profile console">
          <div>
            <strong>Profile</strong>
            <span>{profiles.length ? `${profiles.length} 个 profile` : "暂无 profile"}</span>
          </div>
          <select
            value={selectedProfileId}
            onChange={(event) => setSelectedProfileId(event.target.value)}
          >
            <option value="">未绑定 profile</option>
            {profiles.map((profile) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.display_name || profile.profile_id}
              </option>
            ))}
          </select>
          {profileError ? <p>{profileError}</p> : null}
        </section>
```

Keep the existing test conversation, starter prompts, watcher console, Boss search panel, and send controls in the DOM. Use `activeAgentRoute` only to visually group sections, not to delete or unmount the existing flows.

- [ ] **Step 4: Add compact styles**

Append to `demo/interview-simulator/src/styles.css`:

```css
.agent-route-tabs {
  display: flex;
  gap: 8px;
  margin: 16px 0;
}

.agent-route-tabs button {
  border: 1px solid rgba(15, 23, 42, 0.14);
  background: #fff;
  color: #0f172a;
  border-radius: 8px;
  padding: 8px 12px;
  font: inherit;
  cursor: pointer;
}

.agent-route-tabs button.is-active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
}

.profile-console {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 320px);
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.profile-console strong,
.profile-console span {
  display: block;
}

.profile-console select {
  min-height: 40px;
  border: 1px solid rgba(15, 23, 42, 0.14);
  border-radius: 8px;
  padding: 0 10px;
  background: #fff;
  color: #0f172a;
}

.profile-console p {
  grid-column: 1 / -1;
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}
```

- [ ] **Step 5: Build frontend**

Run: `npm --prefix demo/interview-simulator run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add demo/interview-simulator/src/App.jsx demo/interview-simulator/src/styles.css
git commit -m "feat: add profile console while preserving demo flows"
```

---

### Task 9: Remove Personal Hardcoding From Agent Answer

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/adapters/agent_answer.py`
- Test: `tests/test_agent_answer_no_personal_templates.py`
- Modify: `tests/test_rag_reply_agent_answer.py`

- [ ] **Step 1: Write failing no-hardcoding tests**

Create `tests/test_agent_answer_no_personal_templates.py`:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.adapters.agent_answer import AgentAnswerAdapter


def test_agent_answer_source_has_no_personal_candidate_facts():
    source = Path("src/boss_agent_cli/rag_reply/adapters/agent_answer.py").read_text(encoding="utf-8")

    forbidden = ["孙瑞杰", "宁波伟立", "89 个 API", "26 个核心 schema", "企业级 RAG 知识库与智能问答平台"]
    for token in forbidden:
        assert token not in source


def test_agent_answer_without_ai_and_without_grounding_fails_closed_for_personal_question():
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
    assert "profile" in str(result.error_message).lower()
```

- [ ] **Step 2: Run failing tests**

Run: `pytest tests/test_agent_answer_no_personal_templates.py -v`

Expected: FAIL because `agent_answer.py` still contains personal templates.

- [ ] **Step 3: Remove local personal interview templates**

In `src/boss_agent_cli/rag_reply/adapters/agent_answer.py`, remove `_template_answer_for_interview_question()` and the call that returns `local_interview_template`.

Replace that branch inside `_rule_based_rewrite()` with:

```python
        if not (rag_answer or "").strip():
            return AgentAnswerResult(
                ok=False,
                answer="",
                reasoning_summary={"strategy": "profile_grounding_required"},
                raw_response={"mode": "profile_required"},
                error_message="Personal candidate answers require bound profile RAG grounding.",
                audit_status="agent_answer_failed",
            )
```

Keep `_recruiter_invitation_answer()` because it is generic and does not contain personal candidate facts.

- [ ] **Step 4: Update old tests that expected personal templates**

In `tests/test_rag_reply_agent_answer.py`, replace tests that assert personal hardcoded content with expectations for `agent_answer_failed` or grounded-rule rewrite. Keep tests that verify:

- grounded answer is rewritten into first person.
- direct general answer uses AI service.
- recruiter invitation generic fallback still works.
- AI parse errors with non-empty grounded answer still use rule-based cleanup.

Use this replacement for the old self-introduction hardcoded test:

```python
def test_agent_answer_requires_profile_grounding_for_personal_question_without_ai():
    adapter = AgentAnswerAdapter(ai_service=None)

    result = adapter.answer(
        message_text="请你做一个简短的自我介绍。",
        intent="resume_question",
        job_summary=None,
        rag_answer="",
        citations=[],
    )

    assert result.ok is False
    assert result.audit_status == "agent_answer_failed"
    assert result.raw_response == {"mode": "profile_required"}
```

- [ ] **Step 5: Run agent answer tests**

Run: `pytest tests/test_agent_answer_no_personal_templates.py tests/test_rag_reply_agent_answer.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/adapters/agent_answer.py tests/test_agent_answer_no_personal_templates.py tests/test_rag_reply_agent_answer.py
git commit -m "refactor: require profile grounding for personal answers"
```

---

### Task 10: Final Regression And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/boss-agent-current-stage.md`
- Test: focused pytest suites

- [ ] **Step 1: Add documentation notes**

In `README.md`, add a short section under `Boss Agent V1`:

```markdown
### Commercial Profile Layer

`boss agent profile ...` adds a commercial-ready self-hosted profile layer. A tenant can own users, each user can own multiple profiles, and each Boss conversation can bind to one profile. Candidate facts should come from profile RAG uploads; high-risk fields such as contact details, interview windows, salary policy, resume attachment path, and auto-send flags belong to profile config.

Existing capabilities remain available: demo conversations, watcher replies, Boss auto-greet, search preview, Agent 全自动, and attachment resume delivery. Commercial subscription fields are stored for admin/license workflows, but payment provider callbacks are not connected in this version.
```

In `docs/boss-agent-current-stage.md`, add:

```markdown
## Commercial Profile RAG Layer

The current commercial-ready layer preserves the existing reply and outreach workflows while adding tenant/user/profile identity, profile upload state, conversation binding, usage counters, and quota gates. Live Boss delivery still follows the existing CDP fail-closed rule and attachment resume UI constraints.
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
pytest \
  tests/test_commercial_profile_store.py \
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
  -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `npm --prefix demo/interview-simulator run build`

Expected: PASS.

- [ ] **Step 4: Check preservation strings**

Run:

```bash
rg -n "Boss 自动开聊|Agent 全自动|starterPrompts|/api/boss/auto-greet|/api/agent/ask|send_attachment_resume" demo/interview-simulator/src/App.jsx demo/interview-simulator/vite.config.mjs src/boss_agent_cli
```

Expected: output includes the existing demo prompts, auto-greet endpoint, agent ask endpoint, and attachment resume path.

- [ ] **Step 5: Commit docs and final verification notes**

```bash
git add README.md docs/boss-agent-current-stage.md
git commit -m "docs: document commercial profile layer"
```

- [ ] **Step 6: Live Boss verification rule**

If implementation changed Boss search, auto-greet, browser fetch, CDP, Bridge delivery, or outreach aggregation behavior, run one bounded real Boss verification using the current default UI/CLI filters and report:

```text
total_greeted=<value>
total_failed=<value>
stopped_reason=<value>
platform_error=<value>
```

If only profile persistence, docs, tests, and local RAG context wiring changed, report that live Boss verification was not run because no live Boss delivery path changed.

