from pathlib import Path

from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.models import ConversationRecord, DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


class _RagResult:
    ok = True
    answer = "您好，我主要负责企业级 RAG 的检索链路和回答编排。"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "draft_created"
    send_allowed = False
    approval_required = True


class _RagAdapter:
    def answer(self, **kwargs):
        return _RagResult()


class _Delivery:
    def __init__(self):
        self.calls = []

    def send(
        self,
        *,
        security_id,
        message,
        send_attachment_resume=False,
        resume_file="",
        target=None,
    ):
        self.calls.append(
            {
                "security_id": security_id,
                "message": message,
                "send_attachment_resume": send_attachment_resume,
                "resume_file": resume_file,
                "target": target or {},
            }
        )
        return {
            "ok": True,
            "status": "sent",
            "message_sent": True,
            "resume_sent": bool(send_attachment_resume),
            "error_message": "",
        }


class _Syncer:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def sync_messages(self, *, conversation_id=None):
        self.calls += 1
        return self.result


def _store(tmp_path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return store


def _config(tmp_path, *, dry_run=False, send_enabled=True):
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n")
    return WatcherConfig(
        enabled=True,
        dry_run=dry_run,
        live_sync=True,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        resume_attachment_path=str(resume),
        send_enabled=send_enabled,
        require_send_enabled=True,
    )


def _toolbox(tmp_path, *, dry_run=False, send_enabled=True, sync_result=None):
    store = _store(tmp_path)
    service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())
    delivery = _Delivery()
    context = BossAgentToolContext(
        store=store,
        service=service,
        config=_config(tmp_path, dry_run=dry_run, send_enabled=send_enabled),
        delivery=delivery,
        message_syncer=_Syncer(sync_result or {"ok": True, "count": 0}),
    )
    return BossAgentToolbox(context), store, delivery


def test_sync_boss_messages_records_read_disabled_recovery(tmp_path):
    toolbox, store, delivery = _toolbox(
        tmp_path,
        sync_result={
            "ok": False,
            "status": "read_disabled",
            "error_code": "RAG_READ_NOT_ENABLED",
            "error_message": "Boss message reading is disabled by default.",
            "recoverable": True,
            "recovery_action": "Set boss_rag_allow_message_read=true in config.json and retry.",
        },
    )

    result = toolbox.sync_boss_messages()

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "RAG_READ_NOT_ENABLED"
    assert result.recoverable is True
    assert result.recovery_action == "Set boss_rag_allow_message_read=true in config.json and retry."
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_create_rag_draft_tool_uses_existing_service(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={"security_id": "sec_001"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
        )
    )

    result = toolbox.create_rag_draft(message_id="msg_001")

    assert result.ok is True
    assert result.status == "draft_created"
    assert result.data["draft_id"]
    assert result.data["intent"] == "project_question"
    assert store.get_draft(str(result.data["draft_id"])) is not None
    assert delivery.calls == []


def test_decide_auto_action_marks_resume_share_as_attachment(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path)
    draft = DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="可以的，我发您附件简历。",
        intent="resume_share_request",
    )
    store.save_draft(draft)

    result = toolbox.decide_auto_action(draft_id=draft.draft_id)

    assert result.ok is True
    assert result.status == "action_ready"
    assert result.data["action"]["send_attachment_resume"] is True
    assert result.data["action"]["resume_file"] == toolbox.context.config.resume_attachment_path
    assert delivery.calls == []


def test_send_boss_reply_guarded_blocks_when_send_disabled(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=False)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，我主要负责企业级 RAG。",
            "send_attachment_resume": False,
            "resume_file": "",
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "SEND_DISABLED"
    assert result.error_message == "boss_rag_send_enabled_disabled"
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_send_boss_reply_guarded_dry_run_does_not_call_delivery(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，我主要负责企业级 RAG。",
            "send_attachment_resume": False,
            "resume_file": "",
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert result.data["delivery"] == {"ok": True, "status": "dry_run"}
    assert store.list_drafts() == []
    assert delivery.calls == []


def test_send_boss_reply_guarded_routes_resume_action_to_attachment_tool(tmp_path):
    toolbox, _store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    resume_file = Path(toolbox.context.config.resume_attachment_path)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "resume_file": str(resume_file),
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "resume_file": str(resume_file),
            "target": {"company": "测试公司"},
        }
    ]


def test_send_attachment_resume_guarded_passes_attachment_flags(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    resume_file = Path(toolbox.context.config.resume_attachment_path)

    result = toolbox.send_attachment_resume_guarded(
        message="可以的，我这边通过 BOSS 直聘发送附件简历给您。",
        security_id="sec_001",
        resume_file=str(resume_file),
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "resume_file": str(resume_file),
            "target": {"company": "测试公司"},
        }
    ]
    assert store.list_drafts() == []


def test_send_attachment_resume_guarded_fails_closed_for_invalid_resume_file(tmp_path):
    toolbox, _store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("not a pdf", encoding="utf-8")

    result = toolbox.send_attachment_resume_guarded(
        message="可以的，我这边通过 BOSS 直聘发送附件简历给您。",
        security_id="sec_001",
        resume_file=str(resume_file),
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "attachment_failed"
    assert result.error_message == "invalid_resume_file"
    assert delivery.calls == []


def test_send_attachment_resume_guarded_fails_closed_for_missing_security_id(tmp_path):
    toolbox, _store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)

    result = toolbox.send_attachment_resume_guarded(
        message="可以的，我这边通过 BOSS 直聘发送附件简历给您。",
        security_id="",
        resume_file=toolbox.context.config.resume_attachment_path,
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_message == "missing_security_id"
    assert delivery.calls == []
