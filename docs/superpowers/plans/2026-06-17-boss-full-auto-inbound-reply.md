# Boss Full Auto Inbound Reply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Boss 主动消息的全自动闭环：自动读取新消息、LangGraph 编排决策、生成回复、按配置自动发送，并持续写入 audit。

**Architecture:** 保留现有 Boss bridge / CDP / RAG / draft store 边界，把 `BossPassiveWatcher` 从“本地 store 单次处理器”升级为“live sync + LangGraph decision + delivery”的自动执行器。LangGraph 只负责对话状态和动作编排，不直接访问 BOSS；所有真实平台读写仍走现有 `BossAutomationAdapter` / `execute_chat_reply`，并遵守 `AGENTS.md` 的 Bridge/CDP only 规则。

**Tech Stack:** Python 3.10+, Click CLI, SQLite `RagReplyStore`, existing `BossRagReplyService`, optional `langgraph>=1.0.0`, Vite/React demo bridge, pytest, ruff.

---

## Scope

用户明确要“全自动”，本计划实现的是：

```text
Boss 主动消息
-> live sync 到本地 store
-> watcher 发现未处理 inbound message
-> LangGraph 编排 create_draft / decide_action / resolve_target / deliver_or_dry_run / record_audit
-> dry_run=false 时自动发送
-> 前端 watcher console 自动轮询触发
```

仍然保留这些底线：

- Bridge/CDP 不可用时 fail closed，不走 headless patchright。
- `ACCOUNT_RISK` / 通道异常时 hard-stop，不重试刷平台。
- 空草稿、RAG 失败、缺少 `security_id` 不发送，只写 audit。
- “全自动”需要显式配置打开，避免误触真实 Boss。

## File Structure

- Modify `src/boss_agent_cli/config.py`  
  增加 watcher 全自动配置的 defaults 和 env aliases。

- Modify `src/boss_agent_cli/rag_reply/watcher_config.py`  
  扩展 `WatcherConfig`，支持 `live_sync`、`require_send_enabled`、`send_enabled`。

- Create `src/boss_agent_cli/rag_reply/auto_actions.py`  
  独立保存自动回复 action decision，避免 `auto_graph.py` 和 `watcher.py` 相互导入形成 circular import。

- Create `src/boss_agent_cli/rag_reply/auto_graph.py`  
  新增 LangGraph orchestration module。输入 message/draft/config/delivery，输出结构化 decision/result。模块内部提供 langgraph 不可用时的顺序 fallback，保证测试环境不用真实 LangGraph 也能跑。

- Modify `src/boss_agent_cli/rag_reply/watcher.py`  
  接入 `auto_graph`，支持 live syncer、pause 控制、全自动发送。

- Modify `src/boss_agent_cli/commands/rag.py`  
  增加 `_CliWatcherMessageSyncer`，让 `agent watcher-run --once --live-sync` 先读 Boss 新消息；增加 `--loop` 常驻模式。

- Modify `demo/interview-simulator/vite.config.mjs`  
  让 `/api/agent/watcher/run` 支持 `{liveSync: true}`，并传给 CLI。

- Modify `demo/interview-simulator/src/App.jsx`  
  watcher console 在 running 状态下自动定时调用 `/api/agent/watcher/run`，展示 live sync / send 结果。

- Tests:
  - Modify `tests/test_output.py`
  - Modify `tests/test_watcher_config.py`
  - Create `tests/test_auto_reply_graph.py`
  - Create `tests/test_passive_watcher.py`
  - Modify `tests/test_rag_reply_commands.py`
  - Frontend smoke via fake CLI, no real Boss calls

---

### Task 1: Add Full-Auto Watcher Configuration

**Files:**
- Modify: `src/boss_agent_cli/config.py`
- Modify: `src/boss_agent_cli/rag_reply/watcher_config.py`
- Modify: `tests/test_output.py`
- Modify: `tests/test_watcher_config.py`

- [ ] **Step 1: Write failing config tests**

Append to `tests/test_output.py`:

```python
def test_load_config_reads_watcher_env_aliases(monkeypatch, tmp_path):
	monkeypatch.setenv("BOSS_RAG_WATCHER_ENABLED", "true")
	monkeypatch.setenv("BOSS_RAG_WATCHER_DRY_RUN", "false")
	monkeypatch.setenv("BOSS_RAG_WATCHER_LIVE_SYNC", "true")
	monkeypatch.setenv("BOSS_RAG_WATCHER_POLL_SECONDS", "7")
	monkeypatch.setenv("BOSS_RAG_CONTACT_PHONE", "13800138000")
	monkeypatch.setenv("BOSS_RAG_CONTACT_WECHAT", "reggie-ai")
	monkeypatch.setenv("BOSS_RAG_INTERVIEW_WINDOWS", "工作日 20:00 后")
	monkeypatch.setenv("BOSS_RAG_RESUME_ATTACHMENT_PATH", "/tmp/resume.pdf")

	from boss_agent_cli.config import load_config

	cfg = load_config(tmp_path / "missing.json")

	assert cfg["boss_rag_watcher_enabled"] is True
	assert cfg["boss_rag_watcher_dry_run"] is False
	assert cfg["boss_rag_watcher_live_sync"] is True
	assert cfg["boss_rag_watcher_poll_seconds"] == 7
	assert cfg["boss_rag_contact_phone"] == "13800138000"
	assert cfg["boss_rag_contact_wechat"] == "reggie-ai"
	assert cfg["boss_rag_interview_windows"] == "工作日 20:00 后"
	assert cfg["boss_rag_resume_attachment_path"] == "/tmp/resume.pdf"
```

Append to `tests/test_watcher_config.py`:

```python
def test_watcher_config_reads_full_auto_flags():
	config = WatcherConfig.from_mapping(
		{
			"boss_rag_watcher_enabled": True,
			"boss_rag_watcher_dry_run": False,
			"boss_rag_watcher_live_sync": True,
			"boss_rag_watcher_poll_seconds": 3,
			"boss_rag_watcher_max_failures_per_conversation": 2,
			"boss_rag_watcher_require_send_enabled": True,
			"boss_rag_send_enabled": True,
			"boss_rag_contact_phone": "13800138000",
			"boss_rag_contact_wechat": "reggie-ai",
			"boss_rag_interview_windows": "工作日 20:00 后",
			"boss_rag_resume_attachment_path": "/tmp/resume.pdf",
		}
	)

	assert config.enabled is True
	assert config.dry_run is False
	assert config.live_sync is True
	assert config.poll_seconds == 5
	assert config.max_failures_per_conversation == 2
	assert config.require_send_enabled is True
	assert config.send_enabled is True
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest tests/test_output.py::test_load_config_reads_watcher_env_aliases tests/test_watcher_config.py::test_watcher_config_reads_full_auto_flags -q
```

Expected:

```text
FAILED tests/test_output.py::test_load_config_reads_watcher_env_aliases
FAILED tests/test_watcher_config.py::test_watcher_config_reads_full_auto_flags
```

- [ ] **Step 3: Update `config.py` defaults and env aliases**

Modify `DEFAULTS` in `src/boss_agent_cli/config.py` by adding these keys after `boss_rag_send_enabled`:

```python
	"boss_rag_watcher_enabled": False,
	"boss_rag_watcher_dry_run": True,
	"boss_rag_watcher_live_sync": False,
	"boss_rag_watcher_poll_seconds": 20,
	"boss_rag_watcher_max_failures_per_conversation": 3,
	"boss_rag_watcher_require_send_enabled": True,
	"boss_rag_contact_phone": "",
	"boss_rag_contact_wechat": "",
	"boss_rag_interview_windows": "",
	"boss_rag_resume_attachment_path": "",
```

Modify `ENV_ALIASES` in `src/boss_agent_cli/config.py` by adding:

```python
	"boss_rag_watcher_enabled": ("BOSS_RAG_WATCHER_ENABLED",),
	"boss_rag_watcher_dry_run": ("BOSS_RAG_WATCHER_DRY_RUN",),
	"boss_rag_watcher_live_sync": ("BOSS_RAG_WATCHER_LIVE_SYNC",),
	"boss_rag_watcher_poll_seconds": ("BOSS_RAG_WATCHER_POLL_SECONDS",),
	"boss_rag_watcher_max_failures_per_conversation": ("BOSS_RAG_WATCHER_MAX_FAILURES_PER_CONVERSATION",),
	"boss_rag_watcher_require_send_enabled": ("BOSS_RAG_WATCHER_REQUIRE_SEND_ENABLED",),
	"boss_rag_contact_phone": ("BOSS_RAG_CONTACT_PHONE",),
	"boss_rag_contact_wechat": ("BOSS_RAG_CONTACT_WECHAT",),
	"boss_rag_interview_windows": ("BOSS_RAG_INTERVIEW_WINDOWS",),
	"boss_rag_resume_attachment_path": ("BOSS_RAG_RESUME_ATTACHMENT_PATH",),
```

- [ ] **Step 4: Update `WatcherConfig`**

In `src/boss_agent_cli/rag_reply/watcher_config.py`, replace the dataclass with:

```python
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
    live_sync: bool = False
    require_send_enabled: bool = True
    send_enabled: bool = False

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> "WatcherConfig":
        return cls(
            enabled=bool(values.get("boss_rag_watcher_enabled", False)),
            dry_run=bool(values.get("boss_rag_watcher_dry_run", True)),
            contact_phone=str(values.get("boss_rag_contact_phone") or "").strip(),
            contact_wechat=str(values.get("boss_rag_contact_wechat") or "").strip(),
            interview_windows=str(values.get("boss_rag_interview_windows") or "").strip(),
            resume_attachment_path=str(
                values.get("boss_rag_resume_attachment_path") or ""
            ).strip(),
            poll_seconds=max(5, int(values.get("boss_rag_watcher_poll_seconds") or 20)),
            max_failures_per_conversation=max(
                1,
                int(values.get("boss_rag_watcher_max_failures_per_conversation") or 3),
            ),
            live_sync=bool(values.get("boss_rag_watcher_live_sync", False)),
            require_send_enabled=bool(
                values.get("boss_rag_watcher_require_send_enabled", True)
            ),
            send_enabled=bool(values.get("boss_rag_send_enabled", False)),
        )
```

- [ ] **Step 5: Run config tests**

Run:

```bash
python -m pytest tests/test_output.py::test_load_config_reads_watcher_env_aliases tests/test_watcher_config.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/config.py src/boss_agent_cli/rag_reply/watcher_config.py tests/test_output.py tests/test_watcher_config.py
git commit -m "feat: add boss watcher auto config"
```

---

### Task 2: Add LangGraph Auto-Reply Decision Graph

**Files:**
- Create: `src/boss_agent_cli/rag_reply/auto_actions.py`
- Create: `src/boss_agent_cli/rag_reply/auto_graph.py`
- Create: `tests/test_auto_reply_graph.py`

- [ ] **Step 1: Write graph tests**

Create `tests/test_auto_reply_graph.py`:

```python
from dataclasses import dataclass

from boss_agent_cli.rag_reply.auto_graph import run_auto_reply_graph
from boss_agent_cli.rag_reply.models import DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


@dataclass
class _Delivery:
	calls: list[dict]

	def send(
		self,
		*,
		security_id: str,
		message: str,
		send_attachment_resume: bool = False,
		resume_file: str = "",
		target: dict[str, str] | None = None,
	) -> dict[str, object]:
		payload = {
			"security_id": security_id,
			"message": message,
			"send_attachment_resume": send_attachment_resume,
			"resume_file": resume_file,
			"target": target or {},
		}
		self.calls.append(payload)
		return {"ok": True, "status": "sent", "message_sent": True, "resume_sent": False}


def _config(*, dry_run: bool, send_enabled: bool = True) -> WatcherConfig:
	return WatcherConfig(
		enabled=True,
		dry_run=dry_run,
		live_sync=True,
		contact_phone="13800138000",
		contact_wechat="reggie-ai",
		interview_windows="工作日 20:00 后",
		resume_attachment_path="/tmp/resume.pdf",
		send_enabled=send_enabled,
		require_send_enabled=True,
	)


def _message() -> MessageRecord:
	return MessageRecord(
		message_id="msg_001",
		conversation_id="conv_001",
		message_text="介绍下你的 RAG 项目",
		direction="inbound",
	)


def _draft() -> DraftRecord:
	return DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="您好，我主要负责企业级 RAG 的检索链路和回答编排。",
		intent="project_question",
	)


def test_auto_reply_graph_dry_run_records_send_without_delivery():
	delivery = _Delivery(calls=[])

	result = run_auto_reply_graph(
		message=_message(),
		draft=_draft(),
		config=_config(dry_run=True),
		resolve_security_id=lambda conversation_id: "sec_001",
		target_payload=lambda conversation_id: {"company": "测试公司"},
		delivery=delivery,
	)

	assert result.status == "sent"
	assert result.dry_run is True
	assert result.delivery == {"ok": True, "status": "dry_run"}
	assert result.action["message"].startswith("您好，我主要负责")
	assert delivery.calls == []


def test_auto_reply_graph_live_sends_when_enabled():
	delivery = _Delivery(calls=[])

	result = run_auto_reply_graph(
		message=_message(),
		draft=_draft(),
		config=_config(dry_run=False, send_enabled=True),
		resolve_security_id=lambda conversation_id: "sec_001",
		target_payload=lambda conversation_id: {"company": "测试公司"},
		delivery=delivery,
	)

	assert result.status == "sent"
	assert result.dry_run is False
	assert result.delivery["ok"] is True
	assert delivery.calls == [
		{
			"security_id": "sec_001",
			"message": "您好，我主要负责企业级 RAG 的检索链路和回答编排。",
			"send_attachment_resume": False,
			"resume_file": "",
			"target": {"company": "测试公司"},
		}
	]


def test_auto_reply_graph_blocks_live_send_when_send_flag_disabled():
	delivery = _Delivery(calls=[])

	result = run_auto_reply_graph(
		message=_message(),
		draft=_draft(),
		config=_config(dry_run=False, send_enabled=False),
		resolve_security_id=lambda conversation_id: "sec_001",
		target_payload=lambda conversation_id: {"company": "测试公司"},
		delivery=delivery,
	)

	assert result.status == "blocked_manual_required"
	assert result.error_message == "boss_rag_send_enabled_disabled"
	assert delivery.calls == []


def test_auto_reply_graph_blocks_missing_security_id():
	delivery = _Delivery(calls=[])

	result = run_auto_reply_graph(
		message=_message(),
		draft=_draft(),
		config=_config(dry_run=False, send_enabled=True),
		resolve_security_id=lambda conversation_id: "",
		target_payload=lambda conversation_id: {"company": "测试公司"},
		delivery=delivery,
	)

	assert result.status == "blocked_manual_required"
	assert result.error_message == "missing_security_id"
	assert delivery.calls == []
```

- [ ] **Step 2: Run graph tests and confirm failure**

Run:

```bash
python -m pytest tests/test_auto_reply_graph.py -q
```

Expected:

```text
ERROR tests/test_auto_reply_graph.py - ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.auto_graph'
```

- [ ] **Step 3: Create `auto_actions.py`**

Create `src/boss_agent_cli/rag_reply/auto_actions.py`:

```python
"""Action decisions for automatic Boss inbound replies."""

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


@dataclass(slots=True)
class AutoReplyAction:
	kind: str
	message: str = ""
	status_after_send: str = "sent"
	send_attachment_resume: bool = False
	resume_file: str = ""
	blocked_reason: str = ""


def build_action_for_draft(draft: DraftRecord, config: WatcherConfig) -> AutoReplyAction:
	intent = draft.intent
	draft_text = (draft.draft_text or "").strip()
	if intent in {
		"project_question",
		"resume_question",
		"smalltalk",
		"resignation_status",
		"personal_status",
		"job_location_acceptance",
	}:
		if not draft_text:
			return AutoReplyAction(
				kind="block", status_after_send="rag_failed", blocked_reason="empty_draft"
			)
		return AutoReplyAction(kind="send_text", message=draft_text)
	if intent == "resume_share_request":
		resume_file = _require_resume_file(config.resume_attachment_path)
		message = draft_text or "可以的，我这边通过 BOSS 直聘发送附件简历给您。"
		return AutoReplyAction(
			kind="send_text",
			message=message,
			send_attachment_resume=True,
			resume_file=resume_file,
		)
	if intent in {"interview_time", "availability_or_schedule"}:
		return AutoReplyAction(
			kind="send_text", message=build_interview_window_reply(config)
		)
	if intent == "contact_exchange":
		return AutoReplyAction(kind="send_text", message=build_contact_reply(config))
	if intent == "salary_or_offer":
		if draft_text and draft_text != salary_handoff_reply():
			return AutoReplyAction(kind="send_text", message=draft_text)
		return AutoReplyAction(
			kind="send_text",
			message=salary_handoff_reply(),
			status_after_send="blocked_manual_required",
		)
	return AutoReplyAction(
		kind="block",
		status_after_send="blocked_manual_required",
		blocked_reason="intent_not_allowlisted",
	)


def _require_resume_file(value: str) -> str:
	path = Path(value).expanduser()
	if not value.strip() or not path.is_file():
		raise WatcherConfigError(
			"boss_rag_resume_attachment_path must point to an existing PDF file."
		)
	if path.suffix.lower() != ".pdf":
		raise WatcherConfigError(
			"boss_rag_resume_attachment_path must point to a PDF file."
		)
	return str(path)
```

