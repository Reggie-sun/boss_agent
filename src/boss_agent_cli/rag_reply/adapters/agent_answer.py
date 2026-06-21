"""Agent-side answer composer for grounded RAG replies."""

from __future__ import annotations

import json
import re
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

DIRECT_AGENT_PROMPT = """你是一个中文通用问答助手，正在为本地前端测试生成直接回答。

## 用户问题
{message_text}

## 问题意图
{intent}

## 岗位摘要
{job_summary}

## 约束
1. 直接回答用户问题，不要说“根据知识库 / 根据资料 / RAG 显示”。
2. 如果问题是通用知识、技术概念或闲聊，按通用 LLM 问答方式回答。
3. 如果问题涉及候选人的个人经历、薪资、联系方式、面试安排、到岗时间等敏感或缺少上下文的信息，不要编造；可以说明需要候选人本人确认或补充信息。
4. 输出中文，回答自然、简洁、可继续追问。
5. 不要输出 Markdown 标题、代码块或多版本候选答案。

## 输出要求
只返回 JSON，不要包含其他内容：
```json
{{
  "answer_text": "最终回答正文",
  "strategy": "一句话说明本次回答策略"
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

	def __init__(self, *, ai_service: AIService | None) -> None:
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
		if not (rag_answer or "").strip() or self._is_ungrounded_answer(rag_answer):
			return self._direct_answer(
				message_text=message_text,
				intent=intent,
				job_summary=job_summary,
			)
		if self.ai_service is None:
			return self._rule_based_rewrite(message_text=message_text, rag_answer=rag_answer)
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
		except (AIServiceError, ValueError):
			return self._rule_based_rewrite(message_text=message_text, rag_answer=rag_answer)
		answer_text = str(payload.get("answer_text") or "").strip()
		if not answer_text:
			return self._rule_based_rewrite(message_text=message_text, rag_answer=rag_answer)
		return AgentAnswerResult(
			ok=True,
			answer=answer_text,
			citations=list(citations or []),
			reasoning_summary={"strategy": str(payload.get("strategy") or "").strip()},
			raw_response=payload,
		)

	def _direct_answer(
		self,
		*,
		message_text: str,
		intent: str,
		job_summary: str | None,
	) -> AgentAnswerResult:
		if self.ai_service is None:
			recruiter_invitation_answer = self._recruiter_invitation_answer(message_text)
			if recruiter_invitation_answer:
				return AgentAnswerResult(
					ok=True,
					answer=recruiter_invitation_answer,
					reasoning_summary={"strategy": "在无可用 AI 服务时，命中本地招聘邀约回复模板"},
					raw_response={"mode": "local_recruiter_invitation_template"},
				)
			return self._profile_required_result()
		prompt = DIRECT_AGENT_PROMPT.format(
			message_text=message_text or "（空）",
			intent=intent or "unknown",
			job_summary=job_summary or "（无）",
		)
		try:
			raw = self.ai_service.chat(
				[
					{"role": "system", "content": "你是中文通用问答助手。所有输出使用 JSON 格式。"},
					{"role": "user", "content": prompt},
				]
			)
			payload = self._parse_json_response(raw)
		except (AIServiceError, ValueError):
			recruiter_invitation_answer = self._recruiter_invitation_answer(message_text)
			if recruiter_invitation_answer:
				return AgentAnswerResult(
					ok=True,
					answer=recruiter_invitation_answer,
					reasoning_summary={"strategy": "在无可用 AI 服务时，命中本地招聘邀约回复模板"},
					raw_response={"mode": "local_recruiter_invitation_template"},
				)
			return self._profile_required_result()
		answer_text = str(payload.get("answer_text") or "").strip()
		if not answer_text:
			return self._profile_required_result()
		return AgentAnswerResult(
			ok=True,
			answer=answer_text,
			reasoning_summary={"strategy": str(payload.get("strategy") or "").strip()},
			raw_response=payload,
		)

	@staticmethod
	def _rule_based_rewrite(*, message_text: str, rag_answer: str) -> AgentAnswerResult:
		recruiter_invitation_answer = AgentAnswerAdapter._recruiter_invitation_answer(
			message_text
		)
		if recruiter_invitation_answer:
			return AgentAnswerResult(
				ok=True,
				answer=recruiter_invitation_answer,
				reasoning_summary={"strategy": "在无可用 AI 服务时，命中本地招聘邀约回复模板"},
				raw_response={"mode": "local_recruiter_invitation_template"},
			)
		cleaned = AgentAnswerAdapter._clean_markdown(rag_answer)
		cleaned = AgentAnswerAdapter._normalize_candidate_voice(cleaned)
		sentences = AgentAnswerAdapter._extract_sentences(cleaned)
		focused_sentences = AgentAnswerAdapter._filter_sentences_by_question(
			sentences,
			message_text=message_text,
		)
		opening = AgentAnswerAdapter._pick_sentence(
			focused_sentences,
			lambda sentence: "我" in sentence and ("项目" in sentence or "负责" in sentence),
		)
		responsibility = AgentAnswerAdapter._pick_sentence(
			focused_sentences,
			lambda sentence: "负责" in sentence or "覆盖" in sentence,
		)
		background = AgentAnswerAdapter._pick_sentence(
			focused_sentences,
			lambda sentence: "旨在" in sentence or "面向" in sentence or "目标" in sentence,
		)
		outcome = AgentAnswerAdapter._pick_sentence(
			focused_sentences,
			lambda sentence: "实现" in sentence or "构建" in sentence or "形成" in sentence or "落地" in sentence,
		)
		parts: list[str] = []
		for sentence in (opening, background, responsibility, outcome):
			if sentence and sentence not in parts:
				parts.append(sentence)
		if not parts and focused_sentences:
			parts = focused_sentences[:3]
		if not parts and cleaned:
			parts = [cleaned]
		answer = " ".join(parts).strip()
		return AgentAnswerResult(
			ok=bool(answer),
			answer=answer,
			reasoning_summary={"strategy": "在无可用 AI 改写服务时，基于 grounded answer 做本地规则改写"},
			raw_response={"mode": "rule_based"},
			error_message=None if answer else "Agent answer returned empty answer_text.",
			audit_status="draft_created" if answer else "agent_answer_failed",
		)

	@staticmethod
	def _profile_required_result() -> AgentAnswerResult:
		return AgentAnswerResult(
			ok=False,
			answer="",
			reasoning_summary={"strategy": "profile_grounding_required"},
			raw_response={"mode": "profile_required"},
			error_message="Personal candidate answers require bound profile RAG grounding.",
			audit_status="agent_answer_failed",
		)

	@staticmethod
	def _recruiter_invitation_answer(message_text: str) -> str:
		lower_question = (message_text or "").lower()
		invitation_tokens = (
			"招聘",
			"急招",
			"诚聘",
			"招贤",
			"纳士",
			"岗位",
			"职位",
			"工作机会",
			"新的机会",
			"看工作",
			"在看机会",
		)
		engagement_tokens = (
			"沟通",
			"聊",
			"兴趣",
			"考虑",
			"有时间",
			"方便",
			"机会",
		)
		if not any(token in lower_question for token in invitation_tokens):
			return ""
		if not any(token in lower_question for token in engagement_tokens):
			return ""
		return (
			"您好，我对这个岗位比较感兴趣，可以进一步沟通。"
			"也方便请您简单介绍一下岗位职责、技术方向和团队情况。"
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

	@staticmethod
	def _is_ungrounded_answer(text: str) -> bool:
		normalized = " ".join((text or "").split())
		if not normalized:
			return True
		return normalized in {
			"资料未明确覆盖。",
			"资料未明确覆盖",
			"未明确覆盖。",
			"未明确覆盖",
		}

	@staticmethod
	def _clean_markdown(text: str) -> str:
		lines: list[str] = []
		for raw_line in (text or "").splitlines():
			line = raw_line.strip()
			if not line:
				continue
			if line.startswith("```"):
				continue
			line = re.sub(r"^\s*#+\s*", "", line)
			line = re.sub(r"^\s*[-*]\s*", "", line)
			line = re.sub(r"^\s*\d+(?:\.\d+)*\.?\s*", "", line)
			line = line.replace("**", "")
			if line in {"核心结论", "详细解释", "补充说明", "项目背景与目标", "核心技术方案", "项目成果"}:
				continue
			lines.append(line)
		return " ".join(lines)

	@staticmethod
	def _normalize_candidate_voice(text: str) -> str:
		normalized = text or ""
		normalized = re.sub(r"候选人[\u4e00-\u9fff]{2,4}(?=在)", "我", normalized)
		normalized = re.sub(r"候选人[\u4e00-\u9fff]{2,4}(?=[，、：])", "我", normalized)
		normalized = normalized.replace("候选人", "我")
		normalized = normalized.replace("他负责", "我负责")
		normalized = normalized.replace("他在", "我在")
		normalized = normalized.replace("他的职责", "我的职责")
		normalized = normalized.replace("他的优势", "我的优势")
		normalized = re.sub(r"^[\u4e00-\u9fff]{2,4}(?=在)", "我", normalized)
		normalized = normalized.replace("该项目", "这个项目")
		normalized = normalized.replace("其职责", "我的职责")
		return normalized

	@staticmethod
	def _filter_sentences_by_question(sentences: list[str], *, message_text: str) -> list[str]:
		lower_question = (message_text or "").lower()
		if any(keyword in lower_question for keyword in ("适合", "匹配", "胜任")):
			filtered = [
				sentence
				for sentence in sentences
				if not any(token in sentence for token in ("岁", "未婚", "籍贯", "出生", "联系方式"))
			]
			return filtered or sentences
		if any(keyword in lower_question for keyword in ("协作", "产品", "算法", "后端", "跨团队")):
			filtered = [
				sentence
				for sentence in sentences
				if any(token in sentence for token in ("协作", "配合", "联动", "产品", "算法", "后端", "前端", "评测"))
			]
			return filtered or sentences
		if any(keyword in lower_question for keyword in ("最难", "难点", "怎么解决", "如何解决")):
			filtered = [
				sentence
				for sentence in sentences
				if any(token in sentence for token in ("问题", "难点", "挑战", "排查", "解决", "优化", "稳定", "准确"))
			]
			return filtered or sentences
		return [
			sentence
			for sentence in sentences
			if not any(token in sentence for token in ("岁", "未婚", "籍贯", "出生", "联系方式"))
		] or sentences

	@staticmethod
	def _extract_sentences(text: str) -> list[str]:
		segments = re.split(r"(?<=[。！？；])", text)
		return [segment.strip() for segment in segments if segment.strip()]

	@staticmethod
	def _pick_sentence(sentences: list[str], predicate) -> str:
		for sentence in sentences:
			if predicate(sentence):
				return sentence
		return ""
