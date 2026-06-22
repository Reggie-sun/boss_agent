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
