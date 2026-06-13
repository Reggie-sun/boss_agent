"""Minimal LangChain MCP agent for boss-agent-cli.

Run from the repo root:

    pip install -e ".[langchain]"
    export BOSS_LANGCHAIN_API_KEY=...
    export BOSS_LANGCHAIN_MODEL=gpt-5
    export BOSS_MCP_HTTP_URL=http://127.0.0.1:8766/mcp
    python examples/langchain_mcp_agent.py "先同步消息，再为最近一条对话生成回复草稿"

If BOSS_MCP_HTTP_URL is unset, this example launches the repo-local MCP server via:
    python -m boss_agent_cli.mcp_server
"""

from __future__ import annotations

import asyncio
import sys

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from _mcp_agent_common import (
	DEFAULT_SYSTEM_PROMPT,
	build_boss_mcp_server_config,
	build_chat_model_kwargs,
	extract_last_ai_text,
)


async def main(user_prompt: str) -> None:
	client = MultiServerMCPClient({"boss": build_boss_mcp_server_config()})
	tools = await client.get_tools()
	agent = create_agent(
		ChatOpenAI(**build_chat_model_kwargs()),
		tools=tools,
		system_prompt=DEFAULT_SYSTEM_PROMPT,
	)

	result = await agent.ainvoke(
		{"messages": [{"role": "user", "content": user_prompt}]}
	)
	final_text = extract_last_ai_text(result["messages"])
	if final_text:
		print(final_text)


if __name__ == "__main__":
	prompt = sys.argv[1] if len(sys.argv) > 1 else "搜索广州的 Golang 职位，并给出 3 个值得进一步查看的岗位"
	asyncio.run(main(prompt))
