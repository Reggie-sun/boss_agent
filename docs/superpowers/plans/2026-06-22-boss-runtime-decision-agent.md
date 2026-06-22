# Boss Runtime Decision Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加一个窄范围的 Boss outreach 决策 Agent，让系统先观察候选、解释决策、输出 proposed actions，再由现有 guarded tools 执行真实平台动作。

**Architecture:** 新增 `OutreachPlanner` 作为纯 Python 决策层，只接收已抓取候选、profile gate 和附件状态，输出结构化 `OutreachPlan`，不直接调用 BOSS 写接口。CLI 新增 `boss agent plan-outreach`，Vite bridge 新增只读 endpoint，前端在 Boss 自动开聊区展示 Agent plan 和每个候选的 decision/reason。真实发送仍走现有 `batch-greet`、附件发送、watcher guarded tools 和 CDP/Bridge fail-closed gate。

**Tech Stack:** Python dataclasses, Click CLI, existing `run_search_pipeline`, `RagReplyStore` audit log, Vite bridge, React, pytest contract tests.

---

## Scope

本计划只做“决策 Agent 层”，不重写执行层。

包含：
- 新增本地 outreach planning domain model。
- 新增 `boss agent plan-outreach` 只读命令。
- 新增 `/api/agent/outreach-plan` bridge endpoint。
- 前端 Boss 自动开聊区增加 “生成 Agent 计划” 按钮和 plan cards。
- 记录本地 audit，方便回答“Agent 为什么这么做”。

不包含：
- 不让 LLM 直接调用 live send。
- 不修改 `batch-greet` 的真实发送逻辑。
- 不新增批量平台写操作。
- 不引入新的长期 autonomous daemon。

## File Structure

- Create: `src/boss_agent_cli/rag_reply/outreach_planner.py`
  - 纯决策层。负责候选归一化、匹配评分、decision/reason 生成、proposed CLI args 生成。
- Create: `tests/test_outreach_planner.py`
  - 覆盖 planner 的核心行为，不碰 live BOSS。
- Modify: `src/boss_agent_cli/commands/rag.py`
  - 新增 `agent plan-outreach` 命令，调用 search pipeline 后交给 planner。
  - 记录 `outreach_plan` audit log。
- Modify: `tests/test_rag_reply_commands.py`
  - 覆盖 CLI JSON envelope、profile gate、不会发送真实 greet。
- Modify: `demo/interview-simulator/vite.config.mjs`
  - 新增 `/api/agent/outreach-plan` endpoint，转发到 `boss agent plan-outreach`。
- Modify: `tests/test_interview_simulator_contract.py`
  - 覆盖 bridge route 和前端 wiring 字符串契约。
- Modify: `demo/interview-simulator/src/App.jsx`
  - 增加 `bossAgentPlan` state 和 `handleBossAgentPlan`。
- Modify: `demo/interview-simulator/src/views/OutreachWorkspace.jsx`
  - 增加计划按钮和 plan card 渲染。
- Modify: `demo/interview-simulator/src/styles.css`
  - 增加 plan panel 样式。
- Modify: `README.md`
  - 增加 Boss Agent decision layer 的边界说明。

---

### Task 1: Core Outreach Planner

**Files:**
- Create: `src/boss_agent_cli/rag_reply/outreach_planner.py`
- Create: `tests/test_outreach_planner.py`

- [ ] **Step 1: Write failing planner tests**

Create `tests/test_outreach_planner.py` with:

```python
from boss_agent_cli.rag_reply.outreach_planner import (
    OutreachCandidate,
    OutreachPlanner,
    OutreachPlannerConfig,
)


def _candidate(**overrides):
    base = {
        "security_id": "sec_001",
        "job_id": "job_001",
        "title": "RAG Agent 工程师",
        "company": "光昱智能",
        "salary": "12-24K",
        "city": "杭州",
        "experience": "1年以内",
        "education": "本科",
        "industry": "人工智能",
        "skills": ["RAG", "LLM", "Python"],
        "boss_name": "",
        "boss_title": "招聘经理",
        "greeted": False,
    }
    base.update(overrides)
    return OutreachCandidate.from_mapping(base)


def test_outreach_planner_recommends_greet_with_attachments_for_relevant_candidate():
    planner = OutreachPlanner(
        OutreachPlannerConfig(
            query="RAG",
            target_title="AI Agent 工程师",
            profile_id="profile_001",
            profile_outreach_enabled=True,
            live_execution_requested=True,
        )
    )

    plan = planner.build_plan(
        [_candidate()],
        attachments=["/tmp/proof-1.png", "/tmp/proof-2.png"],
    )

    assert plan.status == "planned"
    assert plan.total == 1
    assert plan.send_ready is True
    assert plan.actions[0].decision == "greet_with_attachments"
    assert plan.actions[0].risk == "low"
    assert "title_match" in plan.actions[0].reasons
    assert "has_attachments" in plan.actions[0].reasons
    assert plan.actions[0].proposed_cli_args[:2] == ["batch-greet", "RAG"]
    assert "--attachment" in plan.actions[0].proposed_cli_args


def test_outreach_planner_skips_already_greeted_candidate_with_reason():
    planner = OutreachPlanner(
        OutreachPlannerConfig(
            query="RAG",
            target_title="AI Agent 工程师",
            profile_id="profile_001",
            profile_outreach_enabled=True,
            live_execution_requested=True,
        )
    )

    plan = planner.build_plan([_candidate(greeted=True)], attachments=[])

    assert plan.status == "planned"
    assert plan.send_ready is False
    assert plan.actions[0].decision == "skip"
    assert plan.actions[0].risk == "none"
    assert "already_greeted" in plan.actions[0].reasons


def test_outreach_planner_blocks_live_plan_when_profile_gate_disabled():
    planner = OutreachPlanner(
        OutreachPlannerConfig(
            query="RAG",
            target_title="AI Agent 工程师",
            profile_id="profile_001",
            profile_outreach_enabled=False,
            live_execution_requested=True,
        )
    )

    plan = planner.build_plan([_candidate()], attachments=["/tmp/proof.png"])

    assert plan.status == "blocked_profile_gate"
    assert plan.send_ready is False
    assert plan.actions[0].decision == "blocked_manual_required"
    assert "profile_outreach_disabled" in plan.actions[0].reasons


def test_outreach_planner_skips_low_match_candidate():
    planner = OutreachPlanner(
        OutreachPlannerConfig(
            query="RAG",
            target_title="AI Agent 工程师",
            profile_id="profile_001",
            profile_outreach_enabled=True,
            live_execution_requested=True,
        )
    )

    plan = planner.build_plan(
        [
            _candidate(
                title="行政助理",
                industry="房地产",
                skills=["Excel"],
            )
        ],
        attachments=[],
    )

    assert plan.actions[0].decision == "skip"
    assert plan.actions[0].score < 40
    assert "low_match_score" in plan.actions[0].reasons
```

- [ ] **Step 2: Run planner tests and verify they fail**

Run:

```bash
pytest tests/test_outreach_planner.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'boss_agent_cli.rag_reply.outreach_planner'
```

- [ ] **Step 3: Create planner implementation**

Create `src/boss_agent_cli/rag_reply/outreach_planner.py`:

