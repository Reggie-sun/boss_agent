# Boss Guarded Tool Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有 Boss inbound watcher 从直接函数调用升级为 LangGraph 调用 guarded tools 的全自动 agent 流程，同时保留发送、附件简历、CDP/Bridge 和 audit 的硬安全边界。

**Architecture:** 外层仍由 `BossPassiveWatcher` 负责循环、去重、pause/resume 和 live-sync 前置门禁；每条 inbound message 进入 `tool_graph.py`，由 LangGraph 节点调用 `agent_tools.py` 中的 guarded tools。LLM/agent 可以通过工具接口表达“同步、起草、决策、解析目标、发送、记录审计”，但真实发送工具内部必须再次执行 deterministic guard，不能绕过 `boss_rag_send_enabled`、`dry_run`、`security_id`、附件简历路径和 fail-closed 错误语义。

**Tech Stack:** Python 3.10+, pytest, Click CLI, SQLite `RagReplyStore`, existing `BossRagReplyService`, existing `_CliWatcherDelivery` / `_CliWatcherMessageSyncer`, optional `langgraph>=1.0.0`, LangChain message memory helpers.

---

## Scope

这份计划只覆盖 Boss inbound reply / watcher / RAG reply / 自动动作的 tool-agent 化。它不重做 search / auto-greet 筛选，也不放宽真实平台写入边界。

保留的硬规则：

- `BossPassiveWatcher` 仍是周期执行入口，`agent watcher-run --loop` 和前端 watcher console 不变。
- `send_boss_reply_guarded` 和 `send_attachment_resume_guarded` 是唯一真实发送工具，内部必须自行阻断未授权 live send。
- `resume_share_request` / `send_attachment_resume` 只能走附件简历上传或官方确认路径，不能退化成普通聊天文本或在线简历 fallback。
- `AUTH_EXPIRED`、`TOKEN_REFRESH_FAILED`、`ACCOUNT_RISK`、CDP/Bridge 不可用、缺少 `security_id`、空草稿、sync 禁用时必须 fail closed，并写入结构化 audit。
- LangGraph 可以不存在；测试和基础运行必须走顺序 fallback。

## File Structure

- Create `src/boss_agent_cli/rag_reply/agent_tools.py`  
  定义 guarded tool 数据结构和 `BossAgentToolbox`。所有 tool 都返回统一 `ToolResult`，不直接抛出可恢复业务错误。

- Create `src/boss_agent_cli/rag_reply/tool_graph.py`  
  定义 per-message tool graph：`create_rag_draft -> decide_auto_action -> resolve_boss_target -> send_boss_reply -> record_watcher_audit`。可选使用 LangGraph，缺依赖时顺序执行。

- Modify `src/boss_agent_cli/rag_reply/watcher.py`  
  保留 live sync、去重、pause/resume；每条消息改为调用 `run_tool_reply_graph`，不再直接调用 `run_auto_reply_graph`。

- Modify `src/boss_agent_cli/commands/rag.py`  
  `_build_passive_watcher` 继续注入现有 CLI syncer 和 delivery；无需新增真实平台入口。若增加 helper，只服务于 tool context 构建。

- Create `tests/test_rag_reply_agent_tools.py`  
  覆盖 guarded tools 的 dry-run、send-disabled、missing-security-id、附件简历、sync read-disabled、structured error metadata。

- Create `tests/test_rag_reply_tool_graph.py`  
  覆盖 tool graph 的节点顺序、LangGraph fallback、blocked path、audit payload。

- Modify `tests/test_passive_watcher.py`  
  验证 watcher 使用 tool graph 后仍只处理 latest inbound、仍去重、仍 pause/resume、仍 fail closed。

- Modify `tests/test_rag_reply_commands.py`  
  验证 CLI watcher 输出保留 tool-agent task metadata，并且 read-disabled 不创建 Boss adapter。

- Modify `docs/boss-agent-current-stage.md`  
  更新当前架构描述：全自动是 guarded tools agent，不是裸 LLM tool-calling。

---

### Task 1: Add Guarded Tool Primitives

**Files:**
- Create: `src/boss_agent_cli/rag_reply/agent_tools.py`
- Create: `tests/test_rag_reply_agent_tools.py`

- [ ] **Step 1: Write the failing agent tool tests**

Create `tests/test_rag_reply_agent_tools.py` with this content:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.models import ConversationRecord, DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


class _RagResult:
    ok = True
    answer = "您好，我主要负责企业级 RAG 的检索链路和回答编排。"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "draft_created"
    send_allowed = False
    approval_required = True


class _RagAdapter:
    def answer(self, **kwargs):
        return _RagResult()


class _Delivery:
    def __init__(self):
        self.calls = []

    def send(
        self,
        *,
        security_id,
        message,
        send_attachment_resume=False,
        resume_file="",
        target=None,
    ):
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
        }


class _Syncer:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def sync_messages(self, *, conversation_id=None):
        self.calls += 1
        return self.result


def _store(tmp_path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return store


def _config(tmp_path, *, dry_run=False, send_enabled=True):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return WatcherConfig(
        enabled=True,
        dry_run=dry_run,
        live_sync=True,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        resume_attachment_path=str(resume),
        send_enabled=send_enabled,
        require_send_enabled=True,
    )


def _toolbox(tmp_path, *, dry_run=False, send_enabled=True, sync_result=None):
    store = _store(tmp_path)
    service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())
    delivery = _Delivery()
    context = BossAgentToolContext(
        store=store,
        service=service,
        config=_config(tmp_path, dry_run=dry_run, send_enabled=send_enabled),
        delivery=delivery,
        message_syncer=_Syncer(sync_result or {"ok": True, "count": 0}),
    )
    return BossAgentToolbox(context), store, delivery


