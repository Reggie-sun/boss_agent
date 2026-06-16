# Boss Agent Passive Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first passive Boss Agent watcher: a background-style loop with a frontend console that auto-handles inbound HR messages using conservative allowlisted actions.

**Architecture:** Add a small watcher layer beside the existing `rag_reply` workflow. The watcher reuses `BossRagReplyService` for classification/RAG/drafts, wraps delivery behind a testable port, stores decisions in existing `audit_logs`, and exposes CLI commands consumed by the Vite demo bridge and React console.

**Tech Stack:** Python 3.10+, Click, SQLite via `RagReplyStore`, pytest, React/Vite, existing CDP Boss delivery helpers.

---

## File Structure

- Create `src/boss_agent_cli/rag_reply/watcher_config.py`  
  Owns watcher config parsing, fixed contact reply, salary handoff reply, and interview-window reply.

- Create `src/boss_agent_cli/rag_reply/watcher.py`  
  Owns watcher task status, duplicate detection, intent-to-action mapping, single-pass orchestration, and audit payloads.

- Modify `src/boss_agent_cli/rag_reply/classifier.py`  
  Keep `contact_exchange` and `salary_or_offer` as sensitive intents, but they become watcher-handled intents in the new watcher policy.

- Modify `src/boss_agent_cli/commands/rag.py`  
  Add `agent watcher-run`, `agent watcher-status`, `agent watcher-pause`, and `agent watcher-resume` commands.

- Modify `demo/interview-simulator/vite.config.mjs`  
  Add local bridge endpoints for watcher status, run-once, pause, and resume.

- Modify `demo/interview-simulator/src/App.jsx`  
  Add a watcher console surface showing health, queue results, audit status, pause/resume controls, and last run output.

- Modify `demo/interview-simulator/src/styles.css`  
  Add compact operational console styling consistent with the existing simulator.

- Create `tests/test_watcher_config.py`  
  Unit coverage for config parsing and fixed replies.

- Create `tests/test_passive_watcher.py`  
  Unit/integration coverage for duplicate detection, action selection, dry-run, blocked cases, salary handoff, contact reply, and attachment action.

- Modify `tests/test_rag_reply_commands.py`  
  CLI coverage for watcher commands.

- Modify `tests/test_probe_script.py` or create `tests/test_interview_simulator_bridge.py` if bridge tests already cover Vite helpers  
  Cover watcher bridge command argument construction if there is an existing pattern; otherwise keep Vite bridge validation in `npm run build`.

---

### Task 1: Watcher Config And Fixed Replies

**Files:**
- Create: `src/boss_agent_cli/rag_reply/watcher_config.py`
- Test: `tests/test_watcher_config.py`

- [ ] **Step 1: Write failing tests for contact, salary, and interview config**

Create `tests/test_watcher_config.py`:

```python
import pytest

from boss_agent_cli.rag_reply.watcher_config import (
    WatcherConfig,
    WatcherConfigError,
    build_contact_reply,
    build_interview_window_reply,
    salary_handoff_reply,
)


def test_contact_reply_requires_unique_phone_and_wechat():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    assert build_contact_reply(config) == "我的手机号是 13800138000，微信号是 reggie-ai。"


def test_contact_reply_blocks_when_phone_missing():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    with pytest.raises(WatcherConfigError, match="boss_rag_contact_phone"):
        build_contact_reply(config)


def test_contact_reply_blocks_when_value_contains_multiple_candidates():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000,13900139000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    with pytest.raises(WatcherConfigError, match="must be unique"):
        build_contact_reply(config)


def test_salary_handoff_reply_is_fixed_agent_message():
    assert salary_handoff_reply() == (
        "我是候选人的求职助理 Agent，薪资相关问题需要候选人本人确认后回复。"
        "我已经记录下来，会提醒本人尽快处理。"
    )


def test_interview_window_reply_uses_configured_windows():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    assert build_interview_window_reply(config) == (
        "可以的，我这边通常工作日 20:00 后，周末全天方便面试。"
        "您可以发几个可选时间，我确认后会尽快回复。"
    )
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_watcher_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.watcher_config'`.

- [ ] **Step 3: Implement watcher config helpers**

Create `src/boss_agent_cli/rag_reply/watcher_config.py`:

