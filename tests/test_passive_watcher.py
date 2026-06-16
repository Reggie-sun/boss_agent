from pathlib import Path

import pytest

from boss_agent_cli.rag_reply.models import DraftRecord
from boss_agent_cli.rag_reply.watcher import WatcherAction, build_action_for_draft
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig, WatcherConfigError


def _config(tmp_path: Path) -> WatcherConfig:
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path=str(resume),
    )


def _draft(intent: str, text: str = "草稿") -> DraftRecord:
    return DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text=text,
        intent=intent,
        risk_labels=[],
        evidence={"source": "test"},
        approval_required=True,
        send_allowed=False,
    )


def test_project_question_sends_draft_text(tmp_path):
    action = build_action_for_draft(
        _draft("project_question", "我是项目回答"), _config(tmp_path)
    )

    assert action == WatcherAction(
        kind="send_text",
        message="我是项目回答",
        status_after_send="sent",
        send_attachment_resume=False,
        blocked_reason="",
    )


def test_resume_share_request_sends_text_and_attachment(tmp_path):
    action = build_action_for_draft(
        _draft("resume_share_request", "可以的，我发您附件简历。"), _config(tmp_path)
    )

    assert action.kind == "send_text"
    assert action.send_attachment_resume is True
    assert action.resume_file.endswith("resume.pdf")


def test_resume_share_request_rejects_pdf_directory(tmp_path):
    resume_dir = tmp_path / "resume.pdf"
    resume_dir.mkdir()
    config = WatcherConfig(
        enabled=True,
        dry_run=False,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后，周末全天",
        resume_attachment_path=str(resume_dir),
    )

    with pytest.raises(WatcherConfigError, match="existing PDF file"):
        build_action_for_draft(_draft("resume_share_request"), config)


def test_contact_exchange_uses_fixed_contact_reply(tmp_path):
    action = build_action_for_draft(_draft("contact_exchange", ""), _config(tmp_path))

    assert action.message == "我的手机号是 13800138000，微信号是 reggie-ai。"
    assert action.kind == "send_text"


def test_salary_or_offer_sends_handoff_and_blocks_after_send(tmp_path):
    action = build_action_for_draft(_draft("salary_or_offer", ""), _config(tmp_path))

    assert "薪资相关问题需要候选人本人确认后回复" in action.message
    assert action.status_after_send == "blocked_manual_required"


def test_unknown_intent_blocks(tmp_path):
    action = build_action_for_draft(_draft("unsafe_or_unclear", ""), _config(tmp_path))

    assert action.kind == "block"
    assert action.blocked_reason == "intent_not_allowlisted"
