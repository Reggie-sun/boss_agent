"""Build minimal-context questions for Enterprise RAG."""

from __future__ import annotations


def build_answer_objective(intent: str, message_text: str = "") -> str:
	"""Return the answer objective for the given intent."""
	lower_text = (message_text or "").lower()
	if intent == "project_question":
		if any(keyword in lower_text for keyword in ("最难", "难点", "怎么解决", "如何解决")):
			return "优先回答我遇到的具体难点、排查过程、解决方案和最终效果。"
		if any(keyword in lower_text for keyword in ("怎么设计", "如何设计", "检索", "重排", "引用溯源", "召回")):
			return "优先回答系统架构、检索与重排设计、引用溯源方案，以及关键取舍。"
		if any(keyword in lower_text for keyword in ("协作", "产品", "算法", "后端", "跨团队")):
			return "优先回答我和产品、算法、后端的协作方式、分工和推进结果。"
		return "优先回答我负责什么、核心技术方案是什么，以及最终结果如何。"
	if intent == "resume_question":
		if any(keyword in lower_text for keyword in ("适合", "匹配", "胜任")):
			return "优先回答我的相关经验、核心优势，以及我为什么适合这个岗位。"
		return "优先回答我的相关经验、技术栈和可落地能力。"
	return "请直接回答问题，并保持候选人本人沟通口吻。"


def build_rag_question(
	hr_question: str,
	job_summary: str | None,
	objective: str,
) -> str:
	"""Build the RAG question without leaking full Boss platform context."""
	parts = [
		"请直接回答下面这位 HR 的问题，答案用于候选人面试交流。",
		f"问题：{hr_question.strip()}",
		f"回答要求：{objective.strip()}",
		"约束：只基于候选人的真实项目经历和已有材料作答，不要编造；回答尽量自然、具体、可追问。",
	]
	if job_summary:
		parts.append(f"岗位摘要：{job_summary.strip()}")
	return "\n".join(parts)