```python
"""Configuration helpers for the passive Boss Agent watcher."""

from __future__ import annotations

from dataclasses import dataclass


class WatcherConfigError(ValueError):
    """Raised when watcher configuration is missing or unsafe."""


@dataclass(slots=True)
class WatcherConfig:
    enabled: bool
    dry_run: bool
    contact_phone: str
    contact_wechat: str
    interview_windows: str
    resume_attachment_path: str
    poll_seconds: int = 20
    max_failures_per_conversation: int = 3

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> "WatcherConfig":
        return cls(
            enabled=bool(values.get("boss_rag_watcher_enabled", False)),
            dry_run=bool(values.get("boss_rag_watcher_dry_run", True)),
            contact_phone=str(values.get("boss_rag_contact_phone") or "").strip(),
            contact_wechat=str(values.get("boss_rag_contact_wechat") or "").strip(),
            interview_windows=str(values.get("boss_rag_interview_windows") or "").strip(),
            resume_attachment_path=str(values.get("boss_rag_resume_attachment_path") or "").strip(),
            poll_seconds=max(5, int(values.get("boss_rag_watcher_poll_seconds") or 20)),
            max_failures_per_conversation=max(
                1,
                int(values.get("boss_rag_watcher_max_failures_per_conversation") or 3),
            ),
        )


def _require_unique(value: str, key: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise WatcherConfigError(f"{key} is required for automatic watcher replies.")
    separators = [",", "，", ";", "；", "/", "|"]
    if any(separator in normalized for separator in separators):
        raise WatcherConfigError(f"{key} must be unique for automatic watcher replies.")
    return normalized


def build_contact_reply(config: WatcherConfig) -> str:
    phone = _require_unique(config.contact_phone, "boss_rag_contact_phone")
    wechat = _require_unique(config.contact_wechat, "boss_rag_contact_wechat")
    return f"我的手机号是 {phone}，微信号是 {wechat}。"


def salary_handoff_reply() -> str:
    return (
        "我是候选人的求职助理 Agent，薪资相关问题需要候选人本人确认后回复。"
        "我已经记录下来，会提醒本人尽快处理。"
    )


def build_interview_window_reply(config: WatcherConfig) -> str:
    windows = _require_unique(config.interview_windows, "boss_rag_interview_windows")
    return f"可以的，我这边通常{windows}方便面试。您可以发几个可选时间，我确认后会尽快回复。"
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `pytest tests/test_watcher_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_watcher_config.py src/boss_agent_cli/rag_reply/watcher_config.py
git commit -m "feat: add passive watcher fixed reply config"
```

---

### Task 2: Watcher Action Policy And Dry-Run Delivery

**Files:**
- Create: `src/boss_agent_cli/rag_reply/watcher.py`
- Test: `tests/test_passive_watcher.py`

- [ ] **Step 1: Write failing tests for watcher action selection**

Create `tests/test_passive_watcher.py`:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.models import DraftRecord
from boss_agent_cli.rag_reply.watcher import WatcherAction, build_action_for_draft
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


def _config(tmp_path: Path) -> WatcherConfig:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path=str(resume),
    )


def _draft(intent: str, text: str = "草稿") -> DraftRecord:
    return DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text=text,
        intent=intent,
        risk_labels=[],
        evidence={"source": "test"},
        approval_required=True,
        send_allowed=False,
    )


def test_project_question_sends_draft_text(tmp_path):
    action = build_action_for_draft(_draft("project_question", "我是项目回答"), _config(tmp_path))

    assert action == WatcherAction(
        kind="send_text",
        message="我是项目回答",
        status_after_send="sent",
        send_attachment_resume=False,
        blocked_reason="",
    )


def test_resume_share_request_sends_text_and_attachment(tmp_path):
    action = build_action_for_draft(_draft("resume_share_request", "可以的，我发您附件简历。"), _config(tmp_path))

    assert action.kind == "send_text"
    assert action.send_attachment_resume is True
    assert action.resume_file.endswith("resume.pdf")


def test_contact_exchange_uses_fixed_contact_reply(tmp_path):
    action = build_action_for_draft(_draft("contact_exchange", ""), _config(tmp_path))

    assert action.message == "我的手机号是 13800138000，微信号是 reggie-ai。"
    assert action.kind == "send_text"


def test_salary_or_offer_sends_handoff_and_blocks_after_send(tmp_path):
    action = build_action_for_draft(_draft("salary_or_offer", ""), _config(tmp_path))

    assert "薪资相关问题需要候选人本人确认后回复" in action.message
    assert action.status_after_send == "blocked_manual_required"


def test_unknown_intent_blocks(tmp_path):
    action = build_action_for_draft(_draft("unsafe_or_unclear", ""), _config(tmp_path))

    assert action.kind == "block"
    assert action.blocked_reason == "intent_not_allowlisted"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_passive_watcher.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.watcher'`.

- [ ] **Step 3: Implement action policy**

Create `src/boss_agent_cli/rag_reply/watcher.py` with this initial content:

```python
"""Passive watcher orchestration for inbound Boss HR messages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from boss_agent_cli.rag_reply.models import DraftRecord
from boss_agent_cli.rag_reply.watcher_config import (
    WatcherConfig,
    WatcherConfigError,
    build_contact_reply,
    build_interview_window_reply,
    salary_handoff_reply,
)


WATCHER_STATUSES = {
    "queued",
    "processing",
    "sent",
    "blocked_manual_required",
    "skipped_duplicate",
    "runtime_unavailable",
    "target_ambiguous",
    "rag_failed",
    "attachment_failed",
    "send_failed",
    "paused",
}


@dataclass(slots=True)
class WatcherAction:
    kind: str
    message: str = ""
    status_after_send: str = "sent"
    send_attachment_resume: bool = False
    resume_file: str = ""
    blocked_reason: str = ""


def build_action_for_draft(draft: DraftRecord, config: WatcherConfig) -> WatcherAction:
    intent = draft.intent
    draft_text = (draft.draft_text or "").strip()
    if intent in {"project_question", "resume_question", "smalltalk", "resignation_status", "personal_status"}:
        if not draft_text:
            return WatcherAction(kind="block", status_after_send="rag_failed", blocked_reason="empty_draft")
        return WatcherAction(kind="send_text", message=draft_text)
    if intent == "resume_share_request":
        resume_file = _require_resume_file(config.resume_attachment_path)
        message = draft_text or "可以的，我这边通过 BOSS 直聘发送附件简历给您。"
        return WatcherAction(
            kind="send_text",
            message=message,
            send_attachment_resume=True,
            resume_file=resume_file,
        )
    if intent in {"interview_time", "availability_or_schedule"}:
        return WatcherAction(kind="send_text", message=build_interview_window_reply(config))
    if intent == "contact_exchange":
        return WatcherAction(kind="send_text", message=build_contact_reply(config))
    if intent == "salary_or_offer":
        return WatcherAction(
            kind="send_text",
            message=salary_handoff_reply(),
            status_after_send="blocked_manual_required",
        )
    return WatcherAction(kind="block", status_after_send="blocked_manual_required", blocked_reason="intent_not_allowlisted")


def _require_resume_file(value: str) -> str:
    path = Path(value).expanduser()
    if not value.strip() or not path.exists():
        raise WatcherConfigError("boss_rag_resume_attachment_path must point to an existing PDF file.")
    if path.suffix.lower() != ".pdf":
        raise WatcherConfigError("boss_rag_resume_attachment_path must point to a PDF file.")
    return str(path)
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_watcher_config.py tests/test_passive_watcher.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/watcher.py tests/test_passive_watcher.py
git commit -m "feat: map passive watcher intents to actions"
```

---

### Task 3: Single-Pass Watcher Service

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/watcher.py`
- Test: `tests/test_passive_watcher.py`

- [ ] **Step 1: Add failing tests for duplicate detection and dry-run run_once**

Append to `tests/test_passive_watcher.py`:

```python
from boss_agent_cli.rag_reply.models import AuditLogRecord, ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher import BossPassiveWatcher


class _FakeRagResult:
    ok = True
    answer = "RAG 回答"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "answered"
    send_allowed = False
    approval_required = True


class _FakeRagAdapter:
    def answer(self, *, rag_question: str, session_id: str, mode: str = "accurate"):
        return _FakeRagResult()


class _RecordingDelivery:
    def __init__(self):
        self.calls = []

    def send(self, *, security_id, message, send_attachment_resume=False, resume_file="", target=None):
        self.calls.append(
            {
                "security_id": security_id,
                "message": message,
                "send_attachment_resume": send_attachment_resume,
                "resume_file": resume_file,
                "target": target or {},
            }
        )
        return {
            "ok": True,
            "status": "sent",
            "message_sent": True,
            "resume_sent": bool(send_attachment_resume),
            "error_message": "",
            "results": ["sent"],
        }


def _store(tmp_path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return store


def _service(store):
    return BossRagReplyService(store=store, rag_adapter=_FakeRagAdapter())


def test_run_once_sends_contact_reply_and_writes_audit(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="test",
            state={"security_id": "sec_001", "recruiter_name": "张三", "company": "测试公司", "title": "AI 工程师"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="方便给个联系方式吗",
            direction="inbound",
        )
    )
    delivery = _RecordingDelivery()
    watcher = BossPassiveWatcher(store=store, service=_service(store), config=_config(tmp_path), delivery=delivery)

    result = watcher.run_once()

    assert result.processed == 1
    assert delivery.calls[0]["message"] == "我的手机号是 13800138000，微信号是 reggie-ai。"
    audit = store.list_audit_logs("conv_001")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["status"] == "sent"


def test_run_once_skips_already_processed_message(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="test", state={"security_id": "sec_001"}))
    store.save_message(MessageRecord(message_id="msg_001", conversation_id="conv_001", message_text="你好", direction="inbound"))
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="conv_001",
            payload={"message_id": "msg_001", "status": "sent"},
        )
    )
    delivery = _RecordingDelivery()
    watcher = BossPassiveWatcher(store=store, service=_service(store), config=_config(tmp_path), delivery=delivery)

    result = watcher.run_once()

    assert result.processed == 0
    assert result.skipped == 1
    assert delivery.calls == []
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_passive_watcher.py -v`

Expected: FAIL with `ImportError` for `BossPassiveWatcher`.

- [ ] **Step 3: Implement single-pass watcher orchestration**

Append to `src/boss_agent_cli/rag_reply/watcher.py`:

```python
from typing import Protocol