- [ ] **Step 4: Create `auto_graph.py`**

Create `src/boss_agent_cli/rag_reply/auto_graph.py`:

```python
"""LangGraph-backed auto reply decision flow for Boss inbound messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TypedDict

from boss_agent_cli.rag_reply.auto_actions import AutoReplyAction, build_action_for_draft
from boss_agent_cli.rag_reply.models import DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig, WatcherConfigError


class AutoReplyDelivery(Protocol):
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


@dataclass(slots=True)
class AutoReplyGraphResult:
	status: str
	intent: str
	dry_run: bool
	action: dict[str, object]
	delivery: dict[str, object]
	error_message: str = ""


class AutoReplyState(TypedDict, total=False):
	message: MessageRecord
	draft: DraftRecord
	config: WatcherConfig
	action: AutoReplyAction
	security_id: str
	target: dict[str, str]
	delivery: dict[str, object]
	status: str
	error_message: str


ResolveSecurityId = Callable[[str], str]
TargetPayload = Callable[[str], dict[str, str]]


def run_auto_reply_graph(
	*,
	message: MessageRecord,
	draft: DraftRecord,
	config: WatcherConfig,
	resolve_security_id: ResolveSecurityId,
	target_payload: TargetPayload,
	delivery: AutoReplyDelivery,
) -> AutoReplyGraphResult:
	"""Run the auto-reply decision graph.

	The graph itself never touches BOSS. It only calls the supplied delivery
	protocol after channel/config checks have passed.
	"""
	initial: AutoReplyState = {"message": message, "draft": draft, "config": config}
	final = _run_langgraph_or_fallback(
		initial,
		resolve_security_id=resolve_security_id,
		target_payload=target_payload,
		delivery=delivery,
	)
	action = final.get("action")
	return AutoReplyGraphResult(
		status=str(final.get("status") or "blocked_manual_required"),
		intent=draft.intent,
		dry_run=config.dry_run,
		action=_action_payload(action),
		delivery=dict(final.get("delivery") or {}),
		error_message=str(final.get("error_message") or ""),
	)


def _run_langgraph_or_fallback(
	state: AutoReplyState,
	*,
	resolve_security_id: ResolveSecurityId,
	target_payload: TargetPayload,
	delivery: AutoReplyDelivery,
) -> AutoReplyState:
	try:
		from langgraph.graph import END, StateGraph
	except ImportError:
		return _run_sequential(
			state,
			resolve_security_id=resolve_security_id,
			target_payload=target_payload,
			delivery=delivery,
		)

	graph = StateGraph(AutoReplyState)
	graph.add_node("decide_action", _decide_action_node)
	graph.add_node(
		"resolve_target",
		lambda current: _resolve_target_node(
			current,
			resolve_security_id=resolve_security_id,
			target_payload=target_payload,
		),
	)
	graph.add_node(
		"deliver",
		lambda current: _deliver_node(current, delivery=delivery),
	)
	graph.set_entry_point("decide_action")
	graph.add_conditional_edges(
		"decide_action",
		_route_after_decision,
		{"block": END, "resolve": "resolve_target"},
	)
	graph.add_conditional_edges(
		"resolve_target",
		_route_after_target,
		{"block": END, "deliver": "deliver"},
	)
	graph.add_edge("deliver", END)
	app = graph.compile()
	return app.invoke(state)


def _run_sequential(
	state: AutoReplyState,
	*,
	resolve_security_id: ResolveSecurityId,
	target_payload: TargetPayload,
	delivery: AutoReplyDelivery,
) -> AutoReplyState:
	current = _decide_action_node(state)
	if _route_after_decision(current) == "block":
		return current
	current = _resolve_target_node(
		current,
		resolve_security_id=resolve_security_id,
		target_payload=target_payload,
	)
	if _route_after_target(current) == "block":
		return current
	return _deliver_node(current, delivery=delivery)


def _decide_action_node(state: AutoReplyState) -> AutoReplyState:
	draft = state["draft"]
	config = state["config"]
	try:
		action = build_action_for_draft(draft, config)
	except WatcherConfigError as exc:
		return {
			**state,
			"status": "blocked_manual_required",
			"error_message": str(exc),
		}
	if action.kind == "block":
		return {
			**state,
			"action": action,
			"status": action.status_after_send,
			"error_message": action.blocked_reason,
		}
	return {**state, "action": action}


def _resolve_target_node(
	state: AutoReplyState,
	*,
	resolve_security_id: ResolveSecurityId,
	target_payload: TargetPayload,
) -> AutoReplyState:
	config = state["config"]
	if not config.dry_run and config.require_send_enabled and not config.send_enabled:
		return {
			**state,
			"status": "blocked_manual_required",
			"error_message": "boss_rag_send_enabled_disabled",
		}
	conversation_id = state["message"].conversation_id
	security_id = resolve_security_id(conversation_id)
	if not security_id:
		return {
			**state,
			"status": "blocked_manual_required",
			"error_message": "missing_security_id",
		}
	return {
		**state,
		"security_id": security_id,
		"target": target_payload(conversation_id),
	}


def _deliver_node(state: AutoReplyState, *, delivery: AutoReplyDelivery) -> AutoReplyState:
	action = state["action"]
	config = state["config"]
	if config.dry_run:
		return {
			**state,
			"status": action.status_after_send,
			"delivery": {"ok": True, "status": "dry_run"},
		}
	result = delivery.send(
		security_id=state["security_id"],
		message=action.message,
		send_attachment_resume=action.send_attachment_resume,
		resume_file=action.resume_file,
		target=state.get("target") or {},
	)
	return {
		**state,
		"status": action.status_after_send if result.get("ok") else "send_failed",
		"delivery": result,
	}


def _route_after_decision(state: AutoReplyState) -> str:
	return "block" if state.get("status") else "resolve"


def _route_after_target(state: AutoReplyState) -> str:
	return "block" if state.get("status") else "deliver"


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
```