```python
"""Read-only decision planner for Boss outreach candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


LOW_MATCH_THRESHOLD = 40


@dataclass(slots=True)
class OutreachCandidate:
    security_id: str
    job_id: str
    title: str
    company: str
    salary: str = ""
    city: str = ""
    experience: str = ""
    education: str = ""
    industry: str = ""
    skills: list[str] = field(default_factory=list)
    boss_name: str = ""
    boss_title: str = ""
    greeted: bool = False

    @classmethod
    def from_mapping(cls, item: dict[str, Any]) -> "OutreachCandidate":
        return cls(
            security_id=str(item.get("security_id") or item.get("securityId") or ""),
            job_id=str(item.get("job_id") or item.get("jobId") or item.get("encryptJobId") or ""),
            title=str(item.get("title") or item.get("jobName") or ""),
            company=str(item.get("company") or item.get("brandName") or ""),
            salary=str(item.get("salary") or item.get("salaryDesc") or ""),
            city=str(item.get("city") or item.get("cityName") or ""),
            experience=str(item.get("experience") or item.get("jobExperience") or ""),
            education=str(item.get("education") or item.get("jobDegree") or ""),
            industry=str(item.get("industry") or item.get("brandIndustry") or ""),
            skills=[str(skill) for skill in item.get("skills") or [] if str(skill).strip()],
            boss_name=str(item.get("boss_name") or item.get("bossName") or ""),
            boss_title=str(item.get("boss_title") or item.get("bossTitle") or ""),
            greeted=bool(item.get("greeted")),
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutreachPlannerConfig:
    query: str
    target_title: str = ""
    profile_id: str = ""
    profile_outreach_enabled: bool = False
    live_execution_requested: bool = False
    count: int = 5


@dataclass(slots=True)
class OutreachDecision:
    candidate: dict[str, Any]
    decision: str
    score: int
    risk: str
    reasons: list[str]
    proposed_cli_args: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutreachPlan:
    status: str
    query: str
    profile_id: str
    total: int
    send_ready: bool
    actions: list[OutreachDecision]
    blocked_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "query": self.query,
            "profile_id": self.profile_id,
            "total": self.total,
            "send_ready": self.send_ready,
            "blocked_reason": self.blocked_reason,
            "actions": [action.to_payload() for action in self.actions],
        }


class OutreachPlanner:
    """Build explainable proposed actions without performing live Boss writes."""

    def __init__(self, config: OutreachPlannerConfig) -> None:
        self.config = config

    def build_plan(
        self,
        candidates: list[OutreachCandidate],
        *,
        attachments: list[str],
    ) -> OutreachPlan:
        actions = [self._decision_for(candidate, attachments=attachments) for candidate in candidates]
        blocked_reason = ""
        if self.config.live_execution_requested and not self.config.profile_outreach_enabled:
            blocked_reason = "profile_outreach_disabled"
        actionable = [
            action
            for action in actions
            if action.decision in {"greet_only", "greet_with_attachments"}
        ]
        status = "blocked_profile_gate" if blocked_reason else "planned"
        return OutreachPlan(
            status=status,
            query=self.config.query,
            profile_id=self.config.profile_id,
            total=len(candidates),
            send_ready=bool(actionable) and not blocked_reason,
            actions=actions,
            blocked_reason=blocked_reason,
        )

    def _decision_for(self, candidate: OutreachCandidate, *, attachments: list[str]) -> OutreachDecision:
        score, reasons = self._score(candidate)
        if candidate.greeted:
            return OutreachDecision(
                candidate=candidate.to_payload(),
                decision="skip",
                score=score,
                risk="none",
                reasons=["already_greeted"],
            )
        if self.config.live_execution_requested and not self.config.profile_outreach_enabled:
            return OutreachDecision(
                candidate=candidate.to_payload(),
                decision="blocked_manual_required",
                score=score,
                risk="medium",
                reasons=["profile_outreach_disabled"],
            )
        if score < LOW_MATCH_THRESHOLD:
            return OutreachDecision(
                candidate=candidate.to_payload(),
                decision="skip",
                score=score,
                risk="none",
                reasons=[*reasons, "low_match_score"],
            )
        decision = "greet_with_attachments" if attachments else "greet_only"
        return OutreachDecision(
            candidate=candidate.to_payload(),
            decision=decision,
            score=score,
            risk="low",
            reasons=[*reasons, "has_attachments"] if attachments else reasons,
            proposed_cli_args=self._proposed_cli_args(candidate, attachments),
        )

    def _score(self, candidate: OutreachCandidate) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        title_text = _norm(candidate.title)
        query_text = _norm(self.config.query)
        target_title = _norm(self.config.target_title)
        skill_text = _norm(" ".join(candidate.skills))
        industry_text = _norm(candidate.industry)

        if query_text and query_text in title_text:
            score += 35
            reasons.append("query_title_match")
        if target_title and any(token in title_text for token in _tokens(target_title)):
            score += 30
            reasons.append("title_match")
        if query_text and query_text in skill_text:
            score += 20
            reasons.append("skill_match")
        if industry_text and any(token in industry_text for token in ("ai", "人工智能", "机器学习", "深度学习", "软件", "互联网")):
            score += 15
            reasons.append("industry_match")
        return min(score, 100), reasons

    def _proposed_cli_args(self, candidate: OutreachCandidate, attachments: list[str]) -> list[str]:
        args = ["batch-greet", self.config.query, "--count", "1"]
        for path in attachments:
            args.extend(["--attachment", path])
        if candidate.city:
            args.extend(["--city", candidate.city])
        return args


def _norm(value: str) -> str:
    return "".join(str(value or "").lower().split())


def _tokens(value: str) -> list[str]:
    normalized = _norm(value)
    return [token for token in (normalized, normalized.replace("工程师", "")) if token]
```

- [ ] **Step 4: Run planner tests and verify they pass**

Run:

```bash
pytest tests/test_outreach_planner.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit core planner**

Run:

```bash
git add src/boss_agent_cli/rag_reply/outreach_planner.py tests/test_outreach_planner.py
git commit -m "feat: add boss outreach decision planner"
```

---

### Task 2: CLI `boss agent plan-outreach`

**Files:**
- Modify: `src/boss_agent_cli/commands/rag.py`
- Modify: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_rag_reply_commands.py`:

```python
def test_agent_plan_outreach_returns_explainable_actions(monkeypatch, tmp_path: Path):
    attachment = tmp_path / "proof.png"
    attachment.write_bytes(b"\x89PNG\r\n\x1a\n")

    def fake_collect(ctx, *, query, city, salary, experience, education, industry, scale, stage, job_type, welfare, count):
        return [
            {
                "security_id": "sec_001",
                "job_id": "job_001",
                "title": "RAG Agent 工程师",
                "company": "光昱智能",
                "city": "杭州",
                "industry": "人工智能",
                "skills": ["RAG", "Python"],
                "greeted": False,
            }
        ]

    monkeypatch.setattr(rag_commands, "_collect_outreach_plan_candidates", fake_collect)
    monkeypatch.setattr(
        rag_commands,
        "_profile_outreach_enabled",
        lambda ctx, profile_id: (True, ""),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "plan-outreach",
            "--query",
            "RAG",
            "--profile-id",
            "profile_001",
            "--target-title",
            "AI Agent 工程师",
            "--attachment",
            str(attachment),
            "--count",
            "1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "agent-plan-outreach"
    assert payload["data"]["plan"]["status"] == "planned"
    assert payload["data"]["plan"]["actions"][0]["decision"] == "greet_with_attachments"
    assert payload["data"]["plan"]["actions"][0]["reasons"]
    assert payload["data"]["dry_run"] is True


def test_agent_plan_outreach_blocks_when_profile_config_disables_outreach(monkeypatch, tmp_path: Path):
    def fake_collect(ctx, *, query, city, salary, experience, education, industry, scale, stage, job_type, welfare, count):
        return [
            {
                "security_id": "sec_001",
                "job_id": "job_001",
                "title": "RAG Agent 工程师",
                "company": "光昱智能",
                "city": "杭州",
                "industry": "人工智能",
                "skills": ["RAG"],
                "greeted": False,
            }
        ]

    monkeypatch.setattr(rag_commands, "_collect_outreach_plan_candidates", fake_collect)
    monkeypatch.setattr(
        rag_commands,
        "_profile_outreach_enabled",
        lambda ctx, profile_id: (False, "profile_outreach_disabled"),
    )
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "--json",
            "--data-dir",
            str(tmp_path),
            "agent",
            "plan-outreach",
            "--query",
            "RAG",
            "--profile-id",
            "profile_001",
            "--target-title",
            "AI Agent 工程师",
            "--live-execution-requested",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["data"]["plan"]["status"] == "blocked_profile_gate"
    assert payload["data"]["plan"]["send_ready"] is False
    assert payload["data"]["plan"]["blocked_reason"] == "profile_outreach_disabled"
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
pytest tests/test_rag_reply_commands.py::test_agent_plan_outreach_returns_explainable_actions tests/test_rag_reply_commands.py::test_agent_plan_outreach_blocks_when_profile_config_disables_outreach -q
```

Expected:

```text
FAILED ... No such command 'plan-outreach'
```

- [ ] **Step 3: Add imports and helper functions**

In `src/boss_agent_cli/commands/rag.py`, add imports near existing `rag_reply` imports:

```python
from boss_agent_cli.rag_reply.outreach_planner import (
    OutreachCandidate,
    OutreachPlanner,
    OutreachPlannerConfig,
)
from boss_agent_cli.search_filters import (
    SearchFilterCriteria,
    SearchPipelinePlatformError,
    resolve_welfare_keywords,
    run_search_pipeline,
)
```

Add helpers above `rag_init_cmd`:

```python
def _resolve_outreach_attachment_paths(ctx: click.Context, attachments: tuple[str, ...]) -> list[str] | None:
    paths: list[str] = []
    for raw_path in attachments:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            handle_error_output(
                ctx,
                _workflow_command(ctx, "plan-outreach"),
                code="INVALID_ATTACHMENT",
                message=f"附件文件不存在或不是文件: {path}",
                recoverable=True,
                recovery_action="检查 --attachment 路径后重试",
            )
            return None
        paths.append(str(path))
    return paths


def _profile_outreach_enabled(ctx: click.Context, profile_id: str) -> tuple[bool, str]:
    if not profile_id.strip():
        return False, "profile_id_required"
    service = _resolve_profile_service(ctx)
    config = service.get_profile_config(profile_id)
    if config is None:
        return False, "profile_config_not_found"
    if not config.outreach_auto_send_enabled:
        return False, "profile_outreach_disabled"
    return True, ""


def _collect_outreach_plan_candidates(
    ctx: click.Context,
    *,
    query: str,
    city: str | None,
    salary: str | None,
    experience: str | None,
    education: str | None,
    industry: str | None,
    scale: str | None,
    stage: str | None,
    job_type: str | None,
    welfare: str | None,
    count: int,
) -> list[dict[str, object]]:
    data_dir = ctx.obj["data_dir"]
    logger = ctx.obj["logger"]
    welfare_conditions = None
    if welfare:
        labels = [label.strip() for label in welfare.split(",") if label.strip()]
        welfare_conditions = [(label, resolve_welfare_keywords(label)) for label in labels]
    criteria = SearchFilterCriteria(
        query=query,
        city=city,
        salary=salary,
        experience=experience,
        education=education,
        industry=industry,
        scale=scale,
        stage=stage,
        job_type=job_type,
    )
    with CacheStore(data_dir / "cache" / "boss_agent.db") as cache:
        auth = AuthManager(data_dir, logger=logger, platform=ctx.obj.get("platform", "zhipin"))
        with get_platform_instance(ctx, auth) as platform:
            result = run_search_pipeline(
                platform,
                cache,
                logger,
                criteria=criteria,
                max_pages=max(1, min(count, 5)),
                limit=count,
                welfare_conditions=welfare_conditions,
                skip_greeted=True,
            )
    return list(result.items)
```