from boss_agent_cli.rag_reply.models import AuditLogRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore


class WatcherDelivery(Protocol):
    def send(
        self,
        *,
        security_id: str,
        message: str,
        send_attachment_resume: bool = False,
        resume_file: str = "",
        target: dict[str, str] | None = None,
    ) -> dict[str, object]:
        ...


@dataclass(slots=True)
class WatcherRunResult:
    processed: int
    skipped: int
    blocked: int
    tasks: list[dict[str, object]]


class BossPassiveWatcher:
    def __init__(
        self,
        *,
        store: RagReplyStore,
        service: BossRagReplyService,
        config: WatcherConfig,
        delivery: WatcherDelivery,
    ) -> None:
        self.store = store
        self.service = service
        self.config = config
        self.delivery = delivery

    def run_once(self) -> WatcherRunResult:
        processed = 0
        skipped = 0
        blocked = 0
        tasks: list[dict[str, object]] = []
        for message in self._candidate_messages():
            if self._already_processed(message.message_id):
                skipped += 1
                tasks.append({"message_id": message.message_id, "status": "skipped_duplicate"})
                continue
            task = self._process_message(message)
            tasks.append(task)
            if task["status"] == "sent":
                processed += 1
            elif task["status"] == "blocked_manual_required":
                blocked += 1
            else:
                processed += 1
        return WatcherRunResult(processed=processed, skipped=skipped, blocked=blocked, tasks=tasks)

    def _candidate_messages(self) -> list[MessageRecord]:
        return [
            message
            for message in self.store.list_messages()
            if message.direction == "inbound" and message.message_text.strip()
        ]

    def _already_processed(self, message_id: str) -> bool:
        for entry in self.store.list_audit_logs():
            if entry.event_type == "watcher_task" and entry.payload.get("message_id") == message_id:
                return True
        return False

    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        draft = self.service.create_draft_for_message(message.message_id)
        try:
            action = build_action_for_draft(draft, self.config)
        except WatcherConfigError as exc:
            return self._record_task(
                message=message,
                status="blocked_manual_required",
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message=str(exc),
            )
        if action.kind == "block":
            return self._record_task(
                message=message,
                status=action.status_after_send,
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message=action.blocked_reason,
            )
        security_id = self._resolve_security_id(message.conversation_id)
        if not security_id:
            return self._record_task(
                message=message,
                status="blocked_manual_required",
                intent=draft.intent,
                draft_id=draft.draft_id,
                error_message="missing_security_id",
            )
        target = self._target_payload(message.conversation_id)
        if self.config.dry_run:
            return self._record_task(
                message=message,
                status=action.status_after_send,
                intent=draft.intent,
                draft_id=draft.draft_id,
                dry_run=True,
                action=action,
                delivery={"ok": True, "status": "dry_run"},
            )
        delivery = self.delivery.send(
            security_id=security_id,
            message=action.message,
            send_attachment_resume=action.send_attachment_resume,
            resume_file=action.resume_file,
            target=target,
        )
        status = action.status_after_send if delivery.get("ok") else "send_failed"
        return self._record_task(
            message=message,
            status=status,
            intent=draft.intent,
            draft_id=draft.draft_id,
            action=action,
            delivery=delivery,
        )

    def _record_task(
        self,
        *,
        message: MessageRecord,
        status: str,
        intent: str,
        draft_id: str,
        error_message: str = "",
        dry_run: bool = False,
        action: WatcherAction | None = None,
        delivery: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload = {
            "message_id": message.message_id,
            "conversation_id": message.conversation_id,
            "draft_id": draft_id,
            "intent": intent,
            "status": status,
            "error_message": error_message,
            "dry_run": dry_run,
            "action": _action_payload(action),
            "delivery": delivery or {},
        }
        self.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id=message.conversation_id,
                payload=payload,
            )
        )
        return payload

    def _resolve_security_id(self, conversation_id: str) -> str:
        conversation = self.store.get_conversation(conversation_id)
        if conversation and isinstance(conversation.state, dict):
            return str(conversation.state.get("security_id") or "").strip()
        return ""

    def _target_payload(self, conversation_id: str) -> dict[str, str]:
        conversation = self.store.get_conversation(conversation_id)
        state = conversation.state if conversation and isinstance(conversation.state, dict) else {}
        return {
            "recruiter_name": str(state.get("recruiter_name") or ""),
            "company": str(state.get("company") or ""),
            "title": str(state.get("title") or ""),
        }


