"""Build minimal-context questions for Enterprise RAG."""

from __future__ import annotations


def build_answer_objective(intent: str) -> str:
	"""Return the answer objective for the given intent."""
	if intent == "project_question":
		return "Draft a concise recruiter-facing answer about the candidate project."
	if intent == "resume_question":
		return "Draft a concise recruiter-facing answer about the candidate skills and experience."
	return "Draft a concise recruiter-facing answer."


def build_rag_question(
	hr_question: str,
	job_summary: str | None,
	objective: str,
) -> str:
	"""Build the RAG question without leaking full Boss platform context."""
	parts = [
		f"HR question: {hr_question.strip()}",
		f"Answer objective: {objective.strip()}",
	]
	if job_summary:
		parts.append(f"Short job summary: {job_summary.strip()}")
	return "\n".join(parts)
