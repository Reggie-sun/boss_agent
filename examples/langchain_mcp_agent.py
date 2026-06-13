"""Minimal LangChain MCP agent for boss-agent-cli.

Run from the repo root:

    pip install langchain langchain-openai langchain-mcp-adapters
    export OPENAI_API_KEY=...
    export BOSS_LANGCHAIN_MODEL=gpt-5
    python examples/langchain_mcp_agent.py "先同步消息，再为最近一条对话生成回复草稿"

By default this example launches the repo-local MCP server via:
    python -m boss_agent_cli.mcp_server
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_SYSTEM_PROMPT = (
	"你是一个低风险求职辅助 Agent。优先使用 boss schema 做能力发现，"
	"在使用 boss_search / boss_detail / boss_shortlist 之前先确认 boss_status。"
	"如果任务是回复草稿工作流，优先使用 boss_rag_sync_messages、boss_rag_draft、"
	"boss_rag_review、boss_rag_approve。遇到 ok=false 时读取 error.code 和 "
	"error.recovery_action，不要伪造成功。"
)


def _build_repo_local_server_config() -> dict[str, object]:
	server_env = dict(os.environ)
	existing_pythonpath = server_env.get("PYTHONPATH")
	server_env["PYTHONPATH"] = (
		f"{SRC_ROOT}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(SRC_ROOT)
	)

	command = os.environ.get("BOSS_MCP_COMMAND", sys.executable)
	args = shlex.split(os.environ.get("BOSS_MCP_ARGS", "-m boss_agent_cli.mcp_server"))
	return {
		"transport": "stdio",
		"command": command,
		"args": args,
		"cwd": str(REPO_ROOT),
		"env": server_env,
	}


async def main(user_prompt: str) -> None:
	model_name = os.environ.get("BOSS_LANGCHAIN_MODEL")
	if not model_name:
		raise SystemExit("Missing BOSS_LANGCHAIN_MODEL, for example: export BOSS_LANGCHAIN_MODEL=gpt-5")
	api_key = os.environ.get("BOSS_LANGCHAIN_API_KEY") or os.environ.get("OPENAI_API_KEY")
	base_url = os.environ.get("BOSS_LANGCHAIN_BASE_URL") or os.environ.get("OPENAI_BASE_URL")

	model_kwargs: dict[str, object] = {"model": model_name}
	if api_key:
		model_kwargs["api_key"] = api_key
	if base_url:
		model_kwargs["base_url"] = base_url

	client = MultiServerMCPClient({"boss": _build_repo_local_server_config()})
	tools = await client.get_tools()
	agent = create_agent(
		ChatOpenAI(**model_kwargs),
		tools=tools,
		system_prompt=DEFAULT_SYSTEM_PROMPT,
	)

	result = await agent.ainvoke(
		{"messages": [{"role": "user", "content": user_prompt}]}
	)
	for message in result["messages"]:
		if getattr(message, "type", "") == "ai":
			content = getattr(message, "text", None) or getattr(message, "content", "")
			if content:
				print(content)


if __name__ == "__main__":
	prompt = sys.argv[1] if len(sys.argv) > 1 else "搜索广州的 Golang 职位，并给出 3 个值得进一步查看的岗位"
	asyncio.run(main(prompt))
