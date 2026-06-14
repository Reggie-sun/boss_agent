"""AI fallback adapter for the Boss RAG reply workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from boss_agent_cli.ai.service import AIService, AIServiceError


AI_FALLBACK_PROMPT = """你是一个低风险求职沟通助手。

主 RAG 服务当前不可用，请基于下面的信息生成一个保守、真实、可人工审核的中文回复草稿。

## 消息意图
{intent}

## 招聘者消息
{message_text}

## 职位摘要
{job_summary}

## 主路径失败原因
{rag_error}

## 约束
1. 只输出一条候选回复，不要输出多版本。
2. 回复长度控制在 30 到 100 个中文字符。
3. 不要承诺薪资、入职时间、面试时间、联系方式等敏感事项。
4. 如果信息不足，优先使用“可以进一步展开/欢迎补充关注点”这类保守表达。
5. 不要编造候选人未提供的经历细节。

## 输出要求
只返回 JSON，不要包含其他内容：
```json
{{
  "reply_text": "候选回复正文",
  "strategy": "一句话说明采用的保守回复策略"
}}
```
"""


@dataclass(slots=True)
class AIFallbackAnswerResult:
	ok: bool
	answer: str
	citations: list[dict[str, Any]] = field(default_factory=list)
	reasoning_summary: dict[str, Any] | None = None
	raw_response: dict[str, Any] | None = None
	error_message: str | None = None
	audit_status: str = "draft_created"
	send_allowed: bool = False
	approval_required: bool = True


class AIFallbackAdapter:
	"""Generate a conservative draft when the primary RAG path fails."""

	def __init__(self, *, ai_service: AIService) -> None:
		self.ai_service = ai_service

	def answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
		rag_error: str | None,
	) -> AIFallbackAnswerResult:
		prompt = AI_FALLBACK_PROMPT.format(
			intent=intent,
			message_text=message_text or "（空）",
			job_summary=job_summary or "（无）",
			rag_error=rag_error or "（未提供）",
		)
		try:
			raw = self.ai_service.chat(
				[
					{"role": "system", "content": "你是求职沟通助手。所有输出使用 JSON 格式。"},
					{"role": "user", "content": prompt},
				]
			)
			payload = self._parse_json_response(raw)
		except (AIServiceError, ValueError) as exc:
			return AIFallbackAnswerResult(
				ok=False,
				answer="",
				error_message=str(exc),
				audit_status="ai_fallback_failed",
			)
		reply_text = str(payload.get("reply_text") or "").strip()
		if not reply_text:
			return AIFallbackAnswerResult(
				ok=False,
				answer="",
				error_message="AI fallback returned empty reply_text.",
				audit_status="ai_fallback_failed",
				raw_response=payload,
			)
		return AIFallbackAnswerResult(
			ok=True,
			answer=reply_text,
			reasoning_summary={"strategy": str(payload.get("strategy") or "").strip()},
			raw_response=payload,
		)

	@staticmethod
	def _parse_json_response(raw: str) -> dict[str, Any]:
		text = (raw or "").strip()
		if text.startswith("```"):
			lines = [line for line in text.splitlines() if not line.lstrip().startswith("```")]
			text = "\n".join(lines).strip()
		try:
			payload = json.loads(text)
		except json.JSONDecodeError as exc:
			raise ValueError("AI fallback returned non-JSON content.") from exc
		if not isinstance(payload, dict):
			raise ValueError("AI fallback JSON payload must be an object.")
		return payload