- [ ] **Step 5: Run graph tests**

Run:

```bash
python -m pytest tests/test_auto_reply_graph.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/auto_actions.py src/boss_agent_cli/rag_reply/auto_graph.py tests/test_auto_reply_graph.py
git commit -m "feat: add boss auto reply graph"
```

---

### Task 3: Integrate Graph and Live Sync Into Watcher

**Files:**
- Modify: `src/boss_agent_cli/rag_reply/watcher.py`
- Modify: `tests/test_rag_reply_commands.py`
- Create or modify: `tests/test_passive_watcher.py` if no watcher unit file exists

- [ ] **Step 1: Write watcher integration tests**

Create `tests/test_passive_watcher.py`:

```python
from dataclasses import dataclass

from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher import BossPassiveWatcher
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


@dataclass
class _RagResult:
	ok: bool = True
	answer: str = "您好，我主要负责企业级 RAG 的检索链路和回答编排。"
	citations: list[dict] = None
	reasoning_summary: dict | None = None
	raw_response: dict | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True

	def __post_init__(self):
		if self.citations is None:
			self.citations = []


class _RagAdapter:
	def answer(self, **kwargs):
		return _RagResult()


@dataclass
class _Delivery:
	calls: list[dict]

	def send(self, **kwargs):
		self.calls.append(dict(kwargs))
		return {"ok": True, "status": "sent", "message_sent": True}


class _Syncer:
	def __init__(self):
		self.calls = 0

	def sync_messages(self, *, conversation_id=None):
		self.calls += 1
		return {"count": 1, "conversation_ids": ["conv_001"], "message_ids": ["msg_001"]}


def _config(*, dry_run=False, live_sync=True):
	return WatcherConfig(
		enabled=True,
		dry_run=dry_run,
		live_sync=live_sync,
		contact_phone="13800138000",
		contact_wechat="reggie-ai",
		interview_windows="工作日 20:00 后",
		resume_attachment_path="/tmp/resume.pdf",
		send_enabled=True,
		require_send_enabled=True,
	)


def test_passive_watcher_syncs_live_messages_before_processing(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
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
	syncer = _Syncer()
	delivery = _Delivery(calls=[])
	service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())

	watcher = BossPassiveWatcher(
		store=store,
		service=service,
		config=_config(dry_run=False, live_sync=True),
		delivery=delivery,
		message_syncer=syncer,
	)

	result = watcher.run_once(live_sync=True)

	assert syncer.calls == 1
	assert result.processed == 1
	assert result.blocked == 0
	assert delivery.calls[0]["security_id"] == "sec_001"
	assert delivery.calls[0]["message"].startswith("您好，我主要负责")


def test_passive_watcher_respects_pause_control(tmp_path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
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
	from boss_agent_cli.rag_reply.models import AuditLogRecord

	store.append_audit_log(
		AuditLogRecord.new(
			event_type="watcher_control",
			entity_type="conversation",
			entity_id="conv_001",
			payload={"action": "pause", "conversation_id": "conv_001"},
		)
	)
	delivery = _Delivery(calls=[])
	service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())

	watcher = BossPassiveWatcher(
		store=store,
		service=service,
		config=_config(dry_run=False, live_sync=False),
		delivery=delivery,
	)

	result = watcher.run_once(live_sync=False)

	assert result.processed == 0
	assert result.blocked == 1
	assert result.tasks[0]["status"] == "paused"
	assert delivery.calls == []
```

- [ ] **Step 2: Run watcher tests and confirm failure**

Run:

```bash
python -m pytest tests/test_passive_watcher.py -q
```

Expected:

```text
FAILED tests/test_passive_watcher.py::test_passive_watcher_syncs_live_messages_before_processing
FAILED tests/test_passive_watcher.py::test_passive_watcher_respects_pause_control
```

- [ ] **Step 3: Add syncer protocol and graph call to watcher**

In `src/boss_agent_cli/rag_reply/watcher.py`, add imports near the existing imports:

```python
from boss_agent_cli.rag_reply.auto_actions import AutoReplyAction
from boss_agent_cli.rag_reply.auto_graph import run_auto_reply_graph
```

Remove the existing `WatcherAction` dataclass and `build_action_for_draft(...)` helper from `watcher.py`; Task 2 moved that action logic into `auto_actions.py`.

Add this protocol after `WatcherDelivery`:

```python
class WatcherMessageSyncer(Protocol):
    def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
        raise NotImplementedError
```

Change `BossPassiveWatcher.__init__` signature:

```python
    def __init__(
        self,
        *,
        store: RagReplyStore,
        service: BossRagReplyService,
        config: WatcherConfig,
        delivery: WatcherDelivery,
        message_syncer: WatcherMessageSyncer | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.config = config
        self.delivery = delivery
        self.message_syncer = message_syncer
```

Change `run_once`:

```python
    def run_once(self, *, live_sync: bool | None = None) -> WatcherRunResult:
        if live_sync is None:
            live_sync = self.config.live_sync
        if live_sync and self.message_syncer is not None:
            self.message_syncer.sync_messages()
        processed = 0
        skipped = 0
        blocked = 0
        tasks: list[dict[str, object]] = []
        for message in self._candidate_messages():
            if self._is_paused(message.conversation_id):
                blocked += 1
                task = self._record_task(
                    message=message,
                    status="paused",
                    intent="unknown",
                    draft_id="",
                    error_message="conversation_paused",
                )
                tasks.append(task)
                continue
            if self._already_processed(message.message_id):
                skipped += 1
                tasks.append(
                    {"message_id": message.message_id, "status": "skipped_duplicate"}
                )
                continue
            task = self._process_message(message)
            tasks.append(task)
            if task["status"] == "sent":
                processed += 1
            elif task["status"] in {"blocked_manual_required", "paused"}:
                blocked += 1
            else:
                processed += 1
        return WatcherRunResult(
            processed=processed, skipped=skipped, blocked=blocked, tasks=tasks
        )
```

Replace `_process_message` with:

```python
    def _process_message(self, message: MessageRecord) -> dict[str, object]:
        draft = self.service.create_draft_for_message(message.message_id)
        result = run_auto_reply_graph(
            message=message,
            draft=draft,
            config=self.config,
            resolve_security_id=self._resolve_security_id,
            target_payload=self._target_payload,
            delivery=self.delivery,
        )
        return self._record_task(
            message=message,
            status=result.status,
            intent=draft.intent,
            draft_id=draft.draft_id,
            error_message=result.error_message,
            dry_run=result.dry_run,
            action=_action_from_payload(result.action),
            delivery=result.delivery,
        )
```

Add `_is_paused` method:

```python
    def _is_paused(self, conversation_id: str) -> bool:
        paused = False
        for entry in self.store.list_audit_logs(conversation_id):
            if entry.event_type != "watcher_control":
                continue
            action = str(entry.payload.get("action") or "")
            if action == "pause":
                paused = True
            elif action == "resume":
                paused = False
        return paused
```

Add helper at bottom:

```python
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

- [ ] **Step 4: Run watcher tests**

Run:

```bash
python -m pytest tests/test_passive_watcher.py tests/test_auto_reply_graph.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/watcher.py tests/test_passive_watcher.py
git commit -m "feat: wire auto graph into boss watcher"
```

---

### Task 4: Add Live Sync and Loop Mode to CLI Watcher

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Modify: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Write CLI tests**

Append to `tests/test_rag_reply_commands.py`:

```python
def test_agent_watcher_run_once_live_sync_passes_flag(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
				"boss_rag_allow_message_read": True,
			}
		),
		encoding="utf-8",
	)
	called = {"live_sync": None}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			called["live_sync"] = live_sync
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": "msg_001", "status": "sent"}],
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
			"--live-sync",
		],
	)

	assert result.exit_code == 0
	assert called["live_sync"] is True
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["processed"] == 1


def test_agent_watcher_run_loop_stops_at_max_cycles(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
				"boss_rag_watcher_poll_seconds": 5,
			}
		),
		encoding="utf-8",
	)
	calls = {"run_once": 0, "sleep": []}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			calls["run_once"] += 1
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": f"msg_{calls['run_once']}", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	monkeypatch.setattr(rag_commands.time, "sleep", lambda seconds: calls["sleep"].append(seconds))
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--loop",
			"--max-cycles",
			"2",
		],
	)

	assert result.exit_code == 0
	assert calls["run_once"] == 2
	assert calls["sleep"] == [5]
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["status"] == "completed"
	assert payload["data"]["cycles"] == 2
	assert payload["data"]["processed"] == 2
```

- [ ] **Step 2: Run CLI tests and confirm failure**

Run:

```bash
python -m pytest tests/test_rag_reply_commands.py::test_agent_watcher_run_once_live_sync_passes_flag tests/test_rag_reply_commands.py::test_agent_watcher_run_loop_stops_at_max_cycles -q
```

Expected:

```text
FAILED
```

- [ ] **Step 3: Add CLI syncer and loop support**

In `src/boss_agent_cli/commands/rag.py`, add import:

```python
import time
```

Add this class after `_CliWatcherDelivery`:

```python
class _CliWatcherMessageSyncer:
	"""Sync recent Boss messages before a watcher cycle."""

	def __init__(self, ctx: click.Context) -> None:
		self.ctx = ctx

	def sync_messages(self, *, conversation_id: str | None = None) -> dict[str, object]:
		config = self.ctx.obj.get("config", {}) if self.ctx and self.ctx.obj else {}
		if not bool(config.get("boss_rag_allow_message_read", False)):
			return {
				"ok": False,
				"status": "read_disabled",
				"count": 0,
			}
		with _build_boss_adapter(self.ctx) as adapter:
			result = adapter.sync_messages(conversation_id=conversation_id)
		return {
			"ok": True,
			"status": "synced",
			"count": result.count,
			"conversation_ids": result.conversation_ids,
			"message_ids": result.message_ids,
		}
```

Modify `_build_passive_watcher`:

```python
def _build_passive_watcher(ctx: click.Context) -> BossPassiveWatcher:
	"""Construct the passive watcher using the shared RAG service and CLI delivery."""
	service = _build_service(ctx)
	return BossPassiveWatcher(
		store=service.store,
		service=service,
		config=_build_watcher_config(ctx),
		delivery=_CliWatcherDelivery(ctx),
		message_syncer=_CliWatcherMessageSyncer(ctx),
	)
