"""Shared helpers for LangChain / LangGraph MCP agent examples."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_SYSTEM_PROMPT = (
	"你是一个低风险求职辅助 Agent。优先使用 boss schema 做能力发现，"
	"在使用 boss_search / boss_detail / boss_shortlist 之前先确认 boss_status。"
	"如果任务是回复草稿工作流，优先使用 boss_rag_sync_messages、boss_rag_draft、"
	"boss_rag_review、boss_rag_approve。遇到 ok=false 时读取 error.code 和 "
	"error.recovery_action，不要伪造成功。"
)


def build_repo_local_server_config() -> dict[str, object]:
	"""Launch the repo-local MCP server from source."""
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


def build_boss_mcp_server_config() -> dict[str, object]:
	"""Prefer an already-running HTTP MCP server, else launch the repo-local server."""
	http_url = os.environ.get("BOSS_MCP_HTTP_URL")
	if http_url:
		return {
			"transport": "http",
			"url": http_url,
		}
	return build_repo_local_server_config()


def build_chat_model_kwargs() -> dict[str, object]:
	"""Resolve OpenAI-compatible model settings from env."""
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
	return model_kwargs


def coerce_message_text(content: Any) -> str:
	"""Convert LangChain/LangGraph message content into plain text for demos."""
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		parts: list[str] = []
		for item in content:
			if isinstance(item, str):
				parts.append(item)
			elif isinstance(item, dict):
				text = item.get("text")
				if text:
					parts.append(str(text))
		return "\n".join(part for part in parts if part)
	return str(content or "")


def extract_last_ai_text(messages: list[Any]) -> str:
	"""Return the last non-empty AI message text from a message list."""
	for message in reversed(messages):
		if getattr(message, "type", "") != "ai":
			continue
		text = coerce_message_text(getattr(message, "text", None) or getattr(message, "content", ""))
		if text:
			return text
	return ""