- [ ] **Step 4: Add the CLI command**

Add below `rag_targets_cmd` and above `rag_draft_cmd`:

```python
@rag_group.command("plan-outreach")
@click.option("--query", required=True)
@click.option("--profile-id", required=True)
@click.option("--target-title", default="")
@click.option("--city", default=None)
@click.option("--salary", default=None)
@click.option("--experience", default=None)
@click.option("--education", default=None)
@click.option("--industry", default=None)
@click.option("--scale", default=None)
@click.option("--stage", default=None)
@click.option("--job-type", default=None)
@click.option("--welfare", default=None)
@click.option("--count", default=5, type=int, show_default=True)
@click.option("--attachment", "attachments", multiple=True)
@click.option("--live-execution-requested", is_flag=True, default=False)
@click.pass_context
@handle_auth_errors("agent-plan-outreach")
def rag_plan_outreach_cmd(
    ctx: click.Context,
    query: str,
    profile_id: str,
    target_title: str,
    city: str | None,
    salary: str | None,
    experience: str | None,
    education: str | None,
    industry: str | None,
    scale: str | None,
    stage: str | None,
    job_type: str | None,
    welfare: str | None,
    count: int,
    attachments: tuple[str, ...],
    live_execution_requested: bool,
) -> None:
    attachment_paths = _resolve_outreach_attachment_paths(ctx, attachments)
    if attachment_paths is None:
        return
    safe_count = max(1, min(count, 150))
    try:
        raw_candidates = _collect_outreach_plan_candidates(
            ctx,
            query=query,
            city=city,
            salary=salary,
            experience=experience,
            education=education,
            industry=industry,
            scale=scale,
            stage=stage,
            job_type=job_type,
            welfare=welfare,
            count=safe_count,
        )
    except SearchPipelinePlatformError as exc:
        handle_error_output(
            ctx,
            _workflow_command(ctx, "plan-outreach"),
            code=exc.code,
            message=exc.message or "搜索结果获取失败",
            recoverable=exc.code == "NETWORK_ERROR",
            recovery_action="重试" if exc.code == "NETWORK_ERROR" else None,
            details=exc.details,
        )
        return
    profile_enabled, profile_blocked_reason = _profile_outreach_enabled(ctx, profile_id)
    planner = OutreachPlanner(
        OutreachPlannerConfig(
            query=query,
            target_title=target_title,
            profile_id=profile_id,
            profile_outreach_enabled=profile_enabled,
            live_execution_requested=live_execution_requested,
            count=safe_count,
        )
    )
    plan = planner.build_plan(
        [OutreachCandidate.from_mapping(item) for item in raw_candidates],
        attachments=attachment_paths,
    )
    payload = plan.to_payload()
    if profile_blocked_reason and not payload.get("blocked_reason"):
        payload["blocked_reason"] = profile_blocked_reason
    store = _resolve_store(ctx)
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="outreach_plan",
            entity_type="profile",
            entity_id=profile_id,
            payload={
                "query": query,
                "profile_id": profile_id,
                "plan": payload,
                "live_execution_requested": live_execution_requested,
            },
        )
    )
    handle_output(
        ctx,
        _workflow_command(ctx, "plan-outreach"),
        {
            "dry_run": True,
            "live_execution_requested": live_execution_requested,
            "plan": payload,
        },
        render=lambda data: click.echo(
            f"Planned {data['plan']['total']} outreach candidate(s).",
            err=True,
        ),
    )
```

- [ ] **Step 5: Run CLI tests and verify they pass**

Run:

```bash
pytest tests/test_rag_reply_commands.py::test_agent_plan_outreach_returns_explainable_actions tests/test_rag_reply_commands.py::test_agent_plan_outreach_blocks_when_profile_config_disables_outreach -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit CLI integration**

Run:

```bash
git add src/boss_agent_cli/commands/rag.py tests/test_rag_reply_commands.py
git commit -m "feat: expose boss outreach planning command"
```

---

### Task 3: Vite Bridge Endpoint

**Files:**
- Modify: `demo/interview-simulator/vite.config.mjs`
- Modify: `tests/test_interview_simulator_contract.py`

- [ ] **Step 1: Write failing bridge contract test**

Append to `tests/test_interview_simulator_contract.py`:

```python
def test_interview_simulator_exposes_read_only_outreach_plan_endpoint():
    repo_root = Path(__file__).resolve().parents[1]
    vite = (repo_root / "demo" / "interview-simulator" / "vite.config.mjs").read_text(encoding="utf-8")

    assert 'req.url === "/api/agent/outreach-plan"' in vite
    assert '"agent", "plan-outreach"' in vite
    assert 'appendTextOption(args, "--profile-id", body.profile_id)' in vite
    assert 'appendTextOption(args, "--target-title", body.targetTitle)' in vite
    assert 'args.push("--attachment", attachmentPath)' in vite
    assert "ensureAutoGreetDeliveryChannel" not in vite.split('req.url === "/api/agent/outreach-plan"', 1)[1].split("return;", 1)[0]