```

Replace `rag_watcher_run_cmd` decorator and function:

```python
@rag_group.command("watcher-run")
@click.option("--once", is_flag=True, default=False)
@click.option("--loop", "loop_mode", is_flag=True, default=False)
@click.option("--live-sync/--no-live-sync", default=None)
@click.option("--max-cycles", default=None, type=int)
@click.pass_context
def rag_watcher_run_cmd(
	ctx: click.Context,
	once: bool,
	loop_mode: bool,
	live_sync: bool | None,
	max_cycles: int | None,
) -> None:
	if once == loop_mode:
		handle_error_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			code="INVALID_PARAM",
			message="watcher-run requires exactly one of --once or --loop.",
			recoverable=True,
			recovery_action="Run agent watcher-run --once or agent watcher-run --loop.",
		)
		return
	config = _build_watcher_config(ctx)
	if not config.enabled:
		handle_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			{
				"status": "paused",
				"reason": "watcher_disabled",
				"processed": 0,
				"skipped": 0,
				"blocked": 0,
				"tasks": [],
			},
			render=lambda data: click.echo("Watcher is disabled; no tasks processed.", err=True),
		)
		return
	watcher = _build_passive_watcher(ctx)
	effective_live_sync = config.live_sync if live_sync is None else live_sync
	if once:
		payload = _watcher_result_payload(watcher.run_once(live_sync=effective_live_sync))
		handle_output(
			ctx,
			_workflow_command(ctx, "watcher-run"),
			payload,
			render=lambda data: click.echo(
				f"Watcher processed {data['processed']} task(s), skipped {data['skipped']}, blocked {data['blocked']}.",
				err=True,
			),
		)
		return
	cycles = 0
	processed = 0
	skipped = 0
	blocked = 0
	tasks: list[dict[str, object]] = []
	while True:
		cycles += 1
		result = watcher.run_once(live_sync=effective_live_sync)
		processed += result.processed
		skipped += result.skipped
		blocked += result.blocked
		tasks.extend(result.tasks)
		if max_cycles is not None and cycles >= max_cycles:
			break
		time.sleep(config.poll_seconds)
	payload = {
		"status": "completed",
		"cycles": cycles,
		"processed": processed,
		"skipped": skipped,
		"blocked": blocked,
		"tasks": tasks[-20:],
	}
	handle_output(
		ctx,
		_workflow_command(ctx, "watcher-run"),
		payload,
		render=lambda data: click.echo(
			f"Watcher loop completed {data['cycles']} cycle(s).",
			err=True,
		),
	)
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
python -m pytest tests/test_rag_reply_commands.py::test_agent_watcher_run_once_live_sync_passes_flag tests/test_rag_reply_commands.py::test_agent_watcher_run_loop_stops_at_max_cycles -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/commands/rag.py tests/test_rag_reply_commands.py
git commit -m "feat: add live boss watcher loop"
```

---

### Task 5: Make Frontend Watcher Trigger Full-Auto Cycles

**Files:**
- Modify: `demo/interview-simulator/vite.config.mjs`
- Modify: `demo/interview-simulator/src/App.jsx`

- [ ] **Step 1: Update Vite bridge API shape**

In `demo/interview-simulator/vite.config.mjs`, replace the watcher run handler body with:

```js
    if (req.method === "POST" && isWatcherRun) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        const liveSync = Boolean(body.liveSync);
        const args = ["agent", "watcher-run", "--once"];
        if (liveSync) args.push("--live-sync");
        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        const payload = error?.commandPayload;
        res.statusCode = payload?.error?.recoverable ? 502 : 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "运行 watcher 失败。",
          }),
        );
      }
      return true;
    }
```

- [ ] **Step 2: Update frontend run call**

In `demo/interview-simulator/src/App.jsx`, change `runWatcherOnce` fetch from:

```js
      const response = await fetch("/api/agent/watcher/run", { method: "POST" });
```

to:

```js
      const response = await fetch("/api/agent/watcher/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ liveSync: true }),
      });
```

- [ ] **Step 3: Add auto interval while watcher is enabled**

In `demo/interview-simulator/src/App.jsx`, add this effect after `runWatcherOnce` is defined:

```js
  useEffect(() => {
    if (!watcherState.running || isWatcherBusy) return undefined;
    const timer = window.setInterval(() => {
      runWatcherOnce();
    }, 20_000);
    return () => window.clearInterval(timer);
  }, [watcherState.running, isWatcherBusy]);
```

If eslint complains about `runWatcherOnce` dependency, wrap `runWatcherOnce` in `useCallback` with dependencies `isWatcherBusy` and `loadWatcherStatus`, then use it in the effect.

- [ ] **Step 4: Run frontend build**

Run:

```bash
npm run build
```

Expected:

```text
✓ built
```

- [ ] **Step 5: Mock QA without touching real Boss**

Create executable fake CLI at `/tmp/boss-agent-fake-watcher`:

```python
#!/usr/bin/env python3
import json
import sys

args = sys.argv[1:]
if "watcher-status" in args:
    print(json.dumps({
        "ok": True,
        "data": {
            "running": True,
            "dry_run": False,
            "tasks": []
        }
    }, ensure_ascii=False))
elif "watcher-run" in args:
    print(json.dumps({
        "ok": True,
        "data": {
            "status": "completed",
            "processed": 1,
            "skipped": 0,
            "blocked": 0,
            "tasks": [
                {
                    "message_id": "msg_001",
                    "conversation_id": "conv_001",
                    "intent": "project_question",
                    "status": "sent",
                    "dry_run": False
                }
            ]
        }
    }, ensure_ascii=False))
else:
    print(json.dumps({"ok": True, "data": {}}, ensure_ascii=False))