def test_sync_boss_messages_records_read_disabled_recovery(tmp_path):
    toolbox, store, delivery = _toolbox(
        tmp_path,
        sync_result={
            "ok": False,
            "status": "read_disabled",
            "error_code": "RAG_READ_NOT_ENABLED",
            "error_message": "Boss message reading is disabled by default.",
            "recoverable": True,
            "recovery_action": "Set boss_rag_allow_message_read=true in config.json and retry.",
        },
    )

    result = toolbox.sync_boss_messages()

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "RAG_READ_NOT_ENABLED"
    assert result.recoverable is True
    assert result.recovery_action == "Set boss_rag_allow_message_read=true in config.json and retry."
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_create_rag_draft_tool_uses_existing_service(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={"security_id": "sec_001"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
        )
    )

    result = toolbox.create_rag_draft(message_id="msg_001")

    assert result.ok is True
    assert result.status == "draft_created"
    assert result.data["draft_id"]
    assert result.data["intent"] == "project_question"
    assert store.get_draft(str(result.data["draft_id"])) is not None
    assert delivery.calls == []


def test_send_boss_reply_guarded_blocks_when_send_disabled(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=False)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，我主要负责企业级 RAG。",
            "send_attachment_resume": False,
            "resume_file": "",
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "SEND_DISABLED"
    assert result.error_message == "boss_rag_send_enabled_disabled"
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_send_boss_reply_guarded_dry_run_does_not_call_delivery(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，我主要负责企业级 RAG。",
            "send_attachment_resume": False,
            "resume_file": "",
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert result.data["delivery"] == {"ok": True, "status": "dry_run"}
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_send_attachment_resume_guarded_passes_attachment_flags(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    resume_file = Path(toolbox.context.config.resume_attachment_path)

    result = toolbox.send_attachment_resume_guarded(
        message="可以的，我这边通过 BOSS 直聘发送附件简历给您。",
        security_id="sec_001",
        resume_file=str(resume_file),
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "resume_file": str(resume_file),
            "target": {"company": "测试公司"},
        }
    ]
    assert store.list_drafts() == []
```

- [ ] **Step 2: Run the failing agent tool tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_agent_tools.py -q
```

Expected:

```text
ERROR tests/test_rag_reply_agent_tools.py - ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.agent_tools'
```

- [ ] **Step 3: Create `agent_tools.py`**

Create `src/boss_agent_cli/rag_reply/agent_tools.py` with this content:

```python
"""Guarded tools for the Boss inbound reply agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from boss_agent_cli.display import error_contract_for_code
from boss_agent_cli.rag_reply.auto_actions import AutoReplyAction, build_action_for_draft
from boss_agent_cli.rag_reply.models import AuditLogRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig, WatcherConfigError


class AgentToolDelivery(Protocol):
    def send(
        self,
        *,
        security_id: str,
        message: str,
        send_attachment_resume: bool = False,
        resume_file: str = "",
        target: dict[str, str] | None = None,
    ) -> dict[str, object]:
        raise NotImplementedError


class AgentToolMessageSyncer(Protocol):
    def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
        raise NotImplementedError


@dataclass(slots=True)
class ToolResult:
    ok: bool
    status: str
    data: dict[str, object] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    recoverable: bool = False
    recovery_action: str = ""
    hints: dict[str, object] = field(default_factory=dict)

    def as_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "status": self.status,
            "data": self.data,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "recoverable": self.recoverable,
            "recovery_action": self.recovery_action,
            "hints": self.hints,
        }


@dataclass(slots=True)
class BossAgentToolContext:
    store: RagReplyStore
    service: BossRagReplyService
    config: WatcherConfig
    delivery: AgentToolDelivery
    message_syncer: AgentToolMessageSyncer | None = None


class BossAgentToolbox:
    """Tools exposed to the Boss inbound reply graph.

    Every live-write tool enforces its own guard so a graph or LLM cannot
    bypass watcher configuration by selecting a different edge.
    """

    def __init__(self, context: BossAgentToolContext) -> None:
        self.context = context

    def sync_boss_messages(self, *, conversation_id: str | None = None) -> ToolResult:
        syncer = self.context.message_syncer
        if syncer is None:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_message="live_sync_unavailable",
            )
        try:
            result = syncer.sync_messages(conversation_id=conversation_id) or {}
        except Exception as exc:
            metadata = _error_metadata(exc)
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                data={"sync": {"error_message": metadata["error_message"]}},
                error_code=metadata["error_code"],
                error_message=metadata["error_message"],
                recoverable=metadata["recoverable"],
                recovery_action=metadata["recovery_action"],
                hints=metadata["hints"],
            )
        if result.get("ok") is False:
            metadata = _error_metadata(result)
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                data={"sync": dict(result)},
                error_code=metadata["error_code"],
                error_message=metadata["error_message"],
                recoverable=metadata["recoverable"],
                recovery_action=metadata["recovery_action"],
                hints=metadata["hints"],
            )
        return ToolResult(ok=True, status="synced", data={"sync": dict(result)})

    def list_unhandled_inbound(self) -> ToolResult:
        latest_by_conversation: dict[str, object] = {}
        processed_message_ids = self._processed_message_ids()
        for message in self.context.store.list_messages():
            if message.direction != "inbound" or not message.message_text.strip():
                continue
            if message.message_id in processed_message_ids:
                continue
            latest_by_conversation[message.conversation_id] = message
        messages = list(latest_by_conversation.values())
        return ToolResult(
            ok=True,
            status="listed",
            data={
                "messages": messages,
                "message_ids": [message.message_id for message in messages],
            },
        )

    def create_rag_draft(self, *, message_id: str) -> ToolResult:
        draft = self.context.service.create_draft_for_message(message_id)
        return ToolResult(
            ok=True,
            status=draft.audit_status,
            data={
                "draft": draft,
                "draft_id": draft.draft_id,
                "intent": draft.intent,
                "draft_text": draft.draft_text,
            },
        )

    def decide_auto_action(self, *, draft_id: str) -> ToolResult:
        draft = self.context.store.get_draft(draft_id)
        if draft is None:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_message=f"unknown_draft:{draft_id}",
            )
        try:
            action = build_action_for_draft(draft, self.context.config)
        except WatcherConfigError as exc:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_message=str(exc),
            )
        payload = _action_payload(action)
        if action.kind == "block":
            return ToolResult(
                ok=False,
                status=action.status_after_send,
                data={"action": payload},
                error_message=action.blocked_reason,
            )
        return ToolResult(ok=True, status="action_ready", data={"action": payload})

    def resolve_boss_target(self, *, conversation_id: str) -> ToolResult:
        conversation = self.context.store.get_conversation(conversation_id)
        state = (
            conversation.state
            if conversation is not None and isinstance(conversation.state, dict)
            else {}
        )
        security_id = str(state.get("security_id") or "").strip()
        if not security_id:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_message="missing_security_id",
            )
        recruiter = None
        if conversation is not None and conversation.recruiter_id:
            recruiter = self.context.store.get_recruiter(str(conversation.recruiter_id))
        target = {
            "recruiter_name": str(
                state.get("recruiter_name")
                or (recruiter.display_name if recruiter else "")
                or ""
            ),
            "company": str(state.get("company") or ""),
            "title": str(state.get("title") or ""),
            "security_id": security_id,
            "gid": str(state.get("gid") or ""),
            "friend_id": str(state.get("friend_id") or ""),
            "uid": str(state.get("uid") or ""),
            "encrypt_boss_id": str(state.get("encrypt_boss_id") or ""),
            "recruiter_id": str(
                state.get("recruiter_id")
                or (conversation.recruiter_id if conversation else "")
                or ""
            ),
        }
        return ToolResult(
            ok=True,
            status="target_resolved",
            data={"security_id": security_id, "target": target},
        )

    def send_boss_reply_guarded(
        self,
        *,
        action: dict[str, object],
        security_id: str,
        target: dict[str, str],
    ) -> ToolResult:
        if not self.context.config.dry_run and not self.context.config.send_enabled:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_code="SEND_DISABLED",
                error_message="boss_rag_send_enabled_disabled",
                recoverable=True,
                recovery_action="先 dry-run 复核，确认后显式开启发送配置再重试",
            )
        message = str(action.get("message") or "").strip()
        if not message:
            return ToolResult(
                ok=False,
                status="rag_failed",
                error_message="empty_message",
            )
        if not security_id.strip():
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_message="missing_security_id",
            )
        if bool(action.get("send_attachment_resume")):
            return self.send_attachment_resume_guarded(
                message=message,
                security_id=security_id,
                resume_file=str(action.get("resume_file") or ""),
                target=target,
                status_after_send=str(action.get("status_after_send") or "sent"),
            )
        status_after_send = str(action.get("status_after_send") or "sent")
        if self.context.config.dry_run:
            return ToolResult(
                ok=True,
                status=status_after_send,
                data={"delivery": {"ok": True, "status": "dry_run"}},
            )
        delivery = self.context.delivery.send(
            security_id=security_id,
            message=message,
            send_attachment_resume=False,
            resume_file="",
            target=target,
        )
        ok = bool(delivery.get("ok"))
        return ToolResult(
            ok=ok,
            status=status_after_send if ok else "send_failed",
            data={"delivery": dict(delivery)},
            error_message="" if ok else str(delivery.get("error_message") or "send_failed"),
        )

    def send_attachment_resume_guarded(
        self,
        *,
        message: str,
        security_id: str,
        resume_file: str,
        target: dict[str, str],
        status_after_send: str = "sent",
    ) -> ToolResult:
        if not self.context.config.dry_run and not self.context.config.send_enabled:
            return ToolResult(
                ok=False,
                status="blocked_manual_required",
                error_code="SEND_DISABLED",
                error_message="boss_rag_send_enabled_disabled",
                recoverable=True,
                recovery_action="先 dry-run 复核，确认后显式开启发送配置再重试",
            )
        if not resume_file.strip():
            return ToolResult(
                ok=False,
                status="attachment_failed",
                error_message="missing_resume_file",
            )
        if self.context.config.dry_run:
            return ToolResult(
                ok=True,
                status=status_after_send,
                data={
                    "delivery": {
                        "ok": True,
                        "status": "dry_run",
                        "send_attachment_resume": True,
                        "resume_file": resume_file,
                    }
                },
            )
        delivery = self.context.delivery.send(
            security_id=security_id,
            message=message,
            send_attachment_resume=True,
            resume_file=resume_file,
            target=target,
        )
        ok = bool(delivery.get("ok"))
        return ToolResult(
            ok=ok,
            status=status_after_send if ok else "attachment_failed",
            data={"delivery": dict(delivery)},
            error_message="" if ok else str(delivery.get("error_message") or "attachment_failed"),
        )

    def record_watcher_audit(
        self,
        *,
        message_id: str,
        conversation_id: str,
        draft_id: str,
        intent: str,
        status: str,
        error_message: str = "",
        dry_run: bool = False,
        action: dict[str, object] | None = None,
        delivery: dict[str, object] | None = None,
        tool_steps: list[dict[str, object]] | None = None,
    ) -> ToolResult:
        payload = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "draft_id": draft_id,
            "intent": intent,
            "status": status,
            "error_message": error_message,
            "dry_run": dry_run,
            "action": action or {},
            "delivery": delivery or {},
            "tool_steps": tool_steps or [],
        }
        self.context.store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id=conversation_id,
                payload=payload,
            )
        )
        return ToolResult(ok=True, status="audit_recorded", data={"task": payload})

    def _processed_message_ids(self) -> set[str]:
        processed: set[str] = set()
        for entry in self.context.store.list_audit_logs():
            if (
                entry.event_type == "watcher_task"
                and entry.payload.get("message_id")
                and entry.payload.get("status") != "paused"
            ):
                processed.add(str(entry.payload["message_id"]))
        return processed


def _action_payload(action: AutoReplyAction) -> dict[str, object]:
    return {
        "kind": action.kind,
        "message": action.message,
        "status_after_send": action.status_after_send,
        "send_attachment_resume": action.send_attachment_resume,
        "resume_file": action.resume_file,
        "blocked_reason": action.blocked_reason,
    }


def _error_metadata(error: object) -> dict[str, object]:
    code = _error_attr(error, "error_code") or _error_attr(error, "code")
    message = (
        _error_attr(error, "error_message")
        or _error_attr(error, "message")
        or _error_attr(error, "status")
        or str(error)
        or error.__class__.__name__
    )
    recoverable = bool(_error_attr(error, "recoverable"))
    recovery_action = _error_attr(error, "recovery_action")
    if code and not recovery_action:
        recoverable, recovery_action = error_contract_for_code(
            str(code),
            fallback_recoverable=recoverable,
            fallback_recovery_action=None,
        )
    hints = _error_attr(error, "hints")
    return {
        "error_code": str(code or ""),
        "error_message": str(message or ""),
        "recoverable": recoverable,
        "recovery_action": str(recovery_action or ""),
        "hints": hints if isinstance(hints, dict) else {},
    }


def _error_attr(error: object, key: str) -> object:
    if isinstance(error, dict):
        return error.get(key)
    return getattr(error, key, None)
```

- [ ] **Step 4: Run the agent tool tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_agent_tools.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/boss_agent_cli/rag_reply/agent_tools.py tests/test_rag_reply_agent_tools.py
git commit -m "feat: add guarded boss agent tools"
```

---

### Task 2: Add Tool-Calling Reply Graph

**Files:**
- Create: `src/boss_agent_cli/rag_reply/tool_graph.py`
- Create: `tests/test_rag_reply_tool_graph.py`

- [ ] **Step 1: Write the failing tool graph tests**

Create `tests/test_rag_reply_tool_graph.py` with this content:

```python
from pathlib import Path

from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.tool_graph import run_tool_reply_graph
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


class _RagResult:
    ok = True
    answer = "您好，我主要负责企业级 RAG 的检索链路和回答编排。"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "draft_created"
    send_allowed = False
    approval_required = True


class _RagAdapter:
    def answer(self, **kwargs):
        return _RagResult()


class _Delivery:
    def __init__(self):
        self.calls = []

    def send(
        self,
        *,
        security_id,
        message,
        send_attachment_resume=False,
        resume_file="",
        target=None,
    ):
        self.calls.append(
            {
                "security_id": security_id,
                "message": message,
                "send_attachment_resume": send_attachment_resume,
                "resume_file": resume_file,
                "target": target or {},
            }
        )
        return {"ok": True, "status": "sent", "message_sent": True, "resume_sent": False}


def _config(tmp_path, *, dry_run=False, send_enabled=True):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return WatcherConfig(
        enabled=True,
        dry_run=dry_run,
        live_sync=True,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        resume_attachment_path=str(resume),
        send_enabled=send_enabled,
        require_send_enabled=True,
    )


def _toolbox(tmp_path, *, dry_run=False, send_enabled=True):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())
    delivery = _Delivery()
    context = BossAgentToolContext(
        store=store,
        service=service,
        config=_config(tmp_path, dry_run=dry_run, send_enabled=send_enabled),
        delivery=delivery,
        message_syncer=None,
    )
    return BossAgentToolbox(context), store, delivery


