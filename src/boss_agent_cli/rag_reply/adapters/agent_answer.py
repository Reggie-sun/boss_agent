"""Agent-side answer composer for grounded RAG replies."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from boss_agent_cli.ai.service import AIService, AIServiceError


AGENT_ANSWER_PROMPT = """你是一个面试问答 Agent，需要把 grounded RAG answer 整理成候选人本人在面试中会说的最终回答。

## 面试问题
{message_text}

## 问题意图
{intent}

## 岗位摘要
{job_summary}

## Grounded answer
{rag_answer}

## 引用线索
{citation_summary}

## 约束
1. 只基于 grounded answer 和引用线索作答，不要编造未提供的经历或数据。
2. 输出中文，并改写成候选人第一人称口吻。
3. 直接回答问题，不要提“知识库 / grounded / 检索 / 文档显示 / 根据资料”。
4. 如果 grounded answer 是第三人称，必须改写成第一人称。
5. 回答尽量自然、具体、可追问，优先突出“我负责什么、怎么做、结果如何”。
6. 不要输出 Markdown 标题、列表、代码块或多版本候选答案。

## 输出要求
只返回 JSON，不要包含其他内容：
```json
{{
  "answer_text": "最终回答正文",
  "strategy": "一句话说明本次整理策略"
}}
```
"""


@dataclass(slots=True)
class AgentAnswerResult:
	ok: bool
	answer: str
	citations: list[dict[str, Any]] = field(default_factory=list)
	reasoning_summary: dict[str, Any] | None = None
	raw_response: dict[str, Any] | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True


class AgentAnswerAdapter:
	"""Compose a candidate-facing answer from grounded RAG output."""

	def __init__(self, *, ai_service: AIService) -> None:
		self.ai_service = ai_service

	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_answer: str,
		citations: list[dict[str, Any]] | None = None,
	) -> AgentAnswerResult:
		prompt = AGENT_ANSWER_PROMPT.format(
			message_text=message_text or "（空）",
			intent=intent or "unknown",
			job_summary=job_summary or "（无）",
			rag_answer=rag_answer or "（空）",
			citation_summary=self._format_citations(citations or []),
		)
		try:
			raw = self.ai_service.chat(
				[
					{"role": "system", "content": "你是求职面试回答整理助手。所有输出使用 JSON 格式。"},
					{"role": "user", "content": prompt},
				]
			)
			payload = self._parse_json_response(raw)
		except (AIServiceError, ValueError) as exc:
			return AgentAnswerResult(
				ok=False,
				answer="",
				error_message=str(exc),
				audit_status="agent_answer_failed",
			)
		answer_text = str(payload.get("answer_text") or "").strip()
		if not answer_text:
			return AgentAnswerResult(
				ok=False,
				answer="",
				error_message="Agent answer returned empty answer_text.",
				audit_status="agent_answer_failed",
				raw_response=payload,
			)
		return AgentAnswerResult(
			ok=True,
			answer=answer_text,
			citations=list(citations or []),
			reasoning_summary={"strategy": str(payload.get("strategy") or "").strip()},
			raw_response=payload,
		)

	@staticmethod
	def _format_citations(citations: list[dict[str, Any]]) -> str:
		if not citations:
			return "（无）"
		lines: list[str] = []
		for index, citation in enumerate(citations[:4], start=1):
			title = (
				citation.get("title")
				or citation.get("document_name")
				or citation.get("document_title")
				or citation.get("source")
				or citation.get("path")
				or f"引用 {index}"
			)
			snippet = (
				citation.get("snippet")
				or citation.get("quote")
				or citation.get("text")
				or citation.get("excerpt")
				or citation.get("content")
				or ""
			)
			compact_snippet = " ".join(str(snippet).split())
			if len(compact_snippet) > 140:
				compact_snippet = f"{compact_snippet[:140]}..."
			lines.append(f"{index}. {title}: {compact_snippet or '（无片段）'}")
		return "\n".join(lines)

	@staticmethod
	def _parse_json_response(raw: str) -> dict[str, Any]:
		text = (raw or "").strip()
		if text.startswith("```"):
			lines = [line for line in text.splitlines() if not line.lstrip().startswith("```")]
			text = "\n".join(lines).strip()
		try:
			payload = json.loads(text)
		except json.JSONDecodeError as exc:
			raise ValueError("Agent answer returned non-JSON content.") from exc
		if not isinstance(payload, dict):
			raise ValueError("Agent answer JSON payload must be an object.")
		return payload