```

Run Vite with fake CLI:

```bash
chmod +x /tmp/boss-agent-fake-watcher
BOSS_RAG_PYTHON_BIN=/tmp/boss-agent-fake-watcher npm run dev -- --host 127.0.0.1 --port 5199 --strictPort
```

Run a browser smoke with system Chrome:

```bash
node --input-type=module - <<'NODE'
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true, executablePath: '/usr/bin/google-chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto('http://127.0.0.1:5199/', { waitUntil: 'domcontentloaded' });
  await page.getByText('Watcher Console').waitFor({ timeout: 10000 });
  await page.getByText('刷新').click();
  await page.getByText('live-send').waitFor({ timeout: 10000 });
  await page.getByText('运行').click();
  await page.getByText('project_question').waitFor({ timeout: 10000 });
  await page.getByText('sent').waitFor({ timeout: 10000 });
  console.log('watcher frontend smoke passed');
} finally {
  await browser.close();
}
NODE
```

Expected:

```text
watcher frontend smoke passed
```

- [ ] **Step 6: Stop fake dev server and clean temp file**

```bash
rm -f /tmp/boss-agent-fake-watcher
```

- [ ] **Step 7: Commit**

```bash
git add demo/interview-simulator/vite.config.mjs demo/interview-simulator/src/App.jsx
git commit -m "feat: auto-run boss watcher from frontend"
```

---

### Task 6: End-to-End Verification and Documentation Note

**Files:**
- Modify: `docs/boss-agent-current-stage.md`

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
python -m pytest tests/test_auto_reply_graph.py tests/test_passive_watcher.py tests/test_watcher_config.py tests/test_rag_reply_commands.py tests/test_rag_reply_service.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run broader relevant tests**

Run:

```bash
python -m pytest tests/test_browser_client.py tests/test_display.py tests/test_commands.py tests/test_greet_extended.py tests/test_search_filters.py tests/test_search_pipeline.py tests/test_platform_base.py tests/test_rag_reply_commands.py tests/test_rag_reply_service.py tests/test_watcher_config.py tests/test_auto_reply_graph.py tests/test_passive_watcher.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run ruff**

Run:

```bash
ruff check src/boss_agent_cli/config.py src/boss_agent_cli/rag_reply/watcher_config.py src/boss_agent_cli/rag_reply/auto_actions.py src/boss_agent_cli/rag_reply/auto_graph.py src/boss_agent_cli/rag_reply/watcher.py src/boss_agent_cli/commands/rag.py tests/test_auto_reply_graph.py tests/test_passive_watcher.py tests/test_watcher_config.py tests/test_rag_reply_commands.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd demo/interview-simulator
npm run build
```

Expected:

```text
✓ built
```

- [ ] **Step 5: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Update stage documentation**

In `docs/boss-agent-current-stage.md`, change:

```markdown
> Last updated: 2026-06-16
```

to:

```markdown
> Last updated: 2026-06-17
```

Under `## Architecture Status`, after the `发送到 Boss 的链路是：` code block and before `本阶段最重要的新边界是：`, insert:

````markdown
Boss 主动消息全自动链路是：

```text
Boss inbound message
  -> boss agent watcher-run --loop or frontend watcher interval
  -> _CliWatcherMessageSyncer.sync_messages(...)
  -> BossPassiveWatcher.run_once(live_sync=True)
  -> BossRagReplyService.create_draft_for_message(...)
  -> run_auto_reply_graph(...)
  -> _CliWatcherDelivery.send(...)
  -> execute_chat_reply(...)
```

这个链路只有在显式配置打开时才会发送真实消息：

- `boss_rag_allow_message_read=true`
- `boss_rag_send_enabled=true`
- `boss_rag_watcher_enabled=true`
- `boss_rag_watcher_dry_run=false`
- `boss_rag_watcher_live_sync=true`
````

Under `本阶段最重要的新边界是：`, append these bullets:

```markdown
- `run_auto_reply_graph(...)` 只做状态编排和动作决策，不直接访问 Boss 页面。
- 真实 Boss 读写仍然只通过 Bridge/CDP channel 和 CLI adapter 进入。
- Frontend watcher console 的 running 状态会周期性触发 `POST /api/agent/watcher/run { liveSync: true }`。
- Bridge/CDP 不可用、`ACCOUNT_RISK`、`AUTH_EXPIRED`、缺少 `security_id` 或空草稿时，全自动链路只写 audit，不发送。
```

- [ ] **Step 7: Confirm no real Boss calls were used during verification**

Run:

```bash
git status --short
```

Expected: only intended changed files are shown, plus pre-existing unrelated untracked files such as `demo/package-lock.json`.

- [ ] **Step 8: Commit final docs**

```bash
git add docs/boss-agent-current-stage.md
git commit -m "docs: update boss full auto watcher status"
```

---

## Runtime Configuration For Full Auto

After implementation, the explicit opt-in config should look like this in `~/.boss-agent/config.json` or equivalent env:

```json
{
  "boss_rag_allow_message_read": true,
  "boss_rag_send_enabled": true,
  "boss_rag_watcher_enabled": true,
  "boss_rag_watcher_dry_run": false,
  "boss_rag_watcher_live_sync": true,
  "boss_rag_watcher_poll_seconds": 20,
  "boss_rag_contact_phone": "13800138000",
  "boss_rag_contact_wechat": "reggie-ai",
  "boss_rag_interview_windows": "工作日 20:00 后，周末全天",
  "boss_rag_resume_attachment_path": "/absolute/path/to/resume.pdf"
}
```

CLI full-auto run:

```bash
boss agent watcher-run --loop
```

Single cycle with live sync:

```bash
boss agent watcher-run --once --live-sync
```

Frontend path:

```text
Watcher Console enabled
-> periodic POST /api/agent/watcher/run { liveSync: true }
-> agent watcher-run --once --live-sync
```

## Self-Review

**Spec coverage:**  
“全自动”由 Task 3 + Task 4 + Task 5 覆盖：live sync、LangGraph decision、automatic delivery、CLI loop、frontend interval。已有 LangChain agent 能力由 Task 2 复用为 graph node input，不重写 RAG/draft service。

**Placeholder scan:**  
Plan avoids `TBD`, vague “add tests”, or unspecified code paths. Every implementation task names exact files and includes concrete test or implementation snippets.

**Type consistency:**  
`WatcherConfig.live_sync`, `WatcherConfig.send_enabled`, `run_auto_reply_graph(...)`, `BossPassiveWatcher.run_once(live_sync=...)`, and CLI `--live-sync` are named consistently across tasks.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-boss-full-auto-inbound-reply.md`. Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