def _message(store):
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={
                "security_id": "sec_001",
                "recruiter_name": "李HR",
                "company": "测试公司",
                "title": "AI 工程师",
            },
        )
    )
    message = MessageRecord(
        message_id="msg_001",
        conversation_id="conv_001",
        message_text="介绍下你的 RAG 项目",
        direction="inbound",
    )
    store.save_message(message)
    return message


def test_tool_reply_graph_calls_guarded_tools_and_records_audit(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    message = _message(store)

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "sent"
    assert result.intent == "project_question"
    assert result.task["message_id"] == "msg_001"
    assert result.task["status"] == "sent"
    assert [step["tool"] for step in result.tool_steps] == [
        "create_rag_draft",
        "decide_auto_action",
        "resolve_boss_target",
        "send_boss_reply_guarded",
        "record_watcher_audit",
    ]
    assert delivery.calls[0]["security_id"] == "sec_001"
    assert delivery.calls[0]["message"].startswith("您好，我主要负责")
    audit = store.list_audit_logs("conv_001")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["tool_steps"][-1]["tool"] == "record_watcher_audit"


def test_tool_reply_graph_blocks_missing_security_id_without_delivery(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="boss_sync"))
    message = MessageRecord(
        message_id="msg_001",
        conversation_id="conv_001",
        message_text="介绍下你的 RAG 项目",
        direction="inbound",
    )
    store.save_message(message)

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "blocked_manual_required"
    assert result.error_message == "missing_security_id"
    assert delivery.calls == []
    assert result.task["status"] == "blocked_manual_required"
    assert result.task["tool_steps"][-2]["tool"] == "resolve_boss_target"