def _action_payload(action: WatcherAction | None) -> dict[str, object]:
    if action is None:
        return {}
    return {
        "kind": action.kind,
        "message": action.message,
        "status_after_send": action.status_after_send,
        "send_attachment_resume": action.send_attachment_resume,
        "resume_file": action.resume_file,
        "blocked_reason": action.blocked_reason,
    }
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_passive_watcher.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/watcher.py tests/test_passive_watcher.py
git commit -m "feat: add passive watcher single pass"
```

---

### Task 4: CLI Watcher Commands

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_rag_reply_commands.py` using the existing CLI runner pattern in that file. If the file already has helper fixtures, reuse them and keep the assertions below:

```python
def test_agent_watcher_status_returns_recent_tasks(cli_runner, tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    result = cli_runner.invoke(
        ["--json", "--data-dir", str(data_dir), "agent", "watcher-status"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["running"] is False
    assert payload["data"]["tasks"] == []


def test_agent_watcher_run_disabled_by_default(cli_runner, tmp_path):
    data_dir = tmp_path / "data"
    result = cli_runner.invoke(
        ["--json", "--data-dir", str(data_dir), "agent", "watcher-run", "--once"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["status"] == "paused"
    assert payload["data"]["reason"] == "watcher_disabled"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_rag_reply_commands.py -k watcher -v`

Expected: FAIL because the commands do not exist.

- [ ] **Step 3: Add delivery wrapper and watcher builders in `commands/rag.py`**

Add imports near the existing watcher-related imports:

```python
from boss_agent_cli.rag_reply.watcher import BossPassiveWatcher, WatcherRunResult
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig
```

Add helper classes/functions above the click command definitions:

```python
class _CliWatcherDelivery:
    def __init__(self, ctx: click.Context) -> None:
        self.ctx = ctx

    def send(
        self,
        *,
        security_id: str,
        message: str,
        send_attachment_resume: bool = False,
        resume_file: str = "",
        target: dict[str, str] | None = None,
    ) -> dict[str, object]:
        target = target or {}
        result = execute_chat_reply(
            self.ctx,
            security_id=security_id,
            message=message,
            send_resume=False,
            send_attachment_resume=send_attachment_resume,
            resume_file_path=resume_file or None,
            target_recruiter_name=str(target.get("recruiter_name") or ""),
            target_company=str(target.get("company") or ""),
            target_title=str(target.get("title") or ""),
        )
        ok = result.message_sent or (send_attachment_resume and result.resume_sent)
        return {
            "ok": ok,
            "status": "sent" if ok else "send_failed",
            "message_sent": result.message_sent,
            "resume_sent": result.resume_sent,
            "error_message": result.error_message,
            "results": result.results,
            "resume_file": result.resume_file_path,
        }


def _build_watcher_config(ctx: click.Context) -> WatcherConfig:
    config = ctx.obj.get("config", {}) if ctx and ctx.obj else {}
    return WatcherConfig.from_mapping(config)


def _build_passive_watcher(ctx: click.Context) -> BossPassiveWatcher:
    service = _build_service(ctx)
    return BossPassiveWatcher(
        store=service.store,
        service=service,
        config=_build_watcher_config(ctx),
        delivery=_CliWatcherDelivery(ctx),
    )


def _watcher_result_payload(result: WatcherRunResult) -> dict[str, object]:
    return {
        "processed": result.processed,
        "skipped": result.skipped,
        "blocked": result.blocked,
        "tasks": result.tasks,
    }
```

- [ ] **Step 4: Add watcher commands**

Add these commands near `rag_audit_cmd`:

```python
@rag_group.command("watcher-run")
@click.option("--once", is_flag=True, default=False)
@click.pass_context
def rag_watcher_run_cmd(ctx: click.Context, once: bool) -> None:
    config = _build_watcher_config(ctx)
    if not config.enabled:
        handle_output(
            ctx,
            _workflow_command(ctx, "watcher-run"),
            {"status": "paused", "reason": "watcher_disabled", "tasks": []},
            render=lambda data: click.echo("Watcher is disabled.", err=True),
        )
        return
    watcher = _build_passive_watcher(ctx)
    result = watcher.run_once()
    handle_output(
        ctx,
        _workflow_command(ctx, "watcher-run"),
        {"status": "completed", **_watcher_result_payload(result)},
        render=lambda data: click.echo(f"Watcher processed {data['processed']} task(s).", err=True),
    )


@rag_group.command("watcher-status")
@click.pass_context
def rag_watcher_status_cmd(ctx: click.Context) -> None:
    store = _resolve_store(ctx)
    config = _build_watcher_config(ctx)
    tasks = [
        {
            "log_id": entry.log_id,
            "conversation_id": entry.entity_id,
            **entry.payload,
            "created_at": entry.created_at,
        }
        for entry in store.list_audit_logs()
        if entry.event_type == "watcher_task"
    ][-20:]
    handle_output(
        ctx,
        _workflow_command(ctx, "watcher-status"),
        {
            "running": config.enabled,
            "dry_run": config.dry_run,
            "tasks": tasks,
        },
        render=lambda data: click.echo(f"Watcher has {len(data['tasks'])} recent task(s).", err=True),
    )


@rag_group.command("watcher-pause")
@click.option("--conversation-id", default="")
@click.pass_context
def rag_watcher_pause_cmd(ctx: click.Context, conversation_id: str) -> None:
    store = _resolve_store(ctx)
    entity_id = conversation_id or "global"
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_control",
            entity_type="conversation" if conversation_id else "watcher",
            entity_id=entity_id,
            payload={"action": "pause", "conversation_id": conversation_id},
        )
    )
    handle_output(ctx, _workflow_command(ctx, "watcher-pause"), {"paused": True, "conversation_id": conversation_id})


@rag_group.command("watcher-resume")
@click.option("--conversation-id", default="")
@click.pass_context
def rag_watcher_resume_cmd(ctx: click.Context, conversation_id: str) -> None:
    store = _resolve_store(ctx)
    entity_id = conversation_id or "global"
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_control",
            entity_type="conversation" if conversation_id else "watcher",
            entity_id=entity_id,
            payload={"action": "resume", "conversation_id": conversation_id},
        )
    )
    handle_output(ctx, _workflow_command(ctx, "watcher-resume"), {"paused": False, "conversation_id": conversation_id})
```

- [ ] **Step 5: Run focused CLI tests**

Run: `pytest tests/test_rag_reply_commands.py -k watcher -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/commands/rag.py tests/test_rag_reply_commands.py
git commit -m "feat: expose passive watcher CLI commands"
```

---

### Task 5: Vite Bridge Endpoints

**Files:**
- Modify: `demo/interview-simulator/vite.config.mjs`

- [ ] **Step 1: Add watcher route detection**

In `createRagBridgePlugin().handler`, add route booleans near the existing `isAgentHealth` declarations:

```js
    const isWatcherStatus = req.url === "/api/agent/watcher/status";
    const isWatcherRun = req.url === "/api/agent/watcher/run";
    const isWatcherControl = req.url === "/api/agent/watcher/control";
```

- [ ] **Step 2: Add status endpoint**

Add before the `isAgentSend` handler:

```js
    if (req.method === "GET" && isWatcherStatus) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = runBossJsonCommand(bridgeConfig, ["agent", "watcher-status"]);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "读取 watcher 状态失败。",
          data: { running: false, dry_run: true, tasks: [] },
        }));
      }
      return true;
    }
```

- [ ] **Step 3: Add run-once endpoint**

Add after the status endpoint:

```js
    if (req.method === "POST" && isWatcherRun) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = runBossJsonCommand(bridgeConfig, ["agent", "watcher-run", "--once"]);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        const payload = error?.commandPayload;
        res.statusCode = payload?.error?.recoverable ? 502 : 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "运行 watcher 失败。",
        }));
      }
      return true;
    }
```

- [ ] **Step 4: Add pause/resume endpoint**

Add after the run endpoint:

```js
    if (req.method === "POST" && isWatcherControl) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const parsed = rawBody ? JSON.parse(rawBody) : {};
        const action = String(parsed.action || "").trim();
        const conversationId = String(parsed.conversation_id || "").trim();
        if (!["pause", "resume"].includes(action)) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "action 必须是 pause 或 resume。" }));
          return true;
        }
        const args = ["agent", action === "pause" ? "watcher-pause" : "watcher-resume"];
        if (conversationId) args.push("--conversation-id", conversationId);
        const payload = runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "更新 watcher 控制状态失败。",
        }));
      }
      return true;
    }
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd demo/interview-simulator
npm run build
```

Expected: PASS with Vite build output.

- [ ] **Step 6: Commit**

```bash
git add demo/interview-simulator/vite.config.mjs
git commit -m "feat: bridge watcher controls to simulator"
```

