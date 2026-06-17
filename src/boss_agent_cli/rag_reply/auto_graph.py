"""LangGraph-backed automatic reply decision graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, TypedDict

from boss_agent_cli.rag_reply.auto_actions import (
    AutoReplyAction,
    build_action_for_draft,
)
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
        ...


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


def run_auto_reply_graph(
    *,
    message: MessageRecord,
    draft: DraftRecord,
    config: WatcherConfig,
    resolve_security_id: Callable[[str], str],
    target_payload: Callable[[str], dict[str, str]],
    delivery: AutoReplyDelivery,
) -> AutoReplyGraphResult:
    state: AutoReplyState = {
        "message": message,
        "draft": draft,
        "config": config,
        "delivery": {},
        "status": "",
        "error_message": "",
    }
    final_state = _run_langgraph_or_fallback(
        state=state,
        resolve_security_id=resolve_security_id,
        target_payload=target_payload,
        delivery=delivery,
    )
    return AutoReplyGraphResult(
        status=str(final_state.get("status") or ""),
        intent=draft.intent,
        dry_run=config.dry_run,
        action=_action_payload(final_state.get("action")),
        delivery=dict(final_state.get("delivery") or {}),
        error_message=str(final_state.get("error_message") or ""),
    )


def _run_langgraph_or_fallback(
    *,
    state: AutoReplyState,
    resolve_security_id: Callable[[str], str],
    target_payload: Callable[[str], dict[str, str]],
    delivery: AutoReplyDelivery,
) -> AutoReplyState:
    resolve_node = _resolve_target_node(resolve_security_id, target_payload)
    deliver_node = _deliver_node(delivery)
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return _run_sequential_fallback(state, resolve_node, deliver_node)

    graph = StateGraph(AutoReplyState)
    graph.add_node("decide_action", _decide_action_node)
    graph.add_node("resolve_target", resolve_node)
    graph.add_node("deliver", deliver_node)
    graph.set_entry_point("decide_action")
    graph.add_conditional_edges(
        "decide_action",
        _route_after_decide,
        {"block": END, "resolve": "resolve_target"},
    )
    graph.add_conditional_edges(
        "resolve_target",
        _route_after_resolve,
        {"block": END, "deliver": "deliver"},
    )
    graph.add_edge("deliver", END)
    return graph.compile().invoke(state)


def _run_sequential_fallback(
    state: AutoReplyState,
    resolve_node: Callable[[AutoReplyState], AutoReplyState],
    deliver_node: Callable[[AutoReplyState], AutoReplyState],
) -> AutoReplyState:
    current = dict(state)
    current.update(_decide_action_node(current))
    if _route_after_decide(current) == "block":
        return current
    current.update(resolve_node(current))
    if _route_after_resolve(current) == "block":
        return current
    current.update(deliver_node(current))
    return current


def _decide_action_node(state: AutoReplyState) -> AutoReplyState:
    try:
        action = build_action_for_draft(state["draft"], state["config"])
    except WatcherConfigError as exc:
        return {
            "status": "blocked_manual_required",
            "error_message": str(exc),
        }
    if action.kind == "block":
        return {
            "action": action,
            "status": action.status_after_send,
            "error_message": action.blocked_reason,
        }
    return {"action": action}


def _resolve_target_node(
    resolve_security_id: Callable[[str], str],
    target_payload: Callable[[str], dict[str, str]],
) -> Callable[[AutoReplyState], AutoReplyState]:
    def _node(state: AutoReplyState) -> AutoReplyState:
        config = state["config"]
        if (
            not config.dry_run
            and config.require_send_enabled
            and not config.send_enabled
        ):
            return {
                "status": "blocked_manual_required",
                "error_message": "boss_rag_send_enabled_disabled",
            }
        conversation_id = state["message"].conversation_id
        security_id = resolve_security_id(conversation_id).strip()
        if not security_id:
            return {
                "status": "blocked_manual_required",
                "error_message": "missing_security_id",
            }
        return {
            "security_id": security_id,
            "target": dict(target_payload(conversation_id)),
        }

    return _node


def _deliver_node(
    delivery: AutoReplyDelivery,
) -> Callable[[AutoReplyState], AutoReplyState]:
    def _node(state: AutoReplyState) -> AutoReplyState:
        action = state["action"]
        if state["config"].dry_run:
            return {
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
        status = action.status_after_send if result.get("ok") else "send_failed"
        return {"status": status, "delivery": result}

    return _node


def _route_after_decide(state: AutoReplyState) -> str:
    action = state.get("action")
    if action is None or action.kind == "block":
        return "block"
    return "resolve"


def _route_after_resolve(state: AutoReplyState) -> str:
    if state.get("status") == "blocked_manual_required" and state.get(
        "error_message"
    ):
        return "block"
    return "deliver"


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