def test_tool_reply_graph_dry_run_records_delivery_without_send(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)
    message = _message(store)

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "sent"
    assert result.task["dry_run"] is True
    assert result.task["delivery"] == {"ok": True, "status": "dry_run"}
    assert delivery.calls == []
```

- [ ] **Step 2: Run the failing tool graph tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_tool_graph.py -q
```

Expected:

```text
ERROR tests/test_rag_reply_tool_graph.py - ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.tool_graph'
```

- [ ] **Step 3: Create `tool_graph.py`**

Create `src/boss_agent_cli/rag_reply/tool_graph.py` with this content:

```python
"""LangGraph tool-calling flow for one Boss inbound reply."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from boss_agent_cli.rag_reply.agent_tools import BossAgentToolbox, ToolResult
from boss_agent_cli.rag_reply.models import MessageRecord


class ToolReplyState(TypedDict, total=False):
    message: MessageRecord
    draft_id: str
    intent: str
    action: dict[str, object]
    security_id: str
    target: dict[str, str]
    delivery: dict[str, object]
    status: str
    error_message: str
    task: dict[str, object]
    tool_steps: list[dict[str, object]]


@dataclass(slots=True)
class ToolReplyGraphResult:
    status: str
    intent: str
    task: dict[str, object]
    tool_steps: list[dict[str, object]] = field(default_factory=list)
    error_message: str = ""


def run_tool_reply_graph(
    *,
    message: MessageRecord,
    toolbox: BossAgentToolbox,
) -> ToolReplyGraphResult:
    initial: ToolReplyState = {
        "message": message,
        "status": "",
        "error_message": "",
        "tool_steps": [],
    }
    final = _run_langgraph_or_fallback(initial, toolbox)
    return ToolReplyGraphResult(
        status=str(final.get("status") or "blocked_manual_required"),
        intent=str(final.get("intent") or "unknown"),
        task=dict(final.get("task") or {}),
        tool_steps=list(final.get("tool_steps") or []),
        error_message=str(final.get("error_message") or ""),
    )


def _run_langgraph_or_fallback(
    state: ToolReplyState,
    toolbox: BossAgentToolbox,
) -> ToolReplyState:
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return _run_sequential(state, toolbox)

    graph = StateGraph(ToolReplyState)
    graph.add_node("create_rag_draft", lambda current: _create_rag_draft(current, toolbox))
    graph.add_node("decide_auto_action", lambda current: _decide_auto_action(current, toolbox))
    graph.add_node("resolve_boss_target", lambda current: _resolve_boss_target(current, toolbox))
    graph.add_node("send_boss_reply_guarded", lambda current: _send_boss_reply_guarded(current, toolbox))
    graph.add_node("record_watcher_audit", lambda current: _record_watcher_audit(current, toolbox))
    graph.set_entry_point("create_rag_draft")
    graph.add_conditional_edges(
        "create_rag_draft",
        _route_after_tool,
        {"continue": "decide_auto_action", "audit": "record_watcher_audit"},
    )
    graph.add_conditional_edges(
        "decide_auto_action",
        _route_after_tool,
        {"continue": "resolve_boss_target", "audit": "record_watcher_audit"},
    )
    graph.add_conditional_edges(
        "resolve_boss_target",
        _route_after_tool,
        {"continue": "send_boss_reply_guarded", "audit": "record_watcher_audit"},
    )
    graph.add_edge("send_boss_reply_guarded", "record_watcher_audit")
    graph.add_edge("record_watcher_audit", END)
    return graph.compile().invoke(state)


def _run_sequential(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    current = dict(state)
    for node in (
        _create_rag_draft,
        _decide_auto_action,
        _resolve_boss_target,
        _send_boss_reply_guarded,
    ):
        current.update(node(current, toolbox))
        if current.get("error_message"):
            break
    current.update(_record_watcher_audit(current, toolbox))
    return current


def _create_rag_draft(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    message = state["message"]
    result = toolbox.create_rag_draft(message_id=message.message_id)
    updates = _merge_step(state, "create_rag_draft", result)
    if not result.ok:
        return updates
    return {
        **updates,
        "draft_id": str(result.data.get("draft_id") or ""),
        "intent": str(result.data.get("intent") or "unknown"),
    }


def _decide_auto_action(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    result = toolbox.decide_auto_action(draft_id=str(state.get("draft_id") or ""))
    updates = _merge_step(state, "decide_auto_action", result)
    if not result.ok:
        return updates
    return {**updates, "action": dict(result.data.get("action") or {})}


def _resolve_boss_target(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    message = state["message"]
    result = toolbox.resolve_boss_target(conversation_id=message.conversation_id)
    updates = _merge_step(state, "resolve_boss_target", result)
    if not result.ok:
        return updates
    return {
        **updates,
        "security_id": str(result.data.get("security_id") or ""),
        "target": dict(result.data.get("target") or {}),
    }


def _send_boss_reply_guarded(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    result = toolbox.send_boss_reply_guarded(
        action=dict(state.get("action") or {}),
        security_id=str(state.get("security_id") or ""),
        target=dict(state.get("target") or {}),
    )
    updates = _merge_step(state, "send_boss_reply_guarded", result)
    return {
        **updates,
        "delivery": dict(result.data.get("delivery") or {}),
    }


def _record_watcher_audit(state: ToolReplyState, toolbox: BossAgentToolbox) -> ToolReplyState:
    message = state["message"]
    result = toolbox.record_watcher_audit(
        message_id=message.message_id,
        conversation_id=message.conversation_id,
        draft_id=str(state.get("draft_id") or ""),
        intent=str(state.get("intent") or "unknown"),
        status=str(state.get("status") or "blocked_manual_required"),
        error_message=str(state.get("error_message") or ""),
        dry_run=toolbox.context.config.dry_run,
        action=dict(state.get("action") or {}),
        delivery=dict(state.get("delivery") or {}),
        tool_steps=list(state.get("tool_steps") or []),
    )
    updates = _merge_step(state, "record_watcher_audit", result)
    return {**updates, "task": dict(result.data.get("task") or {})}


def _merge_step(
    state: ToolReplyState,
    tool_name: str,
    result: ToolResult,
) -> ToolReplyState:
    tool_steps = list(state.get("tool_steps") or [])
    tool_steps.append(
        {
            "tool": tool_name,
            "ok": result.ok,
            "status": result.status,
            "error_code": result.error_code,
            "error_message": result.error_message,
        }
    )
    updates: ToolReplyState = {
        "tool_steps": tool_steps,
        "status": result.status,
        "error_message": result.error_message,
    }
    return updates


def _route_after_tool(state: ToolReplyState) -> str:
    return "audit" if state.get("error_message") else "continue"
```

