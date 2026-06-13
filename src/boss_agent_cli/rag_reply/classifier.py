"""Rule-first message classification for the Boss RAG workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass

INTENTS = {
	"project_question",
	"resume_question",
	"salary_or_offer",
	"resume_share_request",
	"availability_or_schedule",
	"personal_status",
	"interview_time",
	"resignation_status",
	"job_detail_question",
	"smalltalk",
	"contact_exchange",
	"unsafe_or_unclear",
}

SENSITIVE_INTENTS = {
	"salary_or_offer",
	"resume_share_request",
	"availability_or_schedule",
	"personal_status",
	"interview_time",
	"resignation_status",
	"contact_exchange",
	"unsafe_or_unclear",
}

SENSITIVE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
	("salary_or_offer", (r"薪资", r"工资", r"薪酬", r"offer", r"待遇")),
	("resume_share_request", (r"发.*简历", r"简历.*发", r"附件简历", r"一份简历", r"简历过来", r"把简历.*发")),
	("contact_exchange", (r"微信", r"\bvx\b", r"联系方式", r"手机号", r"电话", r"邮箱", r"加我")),
	("interview_time", (r"面试", r"几点", r"哪天", r"约.*面", r"时间面")),
	("availability_or_schedule", (r"方便", r"有空", r"可约", r"什么时候方便", r"时间安排")),
	("resignation_status", (r"离职", r"离岗", r"离职时间", r"什么时候离")),
	("personal_status", (r"在职", r"目前状态", r"当前状态", r"现在还在职", r"是否在职")),
)

PROJECT_PATTERNS = (r"rag", r"项目", r"做了什么", r"具体做了什么", r"介绍一下")
RESUME_PATTERNS = (r"fastapi", r"会.*吗", r"熟悉", r"技术栈", r"经验")
JOB_DETAIL_PATTERNS = (r"岗位", r"你对我们岗位", r"有什么想问", r"还有什么问题")
SMALLTALK_PATTERNS = (r"你好", r"您好", r"收到", r"好的", r"谢谢", r"辛苦", r"在吗")


@dataclass(slots=True)
class ClassificationResult:
	intent: str
	risk_labels: list[str]
	classifier_source: str

	@property
	def requires_rag(self) -> bool:
		return self.intent in {"project_question", "resume_question"}


def classify_message(message_text: str) -> ClassificationResult:
	"""Classify a recruiter message using rule-first sensitive detection."""
	text = (message_text or "").strip()
	lower_text = text.lower()
	for intent, patterns in SENSITIVE_RULES:
		if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in patterns):
			return ClassificationResult(
				intent=intent,
				risk_labels=["human_approval_required", "sensitive_intent", intent],
				classifier_source="rules",
			)
	if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in PROJECT_PATTERNS):
		return ClassificationResult(
			intent="project_question",
			risk_labels=[],
			classifier_source="heuristic",
		)
	if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in RESUME_PATTERNS):
		return ClassificationResult(
			intent="resume_question",
			risk_labels=[],
			classifier_source="heuristic",
		)
	if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in JOB_DETAIL_PATTERNS):
		return ClassificationResult(
			intent="job_detail_question",
			risk_labels=["human_approval_required"],
			classifier_source="heuristic",
		)
	if any(re.search(pattern, lower_text, flags=re.IGNORECASE) for pattern in SMALLTALK_PATTERNS):
		return ClassificationResult(
			intent="smalltalk",
			risk_labels=[],
			classifier_source="heuristic",
		)
	return ClassificationResult(
		intent="unsafe_or_unclear",
		risk_labels=["human_approval_required", "sensitive_intent", "unsafe_or_unclear"],
		classifier_source="fallback",
	)
