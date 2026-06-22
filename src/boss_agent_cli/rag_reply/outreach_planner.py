"""Pure decision planner for Boss outreach candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


LOW_MATCH_THRESHOLD = 40
_AI_INDUSTRY_TERMS = ("人工智能", "ai", "llm", "大模型", "机器学习", "智能")


@dataclass(slots=True)
class OutreachCandidate:
    security_id: str
    job_id: str
    title: str = ""
    company: str = ""
    salary: str = ""
    city: str = ""
    experience: str = ""
    education: str = ""
    industry: str = ""
    skills: list[str] | None = None
    boss_name: str = ""
    boss_title: str = ""
    greeted: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OutreachCandidate":
        return cls(
            security_id=_string_value(value, "security_id", "securityId"),
            job_id=_string_value(value, "job_id", "jobId", "encryptJobId"),
            title=_string_value(value, "title", "jobName"),
            company=_string_value(value, "company", "brandName"),
            salary=_string_value(value, "salary", "salaryDesc"),
            city=_string_value(value, "city", "cityName"),
            experience=_string_value(value, "experience", "jobExperience"),
            education=_string_value(value, "education", "jobDegree"),
            industry=_string_value(value, "industry", "brandIndustry"),
            skills=_skills_value(value.get("skills")),
            boss_name=_string_value(value, "boss_name", "bossName"),
            boss_title=_string_value(value, "boss_title", "bossTitle"),
            greeted=_bool_value(value.get("greeted", False)),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "security_id": self.security_id,
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "salary": self.salary,
            "city": self.city,
            "experience": self.experience,
            "education": self.education,
            "industry": self.industry,
            "skills": list(self.skills or []),
            "boss_name": self.boss_name,
            "boss_title": self.boss_title,
            "greeted": self.greeted,
        }


@dataclass(slots=True)
class OutreachPlannerConfig:
    query: str
    target_title: str
    profile_id: str
    profile_outreach_enabled: bool = False
    live_execution_requested: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "target_title": self.target_title,
            "profile_id": self.profile_id,
            "profile_outreach_enabled": self.profile_outreach_enabled,
            "live_execution_requested": self.live_execution_requested,
        }


@dataclass(slots=True)
class OutreachDecision:
    candidate: OutreachCandidate
    decision: str
    risk: str
    reasons: list[str]
    score: int
    proposed_cli_args: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_payload(),
            "decision": self.decision,
            "risk": self.risk,
            "reasons": list(self.reasons),
            "score": self.score,
            "proposed_cli_args": list(self.proposed_cli_args),
        }


@dataclass(slots=True)
class OutreachPlan:
    status: str
    total: int
    send_ready: bool
    actions: list[OutreachDecision]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total": self.total,
            "send_ready": self.send_ready,
            "actions": [action.to_payload() for action in self.actions],
        }


class OutreachPlanner:
    def __init__(self, config: OutreachPlannerConfig):
        self.config = config

    def build_plan(
        self,
        candidates: Sequence[OutreachCandidate],
        *,
        attachments: Sequence[str],
    ) -> OutreachPlan:
        if (
            self.config.live_execution_requested
            and not self.config.profile_outreach_enabled
        ):
            actions = [
                self._blocked_decision(candidate, "profile_outreach_disabled")
                for candidate in candidates
            ]
            return OutreachPlan(
                status="blocked_profile_gate",
                total=len(candidates),
                send_ready=False,
                actions=actions,
            )

        actions = [self._decision_for(candidate, attachments) for candidate in candidates]
        send_ready = any(
            action.decision in {"greet_only", "greet_with_attachments"}
            for action in actions
        )
        return OutreachPlan(
            status="planned",
            total=len(candidates),
            send_ready=send_ready,
            actions=actions,
        )

    def _decision_for(
        self, candidate: OutreachCandidate, attachments: Sequence[str]
    ) -> OutreachDecision:
        score, reasons = self._score(candidate)
        if candidate.greeted:
            return OutreachDecision(
                candidate=candidate,
                decision="skip",
                risk="none",
                reasons=["already_greeted"],
                score=score,
                proposed_cli_args=[],
            )
        if score < LOW_MATCH_THRESHOLD:
            return OutreachDecision(
                candidate=candidate,
                decision="skip",
                risk="none",
                reasons=[*reasons, "low_match_score"],
                score=score,
                proposed_cli_args=[],
            )
        if attachments:
            decision = "greet_with_attachments"
            reasons = [*reasons, "has_attachments"]
        else:
            decision = "greet_only"
        return OutreachDecision(
            candidate=candidate,
            decision=decision,
            risk="low",
            reasons=reasons,
            score=score,
            proposed_cli_args=self._proposed_cli_args(candidate, attachments),
        )

    def _blocked_decision(
        self, candidate: OutreachCandidate, reason: str
    ) -> OutreachDecision:
        score, reasons = self._score(candidate)
        return OutreachDecision(
            candidate=candidate,
            decision="blocked_manual_required",
            risk="blocked",
            reasons=[*reasons, reason],
            score=score,
            proposed_cli_args=[],
        )

    def _score(self, candidate: OutreachCandidate) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        title = _normalise(candidate.title)
        query = _normalise(self.config.query)
        target_terms = set(_tokens(self.config.target_title))
        title_terms = set(_tokens(candidate.title))
        skills_text = _normalise(" ".join(candidate.skills or []))

        if query and query in title:
            score += 30
            reasons.append("title_match")
            reasons.append("query_match")
        elif target_terms & title_terms:
            score += 30
            reasons.append("title_match")

        if query and query in skills_text:
            score += 25
            reasons.append("skill_match")
        elif target_terms and any(term in skills_text for term in target_terms):
            score += 20
            reasons.append("skill_match")

        industry = _normalise(candidate.industry)
        if industry and any(term in industry for term in _AI_INDUSTRY_TERMS):
            score += 20
            reasons.append("industry_match")

        return min(score, 100), _unique(reasons)

    def _proposed_cli_args(
        self, candidate: OutreachCandidate, attachments: Sequence[str]
    ) -> list[str]:
        args = ["batch-greet", self.config.query, "--count", "1"]
        if candidate.city:
            args.extend(["--city", candidate.city])
        for attachment in attachments:
            args.extend(["--attachment", str(attachment)])
        return args


def _string_value(value: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        if key in value and value[key] is not None:
            return str(value[key])
    return ""


def _skills_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalise(value: str) -> str:
    return value.casefold().strip()


def _tokens(value: str) -> list[str]:
    return re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+", _normalise(value))


def _unique(values: Sequence[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