- [ ] **Step 4: Run the tool graph tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_tool_graph.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/boss_agent_cli/rag_reply/tool_graph.py tests/test_rag_reply_tool_graph.py
git commit -m "feat: add boss tool reply graph"
```

---

### Task 3: Wire Tool Graph Into Watcher

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/watcher.py`
- Modify: `tests/test_passive_watcher.py`

- [ ] **Step 1: Write watcher integration regression tests**

Append these tests to `tests/test_passive_watcher.py`:

```python
def test_passive_watcher_records_tool_steps_for_sent_reply(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={"security_id": "sec_001"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert result.tasks[0]["status"] == "sent"
    assert [step["tool"] for step in result.tasks[0]["tool_steps"]] == [
        "create_rag_draft",
        "decide_auto_action",
        "resolve_boss_target",
        "send_boss_reply_guarded",
    ]
    assert delivery.calls[0]["security_id"] == "sec_001"


def test_passive_watcher_tool_graph_blocks_missing_security_id(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(ConversationRecord(conversation_id="conv_001", source="boss_sync"))
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "missing_security_id"
    assert delivery.calls == []
```

- [ ] **Step 2: Run watcher tests and confirm failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_passive_watcher.py::test_passive_watcher_records_tool_steps_for_sent_reply tests/test_passive_watcher.py::test_passive_watcher_tool_graph_blocks_missing_security_id -q
```

Expected:

```text
FAILED tests/test_passive_watcher.py::test_passive_watcher_records_tool_steps_for_sent_reply
FAILED tests/test_passive_watcher.py::test_passive_watcher_tool_graph_blocks_missing_security_id
```

- [ ] **Step 3: Update watcher imports**

In `src/boss_agent_cli/rag_reply/watcher.py`, replace these imports:

```python
from boss_agent_cli.rag_reply.auto_actions import AutoReplyAction
from boss_agent_cli.rag_reply.auto_graph import run_auto_reply_graph
```

with:

```python
from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.tool_graph import run_tool_reply_graph
```

- [ ] **Step 4: Replace `_process_message`**

In `src/boss_agent_cli/rag_reply/watcher.py`, replace `_process_message` with:

```python
    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        context = BossAgentToolContext(
            store=self.store,
            service=self.service,
            config=self.config,
            delivery=self.delivery,
            message_syncer=self.message_syncer,
        )
        result = run_tool_reply_graph(
            message=message,
            toolbox=BossAgentToolbox(context),
        )
        return result.task