---

### Task 6: Frontend Watcher Console

**Files:**
- Modify: `demo/interview-simulator/src/App.jsx`
- Modify: `demo/interview-simulator/src/styles.css`

- [ ] **Step 1: Add watcher state and API helpers**

In `demo/interview-simulator/src/App.jsx`, add near existing state declarations:

```jsx
  const [watcherState, setWatcherState] = useState({
    running: false,
    dry_run: true,
    tasks: [],
    errorMessage: "",
  });
  const [isWatcherBusy, setIsWatcherBusy] = useState(false);
```

Add helper functions inside the component:

```jsx
  async function refreshWatcherStatus() {
    try {
      const response = await fetch("/api/agent/watcher/status");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "读取 watcher 状态失败。");
      }
      setWatcherState({
        running: Boolean(payload.data?.running),
        dry_run: Boolean(payload.data?.dry_run),
        tasks: Array.isArray(payload.data?.tasks) ? payload.data.tasks : [],
        errorMessage: "",
      });
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage: error instanceof Error ? error.message : "读取 watcher 状态失败。",
      }));
    }
  }

  async function runWatcherOnce() {
    setIsWatcherBusy(true);
    try {
      const response = await fetch("/api/agent/watcher/run", { method: "POST" });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "运行 watcher 失败。");
      }
      await refreshWatcherStatus();
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage: error instanceof Error ? error.message : "运行 watcher 失败。",
      }));
    } finally {
      setIsWatcherBusy(false);
    }
  }

  async function controlWatcher(action, conversationId = "") {
    setIsWatcherBusy(true);
    try {
      const response = await fetch("/api/agent/watcher/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, conversation_id: conversationId }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "更新 watcher 控制状态失败。");
      }
      await refreshWatcherStatus();
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage: error instanceof Error ? error.message : "更新 watcher 控制状态失败。",
      }));
    } finally {
      setIsWatcherBusy(false);
    }
  }
```

- [ ] **Step 2: Refresh watcher status when app loads**

Add to the existing mount effect, or create a new effect:

```jsx
  useEffect(() => {
    void refreshWatcherStatus();
  }, []);
```

- [ ] **Step 3: Add watcher console markup**

Add this section near the existing operational/status panel:

```jsx
          <section className="watcher-console" aria-label="Boss 自动代理 watcher">
            <div className="watcher-console__header">
              <div>
                <h2>Boss 自动代理</h2>
                <p>{watcherState.running ? "watcher 已启用" : "watcher 当前暂停或未启用"}</p>
              </div>
              <div className="watcher-console__actions">
                <button type="button" onClick={runWatcherOnce} disabled={isWatcherBusy}>
                  处理一轮
                </button>
                <button type="button" onClick={() => controlWatcher("pause")} disabled={isWatcherBusy}>
                  暂停
                </button>
                <button type="button" onClick={() => controlWatcher("resume")} disabled={isWatcherBusy}>
                  恢复
                </button>
              </div>
            </div>

            <div className="watcher-console__meta">
              <span>{watcherState.dry_run ? "dry-run" : "live-send"}</span>
              <span>{watcherState.tasks.length} 条最近任务</span>
            </div>

            {watcherState.errorMessage ? (
              <p className="watcher-console__error">{watcherState.errorMessage}</p>
            ) : null}

            <div className="watcher-task-list">
              {watcherState.tasks.length ? (
                watcherState.tasks.slice().reverse().map((task) => (
                  <article className="watcher-task" key={task.log_id || `${task.conversation_id}-${task.message_id}`}>
                    <div className="watcher-task__topline">
                      <strong>{task.intent || "unknown"}</strong>
                      <span>{task.status || "unknown"}</span>
                    </div>
                    <p>{task.error_message || task.action?.message || "无错误信息"}</p>
                    <div className="watcher-task__footer">
                      <span>{task.conversation_id || ""}</span>
                      <button
                        type="button"
                        onClick={() => controlWatcher("pause", task.conversation_id || "")}
                        disabled={isWatcherBusy || !task.conversation_id}
                      >
                        禁用会话
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <p className="watcher-console__empty">还没有 watcher 任务。</p>
              )}
            </div>
          </section>
```

- [ ] **Step 4: Add CSS**

Append to `demo/interview-simulator/src/styles.css`:

```css
.watcher-console {
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 8px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.76);
}

.watcher-console__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.watcher-console__header h2 {
  margin: 0;
  font-size: 16px;
}

.watcher-console__header p,
.watcher-console__empty,
.watcher-task p {
  margin: 6px 0 0;
  color: rgba(226, 232, 240, 0.76);
  font-size: 13px;
}

.watcher-console__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.watcher-console__actions button,
.watcher-task__footer button {
  min-height: 32px;
  border: 1px solid rgba(148, 163, 184, 0.32);
  border-radius: 6px;
  padding: 0 10px;
  background: rgba(30, 41, 59, 0.9);
  color: #f8fafc;
  cursor: pointer;
}

.watcher-console__actions button:disabled,
.watcher-task__footer button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.watcher-console__meta,
.watcher-task__footer,
.watcher-task__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.watcher-console__meta {
  margin-top: 12px;
  color: rgba(148, 163, 184, 0.9);
  font-size: 12px;
}

.watcher-console__error {
  margin: 12px 0 0;
  color: #fecaca;
  font-size: 13px;
}

.watcher-task-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.watcher-task {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 8px;
  padding: 12px;
  background: rgba(2, 6, 23, 0.42);
}

.watcher-task__topline strong {
  font-size: 13px;
}

.watcher-task__topline span {
  color: #bfdbfe;
  font-size: 12px;
}

.watcher-task__footer {
  margin-top: 10px;
  color: rgba(148, 163, 184, 0.86);
  font-size: 12px;
}
```

- [ ] **Step 5: Build frontend**

Run:

```bash
cd demo/interview-simulator
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add demo/interview-simulator/src/App.jsx demo/interview-simulator/src/styles.css
git commit -m "feat: add passive watcher console"
```

---

### Task 7: Focused Regression And Local Smoke

**Files:**
- Modify only if failures reveal a direct issue in files touched by Tasks 1-6.

- [ ] **Step 1: Run Python focused tests**

Run:

```bash
pytest \
  tests/test_watcher_config.py \
  tests/test_passive_watcher.py \
  tests/test_rag_reply_commands.py \
  tests/test_api_client_methods.py \
  tests/test_stack_readiness.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd demo/interview-simulator
npm run build
```

Expected: PASS.

- [ ] **Step 3: Run CLI smoke in dry-run mode**

Create a temporary data dir and run:

```bash
tmpdir="$(mktemp -d)"
python -c "from boss_agent_cli.main import cli; cli.main(args=['--json','--data-dir', '$tmpdir', 'agent', 'watcher-status'], standalone_mode=False)"
python -c "from boss_agent_cli.main import cli; cli.main(args=['--json','--data-dir', '$tmpdir', 'agent', 'watcher-run', '--once'], standalone_mode=False)"
```

Expected:

- `watcher-status` returns JSON with `ok=true`.
- `watcher-run --once` returns JSON with `status=paused` while `boss_rag_watcher_enabled` is false.

- [ ] **Step 4: Start simulator for manual local smoke**

Run:

```bash
cd demo/interview-simulator
npm run dev -- --host 127.0.0.1
```

Expected:

- Vite prints a local URL.
- The page loads.
- The watcher console renders.
- “处理一轮” returns either `watcher_disabled` or recent dry-run tasks.
- Pause/resume buttons return success responses.

- [ ] **Step 5: Record live Boss E2E as not run unless preflight is ready**

Run:

```bash
curl -s http://127.0.0.1:5175/api/agent/health
```

Expected for live E2E:

- Only claim live Boss E2E if `browserChannel.preflightStatus` is `ready`.
- If status is `chat_login_redirect`, `transport_unavailable`, or any non-ready value, report live Boss E2E as not run and include that exact status.

- [ ] **Step 6: Final commit for test-only fixes**

If Step 1-5 required direct fixes, commit them:

```bash
git add <specific-fixed-files>
git commit -m "test: stabilize passive watcher verification"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Background watcher: covered by Tasks 3 and 4.
- Frontend console: covered by Tasks 5 and 6.
- Conservative automatic strategy: covered by Tasks 1, 2, and 3.
- Attachment PDF path: covered by Task 2 action policy and Task 7 regression list.
- Contact phone + WeChat reply: covered by Tasks 1 and 2.
- Salary Agent handoff reply: covered by Tasks 1 and 2.
- Audit log traceability: covered by Tasks 3 and 4.
- Mock versus live proof separation: covered by Task 7.

Type consistency:

- `WatcherConfig`, `WatcherAction`, `WatcherRunResult`, and `BossPassiveWatcher` are introduced before later tasks reference them.
- CLI commands use existing `rag_group` under the user-facing `agent` alias.
- Frontend bridge calls only the CLI commands introduced in Task 4.

Execution notes:

- `docs/superpowers/` is ignored by `.gitignore`; the plan file itself should be added with `git add -f docs/superpowers/plans/2026-06-16-boss-agent-passive-watcher.md` if it needs to be committed.
- During implementation, do not use `git add .`; stage only the files listed in each task.
