"""Stateful LangGraph MCP agent for boss-agent-cli.

Run from the repo root:

    pip install -e ".[langchain]"
    export BOSS_LANGCHAIN_API_KEY=...
    export BOSS_LANGCHAIN_MODEL=gpt-5
    python examples/langgraph_mcp_agent.py "先执行 boss status，再同步最近消息并生成回复草稿"

By default this example launches the repo-local MCP server via:
    python -m boss_agent_cli.mcp_server
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from _mcp_agent_common import (
	DEFAULT_SYSTEM_PROMPT,
	build_chat_model_kwargs,
	build_repo_local_server_config,
	coerce_message_text,
	extract_last_ai_text,
)


class GraphState(TypedDict):
	messages: list[dict[str, str]]
	final_text: str


def _normalize_messages(messages: list[Any]) -> list[dict[str, str]]:
	normalized: list[dict[str, str]] = []
	for message in messages:
		msg_type = getattr(message, "type", "")
		if msg_type not in {"human", "ai", "system"}:
			continue
		content = coerce_message_text(getattr(message, "text", None) or getattr(message, "content", ""))
		if not content:
			continue
		role = {"human": "user", "ai": "assistant", "system": "system"}[msg_type]
		normalized.append({"role": role, "content": content})
	return normalized


async def build_graph():
	client = MultiServerMCPClient({"boss": build_repo_local_server_config()})
	tools = await client.get_tools()
	agent = create_agent(
		ChatOpenAI(**build_chat_model_kwargs()),
		tools=tools,
		system_prompt=DEFAULT_SYSTEM_PROMPT,
	)

	async def agent_node(state: GraphState) -> dict[str, object]:
		result = await agent.ainvoke({"messages": state["messages"]})
		return {
			"messages": _normalize_messages(result["messages"]),
			"final_text": extract_last_ai_text(result["messages"]),
		}

	workflow = StateGraph(GraphState)
	workflow.add_node("agent", agent_node)
	workflow.add_edge(START, "agent")
	workflow.add_edge("agent", END)
	return workflow.compile(checkpointer=InMemorySaver())


async def main(user_prompt: str) -> None:
	thread_id = os.environ.get("BOSS_LANGGRAPH_THREAD_ID", "boss-agent-demo")
	graph = await build_graph()
	result = await graph.ainvoke(
		{
			"messages": [{"role": "user", "content": user_prompt}],
			"final_text": "",
		},
		config={"configurable": {"thread_id": thread_id}},
	)
	final_text = result.get("final_text", "")
	if final_text:
		print(final_text)


if __name__ == "__main__":
	prompt = sys.argv[1] if len(sys.argv) > 1 else "搜索广州的 Golang 职位，并给出 3 个值得进一步查看的岗位"
	asyncio.run(main(prompt))