```

- [ ] **Step 5: Remove obsolete watcher action helpers**

In `src/boss_agent_cli/rag_reply/watcher.py`, remove these now-unused methods and helpers:

```python
    def _record_task(
        self,
        *,
        message: MessageRecord,
        status: str,
        intent: str,
        draft_id: str,
        error_message: str = "",
        dry_run: bool = False,
        action: AutoReplyAction | None = None,
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
        state = (
            conversation.state
            if conversation and isinstance(conversation.state, dict)
            else {}
        )
        recruiter = None
        if conversation and conversation.recruiter_id:
            recruiter = self.store.get_recruiter(str(conversation.recruiter_id))
        return {
            "recruiter_name": str(
                state.get("recruiter_name")
                or (recruiter.display_name if recruiter else "")
                or ""
            ),
            "company": str(state.get("company") or ""),
            "title": str(state.get("title") or ""),
            "security_id": str(state.get("security_id") or ""),
            "gid": str(state.get("gid") or ""),
            "friend_id": str(state.get("friend_id") or ""),
            "uid": str(state.get("uid") or ""),
            "encrypt_boss_id": str(state.get("encrypt_boss_id") or ""),
            "recruiter_id": str(state.get("recruiter_id") or (conversation.recruiter_id if conversation else "") or ""),
        }
```

Remove these bottom helpers as well:

```python
def _action_payload(action: AutoReplyAction | None) -> dict[str, object]:
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


def _action_from_payload(payload: dict[str, object]) -> AutoReplyAction | None:
    if not payload:
        return None
    return AutoReplyAction(
        kind=str(payload.get("kind") or ""),
        message=str(payload.get("message") or ""),
        status_after_send=str(payload.get("status_after_send") or "sent"),
        send_attachment_resume=bool(payload.get("send_attachment_resume") or False),
        resume_file=str(payload.get("resume_file") or ""),
        blocked_reason=str(payload.get("blocked_reason") or ""),
    )
```

- [ ] **Step 6: Update paused task recording**

In `src/boss_agent_cli/rag_reply/watcher.py`, replace the paused branch inside `run_once`:

```python
                task = self._record_task(
                    message=message,
                    status="paused",
                    intent="unknown",
                    draft_id="",
                    error_message="conversation_paused",
                )
```

with:

```python
                task = {
                    "message_id": message.message_id,
                    "conversation_id": message.conversation_id,
                    "draft_id": "",
                    "intent": "unknown",
                    "status": "paused",
                    "error_message": "conversation_paused",
                    "dry_run": self.config.dry_run,
                    "action": {},
                    "delivery": {},
                    "tool_steps": [],
                }
                self.store.append_audit_log(
                    AuditLogRecord.new(
                        event_type="watcher_task",
                        entity_type="conversation",
                        entity_id=message.conversation_id,
                        payload=task,
                    )
                )
```

- [ ] **Step 7: Run watcher tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_passive_watcher.py tests/test_rag_reply_tool_graph.py tests/test_rag_reply_agent_tools.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```bash
git add src/boss_agent_cli/rag_reply/watcher.py tests/test_passive_watcher.py
git commit -m "feat: route boss watcher through guarded tools"
```

---

### Task 4: Preserve CLI Watcher Contract

**Files:**
- Modify: `tests/test_rag_reply_commands.py`
- Modify: `src/boss_agent_cli/commands/rag.py`

- [ ] **Step 1: Add CLI contract test for tool metadata**

Append this test to `tests/test_rag_reply_commands.py`:

```python
def test_agent_watcher_run_returns_tool_steps_from_tool_agent(monkeypatch, tmp_path: Path):
    (tmp_path / "config.json").write_text(
        json.dumps({"boss_rag_watcher_enabled": True}),
        encoding="utf-8",
    )

    class _FakeWatcher:
        def run_once(self, *, live_sync=None):
            return rag_commands.WatcherRunResult(
                processed=1,
                skipped=0,
                blocked=0,
                tasks=[
                    {
                        "message_id": "msg_001",
                        "conversation_id": "conv_001",
                        "status": "sent",
                        "intent": "project_question",
                        "tool_steps": [
                            {"tool": "create_rag_draft", "ok": True, "status": "draft_created"},
                            {"tool": "send_boss_reply_guarded", "ok": True, "status": "sent"},
                        ],
                    }
                ],
            )

    monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "watcher-run",
            "--once",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    task = payload["data"]["tasks"][0]
    assert task["tool_steps"][0]["tool"] == "create_rag_draft"
    assert task["tool_steps"][1]["tool"] == "send_boss_reply_guarded"
```

- [ ] **Step 2: Run CLI contract test**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_commands.py::test_agent_watcher_run_returns_tool_steps_from_tool_agent -q
```

Expected:

```text
1 passed
```

This test passes immediately because `watcher-run` serializes watcher task dictionaries without dropping fields. That is acceptable because this task locks the CLI contract rather than driving new production code.

- [ ] **Step 3: Move duplicated read-disabled metadata into a helper**

In `src/boss_agent_cli/commands/rag.py`, add this helper above `_CliWatcherMessageSyncer`:

```python
def _read_disabled_sync_result() -> dict[str, object]:
    return {
        "ok": False,
        "status": "read_disabled",
        "error_code": "RAG_READ_NOT_ENABLED",
        "error_message": "Boss message reading is disabled by default.",
        "recoverable": True,
        "recovery_action": "Set boss_rag_allow_message_read=true in config.json and retry.",
        "count": 0,
    }
```

Then replace this block in `_CliWatcherMessageSyncer.sync_messages`:

```python
            return {
                "ok": False,
                "status": "read_disabled",
                "error_code": "RAG_READ_NOT_ENABLED",
                "error_message": "Boss message reading is disabled by default.",
                "recoverable": True,
                "recovery_action": "Set boss_rag_allow_message_read=true in config.json and retry.",
                "count": 0,
            }
```

with:

```python
            return _read_disabled_sync_result()
```

- [ ] **Step 4: Run command tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_commands.py::test_cli_watcher_message_syncer_normalizes_read_disabled_and_success tests/test_rag_reply_commands.py::test_agent_watcher_run_live_sync_read_disabled_records_recovery tests/test_rag_reply_commands.py::test_agent_watcher_run_returns_tool_steps_from_tool_agent -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```bash
git add src/boss_agent_cli/commands/rag.py tests/test_rag_reply_commands.py
git commit -m "test: preserve boss watcher tool metadata"
```

---

### Task 5: Documentation And Verification

**Files:**
- Modify: `docs/boss-agent-current-stage.md`

- [ ] **Step 1: Update current stage docs**

In `docs/boss-agent-current-stage.md`, find the section that describes the Boss inbound full-auto chain. Replace the chain with:

````markdown
Boss 主动消息 guarded tool-agent 链路是：

```text
Boss inbound message
  -> boss agent watcher-run --loop or frontend watcher interval
  -> _CliWatcherMessageSyncer.sync_messages
  -> BossPassiveWatcher.run_once(live_sync=True)
  -> run_tool_reply_graph
  -> BossAgentToolbox.create_rag_draft
  -> BossAgentToolbox.decide_auto_action
  -> BossAgentToolbox.resolve_boss_target
  -> BossAgentToolbox.send_boss_reply_guarded
  -> BossAgentToolbox.record_watcher_audit
```

这里的 “Agent tool” 是受保护工具，不是裸 LLM tool-calling：

- LangGraph 负责按状态调用 tool node。
- `BossAgentToolbox` 负责把 sync、draft、action、target、send、audit 暴露成工具。
- 真实发送工具内部再次检查 `boss_rag_send_enabled`、`boss_rag_watcher_dry_run`、`security_id` 和附件简历路径。
- `resume_share_request` 只能通过 `send_attachment_resume_guarded` 进入附件简历路径。
- CDP/Bridge 不可用、`AUTH_EXPIRED`、`TOKEN_REFRESH_FAILED`、`ACCOUNT_RISK`、sync 禁用、缺少 `security_id` 或空草稿时，tool 返回结构化 blocked result，watcher 只写 audit，不发送。
````

- [ ] **Step 2: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_agent_tools.py tests/test_rag_reply_tool_graph.py tests/test_passive_watcher.py tests/test_rag_reply_commands.py tests/test_auto_reply_graph.py tests/test_rag_reply_service.py tests/test_watcher_config.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run lint and diff checks**

Run:

```bash
ruff check src/boss_agent_cli/rag_reply/agent_tools.py src/boss_agent_cli/rag_reply/tool_graph.py src/boss_agent_cli/rag_reply/watcher.py src/boss_agent_cli/commands/rag.py tests/test_rag_reply_agent_tools.py tests/test_rag_reply_tool_graph.py tests/test_passive_watcher.py tests/test_rag_reply_commands.py
git diff --check
```

Expected:

```text
All checks passed!
```

`git diff --check` should produce no output.

- [ ] **Step 4: Run fake full-auto smoke without real Boss**

Run:

```bash
.venv/bin/python -m pytest tests/test_rag_reply_agent_tools.py::test_send_boss_reply_guarded_dry_run_does_not_call_delivery tests/test_rag_reply_tool_graph.py::test_tool_reply_graph_dry_run_records_delivery_without_send -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Decide whether real BOSS bounded verification is required**

Use this rule:

```text
If the implementation only refactors watcher orchestration into guarded tools and does not change _CliWatcherDelivery, execute_chat_reply, BossAutomationAdapter, CDP, Bridge, browser fetch, search, auto-greet, or outreach result aggregation, do not run real BOSS auto-greet verification.

If any implementation task changes _CliWatcherDelivery, execute_chat_reply, BossAutomationAdapter, CDP, Bridge, browser fetch, search, auto-greet, or outreach result aggregation, run exactly one bounded real BOSS auto-greet verification with current default filters and report total_greeted, total_failed, stopped_reason, and platform error.
```

- [ ] **Step 6: Commit docs**

Run:

```bash
git add docs/boss-agent-current-stage.md
git commit -m "docs: describe boss guarded tool agent"
```

---

## Runtime Contract After This Plan

Full-auto remains explicitly opt-in:

```json
{
  "boss_rag_allow_message_read": true,
  "boss_rag_send_enabled": true,
  "boss_rag_watcher_enabled": true,
  "boss_rag_watcher_dry_run": false,
  "boss_rag_watcher_live_sync": true,
  "boss_rag_contact_phone": "13800138000",
  "boss_rag_contact_wechat": "reggie-ai",
  "boss_rag_interview_windows": "工作日 20:00 后",
  "boss_rag_resume_attachment_path": "/absolute/path/to/resume.pdf"
}
```

Expected agent chain:

```text
watcher loop
  -> sync_boss_messages
  -> per-message tool graph
  -> create_rag_draft
  -> decide_auto_action
  -> resolve_boss_target
  -> send_boss_reply_guarded or send_attachment_resume_guarded
  -> record_watcher_audit
```

The LLM can help compose answers through existing `AgentAnswerAdapter`, and future agent planners can call the same guarded tools. The write tools remain deterministic and policy-gated.

## Self-Review

**Spec coverage:**  
这份计划覆盖了用户要求的 “不注册成工具 agent 怎么调用”：Task 1 建 tool API，Task 2 建 LangGraph tool graph，Task 3 接入 watcher，Task 4 锁 CLI 输出，Task 5 更新文档和验证边界。附件简历和 fail-closed 边界在 Task 1 的 guarded send tools 和 Task 5 的 runtime contract 中覆盖。

**Red-flag scan:**  
计划没有未定义函数名；后续任务使用的 `BossAgentToolContext`、`BossAgentToolbox`、`ToolResult`、`run_tool_reply_graph` 都在前置任务中定义。每个测试和实现步骤都给出具体路径、命令和预期结果。

**Type consistency:**  
`ToolResult.as_payload()`、`BossAgentToolbox.*` 方法返回字段与 `tool_graph.py` 使用的 `status`、`data`、`error_message`、`tool_steps` 一致。`WatcherRunResult.tasks` 继续是 `list[dict[str, object]]`，CLI 不需要 schema migration。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-boss-guarded-tool-agent.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
