import pytest

from boss_agent_cli.rag_reply.watcher_config import (
    WatcherConfig,
    WatcherConfigError,
    build_contact_reply,
    build_interview_window_reply,
    salary_handoff_reply,
)


def test_contact_reply_requires_unique_phone_and_wechat():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    assert (
        build_contact_reply(config)
        == "我的手机号是 13800138000，微信号是 reggie-ai。"
    )


def test_contact_reply_blocks_when_phone_missing():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    with pytest.raises(WatcherConfigError, match="boss_rag_contact_phone"):
        build_contact_reply(config)


def test_contact_reply_blocks_when_value_contains_multiple_candidates():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000,13900139000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    with pytest.raises(WatcherConfigError, match="must be unique"):
        build_contact_reply(config)


def test_salary_handoff_reply_is_fixed_agent_message():
    assert salary_handoff_reply() == (
        "我是候选人的求职助理 Agent，薪资相关问题需要候选人本人确认后回复。"
        "我已经记录下来，会提醒本人尽快处理。"
    )


def test_interview_window_reply_uses_configured_windows():
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path="/tmp/resume.pdf",
    )

    assert build_interview_window_reply(config) == (
        "可以的，我这边通常工作日 20:00 后，周末全天方便面试。"
        "您可以发几个可选时间，我确认后会尽快回复。"
    )