```

- [ ] **Step 2: Run bridge contract test and verify it fails**

Run:

```bash
pytest tests/test_interview_simulator_contract.py::test_interview_simulator_exposes_read_only_outreach_plan_endpoint -q
```

Expected:

```text
FAILED ... assert 'req.url === "/api/agent/outreach-plan"' in vite
```

- [ ] **Step 3: Add text option helper if missing**

In `demo/interview-simulator/vite.config.mjs`, add this helper near `normalizeAttachmentPaths` if there is no existing equivalent:

```js
function appendTextOption(args, flag, value) {
  const normalized = String(value || "").trim();
  if (normalized) {
    args.push(flag, normalized);
  }
}
```

- [ ] **Step 4: Add bridge route**

Inside `createRagBridgePlugin().configureServer(server)` request handler, add the route before `/api/boss/auto-greet`:

```js
      if (req.method === "POST" && req.url === "/api/agent/outreach-plan") {
        const body = await readJsonBody(req);
        const attachments = normalizeAttachmentPaths(body.attachments);
        const args = ["agent", "plan-outreach"];
        appendTextOption(args, "--query", body.query);
        appendTextOption(args, "--profile-id", body.profile_id);
        appendTextOption(args, "--target-title", body.targetTitle);
        appendTextOption(args, "--city", body.city);
        appendTextOption(args, "--salary", body.salary);
        appendTextOption(args, "--experience", body.experience);
        appendTextOption(args, "--education", body.education);
        appendTextOption(args, "--industry", body.industry);
        appendTextOption(args, "--scale", body.scale);
        appendTextOption(args, "--stage", body.stage);
        appendTextOption(args, "--job-type", body.jobType);
        appendTextOption(args, "--welfare", body.welfare);
        appendTextOption(args, "--count", body.count);
        for (const attachmentPath of attachments) {
          args.push("--attachment", attachmentPath);
        }
        const payload = runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, {
          ok: Boolean(payload.ok),
          data: payload.data || {},
          errorMessage: payload.error?.message || payload.errorMessage || "",
        });
        return;
      }
```

- [ ] **Step 5: Run bridge contract test and verify it passes**

Run:

```bash
pytest tests/test_interview_simulator_contract.py::test_interview_simulator_exposes_read_only_outreach_plan_endpoint -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit bridge endpoint**

Run:

```bash
git add demo/interview-simulator/vite.config.mjs tests/test_interview_simulator_contract.py
git commit -m "feat: bridge boss outreach planning"
```

---

### Task 4: Frontend Agent Plan Panel

**Files:**
- Modify: `demo/interview-simulator/src/App.jsx`
- Modify: `demo/interview-simulator/src/views/OutreachWorkspace.jsx`
- Modify: `demo/interview-simulator/src/styles.css`
- Modify: `tests/test_interview_simulator_contract.py`

- [ ] **Step 1: Write failing frontend contract test**

Append to `tests/test_interview_simulator_contract.py`:

```python
def test_interview_simulator_renders_agent_outreach_plan_panel():
    repo_root = Path(__file__).resolve().parents[1]
    app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")
    outreach = (
        repo_root / "demo" / "interview-simulator" / "src" / "views" / "OutreachWorkspace.jsx"
    ).read_text(encoding="utf-8")
    styles = (repo_root / "demo" / "interview-simulator" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "bossAgentPlan" in app
    assert "handleBossAgentPlan" in app
    assert 'fetch("/api/agent/outreach-plan"' in app
    assert "生成 Agent 计划" in outreach
    assert "agent-plan-card" in outreach
    assert ".agent-plan-card" in styles
```

- [ ] **Step 2: Run frontend contract test and verify it fails**

Run:

```bash
pytest tests/test_interview_simulator_contract.py::test_interview_simulator_renders_agent_outreach_plan_panel -q
```

Expected:

```text
FAILED ... assert 'bossAgentPlan' in app
```

- [ ] **Step 3: Add App state and handler**

In `demo/interview-simulator/src/App.jsx`, add state near existing Boss automation state:

```jsx
  const [bossAgentPlan, setBossAgentPlan] = useState(null);
  const [isBossAgentPlanning, setIsBossAgentPlanning] = useState(false);
  const [bossAgentPlanError, setBossAgentPlanError] = useState("");
```

Add handler near `handleBossSearchPreview` / `handleBossAutoGreet`:

```jsx
  async function handleBossAgentPlan() {
    if (!bossSearchForm.query.trim() || isBossAgentPlanning) return;
    setIsBossAgentPlanning(true);
    setBossAgentPlanError("");
    try {
      const response = await fetch("/api/agent/outreach-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...bossSearchForm,
          profile_id: selectedProfileId,
          targetTitle: "AI Agent 工程师",
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "生成 Agent 计划失败。");
      }
      setBossAgentPlan(payload.data?.plan || null);
    } catch (error) {
      setBossAgentPlan(null);
      setBossAgentPlanError(error instanceof Error ? error.message : "生成 Agent 计划失败。");
    } finally {
      setIsBossAgentPlanning(false);
    }
  }
```

Pass props into `<OutreachWorkspace />`:

```jsx
          bossAgentPlan={bossAgentPlan}
          isBossAgentPlanning={isBossAgentPlanning}
          bossAgentPlanError={bossAgentPlanError}
          handleBossAgentPlan={handleBossAgentPlan}
```

- [ ] **Step 4: Add OutreachWorkspace controls and cards**

In `demo/interview-simulator/src/views/OutreachWorkspace.jsx`, add props:

```jsx
  bossAgentPlan,
  isBossAgentPlanning,
  bossAgentPlanError,
  handleBossAgentPlan,
```

Add this button beside `预览` and before `Agent 全自动`:

```jsx
            <button
              type="button"
              className="apply-btn apply-btn--search"
              onClick={handleBossAgentPlan}
              disabled={isBossAgentPlanning || bossSearchActionsDisabled || !selectedProfileId}
            >
              <Lightning size={16} weight="fill" />
              {isBossAgentPlanning ? "规划中..." : "生成 Agent 计划"}
            </button>
```

Add this panel after the pending result block and before `bossAutomationResult`:

```jsx
          {bossAgentPlanError ? (
            <div className="apply-result apply-result--error">
              <WarningCircle size={18} weight="fill" />
              <span>{bossAgentPlanError}</span>
            </div>
          ) : null}

          {bossAgentPlan ? (
            <div className="agent-plan-panel">
              <div className="agent-plan-panel__header">
                <strong>Agent 计划</strong>
                <span>
                  {bossAgentPlan.status} · {bossAgentPlan.total || 0} 个候选 ·{" "}
                  {bossAgentPlan.send_ready ? "可执行" : "需确认"}
                </span>
              </div>
              <div className="agent-plan-list">
                {(bossAgentPlan.actions || []).slice(0, 5).map((action, index) => {
                  const candidate = action.candidate || {};
                  const label =
                    [candidate.title, candidate.company].filter(Boolean).join(" @ ") ||
                    candidate.security_id ||
                    `候选 ${index + 1}`;
                  return (
                    <article className="agent-plan-card" key={`${candidate.security_id || label}-${index}`}>
                      <div className="agent-plan-card__topline">
                        <strong>{label}</strong>
                        <span>{action.decision}</span>
                      </div>
                      <p>
                        score {action.score} · risk {action.risk}
                      </p>
                      <div className="agent-plan-card__reasons">
                        {(action.reasons || []).map((reason) => (
                          <span key={reason}>{reason}</span>
                        ))}
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}
```

- [ ] **Step 5: Add CSS**

Append to `demo/interview-simulator/src/styles.css`:

```css
.agent-plan-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(47, 128, 237, 0.14);
  background: rgba(255, 255, 255, 0.62);
}

.agent-plan-panel__header,
.agent-plan-card__topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.agent-plan-panel__header span,
.agent-plan-card p {
  margin: 0;
  color: var(--muted);
  font-size: 0.84rem;
}

.agent-plan-list {
  display: grid;
  gap: 10px;
}

.agent-plan-card {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--line);
  background: var(--surface-soft);
}

.agent-plan-card__topline strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-plan-card__topline span {
  flex: 0 0 auto;
  padding: 4px 8px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.76rem;
  font-weight: 800;
}

.agent-plan-card__reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-plan-card__reasons span {
  padding: 4px 7px;
  background: rgba(43, 58, 78, 0.06);
  color: var(--muted);
  font-size: 0.76rem;
}
```

- [ ] **Step 6: Run frontend contract test and verify it passes**

Run:

```bash
pytest tests/test_interview_simulator_contract.py::test_interview_simulator_renders_agent_outreach_plan_panel -q
```

Expected:

```text
1 passed
```

- [ ] **Step 7: Commit frontend panel**

Run:

```bash
git add demo/interview-simulator/src/App.jsx demo/interview-simulator/src/views/OutreachWorkspace.jsx demo/interview-simulator/src/styles.css tests/test_interview_simulator_contract.py
git commit -m "feat: show boss outreach agent plan"
```

---

### Task 5: Documentation and Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README description**

In `README.md`, under `## 🧠 Boss Agent V1`, add this subsection after the V1 bullet list:

```markdown
### Boss Runtime Decision Agent

`boss agent plan-outreach` 是只读决策层：它会搜索候选、读取本地 profile gate、检查附件路径、给每个候选生成 `decision / score / risk / reasons / proposed_cli_args`，并写入本地 audit log。它不会调用真实 `greet`、不会发送附件，也不会绕过 CDP/Bridge fail-closed 边界。

推荐链路是：

1. `boss agent plan-outreach --query <关键词> --profile-id <profile_id>` 生成计划。
2. 用户或上层 Agent 审阅 `actions` 和 `reasons`。
3. 真正执行时仍调用现有 `batch-greet` / watcher guarded tools。

这让系统具备“观察、解释、规划”的 Agent 行为，同时保持 live Boss 写操作可测试、可审计、可阻断。
```

- [ ] **Step 2: Run backend focused tests**

Run:

```bash
pytest tests/test_outreach_planner.py tests/test_rag_reply_commands.py::test_agent_plan_outreach_returns_explainable_actions tests/test_rag_reply_commands.py::test_agent_plan_outreach_blocks_when_profile_config_disables_outreach -q
```

Expected:

```text
6 passed
```

- [ ] **Step 3: Run frontend contract tests**

Run:

```bash
pytest tests/test_interview_simulator_contract.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 4: Run syntax and diff checks**

Run:

```bash
python -m py_compile src/boss_agent_cli/rag_reply/outreach_planner.py src/boss_agent_cli/commands/rag.py
git diff --check -- README.md src/boss_agent_cli/rag_reply/outreach_planner.py src/boss_agent_cli/commands/rag.py tests/test_outreach_planner.py tests/test_rag_reply_commands.py demo/interview-simulator/vite.config.mjs demo/interview-simulator/src/App.jsx demo/interview-simulator/src/views/OutreachWorkspace.jsx demo/interview-simulator/src/styles.css tests/test_interview_simulator_contract.py
```

Expected:

```text
both commands exit 0
```

- [ ] **Step 5: Commit docs and verification lock**

Run:

```bash
git add README.md
git commit -m "docs: describe boss decision agent layer"
```

---

## Final Verification

After all tasks are implemented, run:

```bash
pytest tests/test_outreach_planner.py tests/test_rag_reply_commands.py tests/test_interview_simulator_contract.py -q
python -m py_compile src/boss_agent_cli/rag_reply/outreach_planner.py src/boss_agent_cli/commands/rag.py
git diff --check -- README.md src/boss_agent_cli/rag_reply/outreach_planner.py src/boss_agent_cli/commands/rag.py tests/test_outreach_planner.py tests/test_rag_reply_commands.py demo/interview-simulator/vite.config.mjs demo/interview-simulator/src/App.jsx demo/interview-simulator/src/views/OutreachWorkspace.jsx demo/interview-simulator/src/styles.css tests/test_interview_simulator_contract.py
```

Expected:

```text
pytest exits 0
py_compile exits 0
git diff --check exits 0
```

Do not run live Boss auto-greet as part of this plan unless a later task changes `batch-greet`, `send_chat_attachment`, `_CliWatcherDelivery`, `execute_chat_reply`, CDP, Bridge, browser fetch, or result aggregation. This plan only adds read-only planning and UI display.

## Self-Review

Spec coverage:
- “Agent 体现在哪里” 的核心缺口：Task 1 增加可解释决策层。
- “不要把执行层变成自由 Agent” 的边界：Task 1/2 只输出 plan；真实执行仍复用现有 guarded tools。
- “前端能看见 Agent 感” 的需求：Task 3/4 增加 bridge endpoint 和 plan panel。
- “live Boss 安全边界” 的需求：Task 2 profile gate、Task 5 no-live-smoke rule 覆盖。

Placeholder scan:
- 本计划没有待定占位标记。
- 本计划没有空泛实现指令。
- 本计划没有未定义函数名：`OutreachPlanner`、`_collect_outreach_plan_candidates`、`_profile_outreach_enabled`、`handleBossAgentPlan` 都在任务内定义。

Type consistency:
- `OutreachPlan.to_payload()` 输出 `status/query/profile_id/total/send_ready/blocked_reason/actions`。
- CLI 输出 `data.plan`。
- Vite bridge 返回 `data`。
- React 读取 `payload.data?.plan`，字段一致。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-22-boss-runtime-decision-agent.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
