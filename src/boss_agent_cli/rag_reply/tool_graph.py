"""Tool-calling graph for one Boss inbound reply."""

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
    graph.add_node(
        "decide_auto_action", lambda current: _decide_auto_action(current, toolbox)
    )
    graph.add_node(
        "resolve_boss_target", lambda current: _resolve_boss_target(current, toolbox)
    )
    graph.add_node(
        "send_boss_reply_guarded",
        lambda current: _send_boss_reply_guarded(current, toolbox),
    )
    graph.add_node(
        "record_watcher_audit",
        lambda current: _record_watcher_audit(current, toolbox),
    )
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
        if _route_after_tool(current) == "audit":
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


def _decide_auto_action(
    state: ToolReplyState,
    toolbox: BossAgentToolbox,
) -> ToolReplyState:
    result = toolbox.decide_auto_action(draft_id=str(state.get("draft_id") or ""))
    updates = _merge_step(state, "decide_auto_action", result)
    if not result.ok:
        return updates
    return {**updates, "action": dict(result.data.get("action") or {})}


def _resolve_boss_target(
    state: ToolReplyState,
    toolbox: BossAgentToolbox,
) -> ToolReplyState:
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


def _send_boss_reply_guarded(
    state: ToolReplyState,
    toolbox: BossAgentToolbox,
) -> ToolReplyState:
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


def _record_watcher_audit(
    state: ToolReplyState,
    toolbox: BossAgentToolbox,
) -> ToolReplyState:
    message = state["message"]
    business_status = str(state.get("status") or "blocked_manual_required")
    business_error = str(state.get("error_message") or "")
    tool_steps = _with_record_audit_step(state)
    result = toolbox.record_watcher_audit(
        message_id=message.message_id,
        conversation_id=message.conversation_id,
        draft_id=str(state.get("draft_id") or ""),
        intent=str(state.get("intent") or "unknown"),
        status=business_status,
        error_message=business_error,
        dry_run=toolbox.context.config.dry_run,
        action=dict(state.get("action") or {}),
        delivery=dict(state.get("delivery") or {}),
        tool_steps=tool_steps,
    )
    if not result.ok:
        tool_steps[-1] = _step_payload("record_watcher_audit", result)
        return {
            "tool_steps": tool_steps,
            "status": result.status,
            "error_message": result.error_message,
            "task": dict(result.data.get("task") or {}),
        }
    return {
        "tool_steps": tool_steps,
        "status": business_status,
        "error_message": business_error,
        "task": dict(result.data.get("task") or {}),
    }


def _merge_step(
    state: ToolReplyState,
    tool_name: str,
    result: ToolResult,
) -> ToolReplyState:
    tool_steps = list(state.get("tool_steps") or [])
    tool_steps.append(_step_payload(tool_name, result))
    return {
        "tool_steps": tool_steps,
        "status": result.status,
        "error_message": result.error_message,
    }


def _with_record_audit_step(state: ToolReplyState) -> list[dict[str, object]]:
    tool_steps = list(state.get("tool_steps") or [])
    tool_steps.append(
        {
            "tool": "record_watcher_audit",
            "ok": True,
            "status": "audit_recorded",
            "error_code": "",
            "error_message": "",
        }
    )
    return tool_steps


def _step_payload(tool_name: str, result: ToolResult) -> dict[str, object]:
    return {
        "tool": tool_name,
        "ok": result.ok,
        "status": result.status,
        "error_code": result.error_code,
        "error_message": result.error_message,
    }


def _route_after_tool(state: ToolReplyState) -> str:
    return "audit" if state.get("error_message") else "continue"
