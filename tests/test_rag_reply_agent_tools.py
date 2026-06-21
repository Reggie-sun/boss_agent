from pathlib import Path

from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.models import (
    AuditLogRecord,
    ConversationRecord,
    DraftRecord,
    MessageRecord,
)
from boss_agent_cli.rag_reply.profile_models import (
    ConversationProfileBindingRecord,
    ProfileConfigRecord,
    TenantRecord,
    UserProfileRecord,
    UserRecord,
)
from boss_agent_cli.rag_reply.profile_service import ProfileService
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


class _FailingDelivery:
    def __init__(self, error):
        self.error = error
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
        raise self.error


class _TextThenFailingAttachmentDelivery(_Delivery):
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
        if send_attachment_resume:
            return {
                "ok": False,
                "status": "send_failed",
                "message_sent": False,
                "resume_sent": False,
                "error_message": "attachment upload failed",
            }
        return {
            "ok": True,
            "status": "sent",
            "message_sent": True,
            "resume_sent": False,
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


def _toolbox(
    tmp_path,
    *,
    dry_run=False,
    send_enabled=True,
    sync_result=None,
    delivery=None,
):
    store = _store(tmp_path)
    service = BossRagReplyService(store=store, rag_adapter=_RagAdapter())
    delivery = delivery or _Delivery()
    context = BossAgentToolContext(
        store=store,
        service=service,
        config=_config(tmp_path, dry_run=dry_run, send_enabled=send_enabled),
        delivery=delivery,
        message_syncer=_Syncer(sync_result or {"ok": True, "count": 0}),
    )
    return BossAgentToolbox(context), store, delivery


def _bind_profile_config(
    store,
    *,
    conversation_id="conv_001",
    reply_auto_send_enabled=True,
    proactive_resume_enabled=False,
    resume_attachment_path="",
):
    profile_service = ProfileService(store)
    profile_service.save_tenant(TenantRecord(tenant_id="tenant_001", display_name="Demo"))
    profile_service.save_user(
        UserRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            display_name="Reggie",
            email="r@example.com",
        )
    )
    profile_service.save_profile(
        UserProfileRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            profile_id="profile_ai",
            display_name="AI 应用工程师",
            target_title="AI Application Engineer",
            knowledge_base_id="kb_ai",
        )
    )
    profile_service.save_profile_config(
        ProfileConfigRecord(
            tenant_id="tenant_001",
            profile_id="profile_ai",
            contact_phone="13900139000",
            contact_wechat="profile-wechat",
            interview_windows="周三 19:00 后",
            salary_reply_policy="薪资需要本人确认。",
            resume_attachment_path=resume_attachment_path,
            reply_auto_send_enabled=reply_auto_send_enabled,
            proactive_resume_enabled=proactive_resume_enabled,
        )
    )
    profile_service.bind_conversation(
        ConversationProfileBindingRecord(
            tenant_id="tenant_001",
            user_id="user_001",
            conversation_id=conversation_id,
            profile_id="profile_ai",
            knowledge_base_id="kb_ai",
        )
    )
    return profile_service


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


def test_decide_auto_action_blocks_salary_without_policy(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path)
    draft = DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="",
        intent="salary_or_offer",
    )
    store.save_draft(draft)

    result = toolbox.decide_auto_action(draft_id=draft.draft_id)

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "INVALID_PARAM"
    assert "boss_rag_salary_reply" in result.error_message
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


def test_profile_config_blocks_live_send_after_action_is_ready(tmp_path):
    store = _store(tmp_path)
    config = _config(tmp_path, dry_run=False, send_enabled=True)
    profile_service = _bind_profile_config(
        store,
        reply_auto_send_enabled=False,
        resume_attachment_path=config.resume_attachment_path,
    )
    service = BossRagReplyService(
        store=store,
        rag_adapter=_RagAdapter(),
        profile_service=profile_service,
        profile_binding_required=False,
    )
    delivery = _Delivery()
    toolbox = BossAgentToolbox(
        BossAgentToolContext(
            store=store,
            service=service,
            config=config,
            delivery=delivery,
            message_syncer=_Syncer({"ok": True, "count": 0}),
        )
    )
    draft = DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="您好，我主要负责企业级 RAG。",
        intent="general_question",
    )
    store.save_draft(draft)

    action_result = toolbox.decide_auto_action(draft_id=draft.draft_id)
    send_result = toolbox.send_boss_reply_guarded(
        action=dict(action_result.data["action"]),
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert action_result.ok is True
    assert action_result.data["action"]["profile_config_applied"] is True
    assert action_result.data["action"]["profile_reply_auto_send_enabled"] is False
    assert send_result.ok is False
    assert send_result.error_code == "PROFILE_CONFIG_DISABLED"
    assert send_result.error_message == "profile_reply_auto_send_disabled"
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


def test_profile_config_disabled_send_still_allows_dry_run(tmp_path):
    toolbox, _store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，我主要负责企业级 RAG。",
            "send_attachment_resume": False,
            "resume_file": "",
            "status_after_send": "sent",
            "profile_config_applied": True,
            "profile_reply_auto_send_enabled": False,
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.data["delivery"] == {"ok": True, "status": "dry_run"}
    assert delivery.calls == []


def test_send_boss_reply_guarded_fails_closed_when_delivery_raises(tmp_path):
    delivery = _FailingDelivery(RuntimeError("browser unavailable"))
    toolbox, store, _delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        delivery=delivery,
    )

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
    assert result.status == "send_failed"
    assert result.error_message == "browser unavailable"
    assert result.data["delivery"]["ok"] is False
    assert result.data["delivery"]["status"] == "send_failed"
    assert len(delivery.calls) == 1
    assert store.list_drafts() == []


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


def test_send_boss_reply_guarded_sends_text_before_optional_proactive_resume(tmp_path):
    delivery = _TextThenFailingAttachmentDelivery()
    toolbox, _store, _delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        delivery=delivery,
    )
    resume_file = Path(toolbox.context.config.resume_attachment_path)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "您好，工作还在看的，方便的话可以继续沟通。",
            "send_attachment_resume": True,
            "attachment_required": False,
            "resume_file": str(resume_file),
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert result.error_message == ""
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "您好，工作还在看的，方便的话可以继续沟通。",
            "send_attachment_resume": False,
            "resume_file": "",
            "target": {"company": "测试公司"},
        },
        {
            "security_id": "sec_001",
            "message": "您好，工作还在看的，方便的话可以继续沟通。",
            "send_attachment_resume": True,
            "resume_file": str(resume_file),
            "target": {"company": "测试公司"},
        },
    ]
    assert result.data["delivery"]["message_sent"] is True
    assert result.data["delivery"]["resume_sent"] is False
    assert result.data["delivery"]["attachment_delivery"]["ok"] is False
    assert result.data["delivery"]["attachment_error_message"] == "attachment upload failed"


def test_profile_config_disables_proactive_resume_action(tmp_path):
    store = _store(tmp_path)
    config = _config(tmp_path, dry_run=False, send_enabled=True)
    config.proactive_resume_enabled = True
    profile_service = _bind_profile_config(
        store,
        reply_auto_send_enabled=True,
        proactive_resume_enabled=False,
        resume_attachment_path=config.resume_attachment_path,
    )
    service = BossRagReplyService(
        store=store,
        rag_adapter=_RagAdapter(),
        profile_service=profile_service,
        profile_binding_required=False,
    )
    toolbox = BossAgentToolbox(
        BossAgentToolContext(
            store=store,
            service=service,
            config=config,
            delivery=_Delivery(),
            message_syncer=_Syncer({"ok": True, "count": 0}),
        )
    )
    draft = DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="您好，我主要负责企业级 RAG。",
        intent="general_question",
    )
    store.save_draft(draft)

    result = toolbox.decide_auto_action(draft_id=draft.draft_id)

    assert result.ok is True
    assert result.data["action"]["profile_config_applied"] is True
    assert result.data["action"]["send_attachment_resume"] is False
    assert result.data["action"]["resume_file"] == ""


def test_send_boss_reply_guarded_keeps_required_resume_attachment_fail_closed(tmp_path):
    delivery = _TextThenFailingAttachmentDelivery()
    toolbox, _store, _delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        delivery=delivery,
    )
    resume_file = Path(toolbox.context.config.resume_attachment_path)

    result = toolbox.send_boss_reply_guarded(
        action={
            "kind": "send_text",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "attachment_required": True,
            "resume_file": str(resume_file),
            "status_after_send": "sent",
        },
        security_id="sec_001",
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "attachment_failed"
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


def test_send_attachment_resume_guarded_fails_closed_when_delivery_raises(tmp_path):
    delivery = _FailingDelivery(RuntimeError("browser unavailable"))
    toolbox, _store, _delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        delivery=delivery,
    )

    result = toolbox.send_attachment_resume_guarded(
        message="可以的，我这边通过 BOSS 直聘发送附件简历给您。",
        security_id="sec_001",
        resume_file=toolbox.context.config.resume_attachment_path,
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "attachment_failed"
    assert result.error_message == "browser unavailable"
    assert result.data["delivery"]["ok"] is False
    assert result.data["delivery"]["status"] == "attachment_failed"
    assert result.data["delivery"]["send_attachment_resume"] is True
    assert len(delivery.calls) == 1


def test_send_read_no_reply_followup_guarded_dry_run_uses_existing_disclosure(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "dry_run"
    assert result.data["stage"] == "read_no_reply"
    assert result.data["message"] == (
        "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位。"
    )
    assert result.data["delivery"] == {"ok": True, "status": "dry_run"}
    assert store.list_audit_logs("sec_read") == []
    assert delivery.calls == []


def test_send_read_no_reply_followup_guarded_blocks_live_send_when_disabled(tmp_path):
    toolbox, _store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=False)

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "SEND_DISABLED"
    assert result.error_message == "boss_rag_send_enabled_disabled"
    assert delivery.calls == []


def test_send_read_no_reply_followup_guarded_blocks_profile_disabled_send(tmp_path):
    store = _store(tmp_path)
    config = _config(tmp_path, dry_run=False, send_enabled=True)
    profile_service = _bind_profile_config(
        store,
        reply_auto_send_enabled=False,
        resume_attachment_path=config.resume_attachment_path,
    )
    delivery = _Delivery()
    service = BossRagReplyService(
        store=store,
        rag_adapter=_RagAdapter(),
        profile_service=profile_service,
        profile_binding_required=False,
    )
    toolbox = BossAgentToolbox(
        BossAgentToolContext(
            store=store,
            service=service,
            config=config,
            delivery=delivery,
            message_syncer=_Syncer({"ok": True, "count": 0}),
        )
    )

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
        conversation_id="conv_001",
    )

    assert result.ok is False
    assert result.status == "blocked_manual_required"
    assert result.error_code == "PROFILE_CONFIG_DISABLED"
    assert result.error_message == "profile_reply_auto_send_disabled"
    assert delivery.calls == []


def test_send_read_no_reply_followup_guarded_sends_and_records_audit(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert delivery.calls == [
        {
            "security_id": "sec_read",
            "message": "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位。",
            "send_attachment_resume": False,
            "resume_file": "",
            "target": {"company": "测试公司"},
        }
    ]
    audit = store.list_audit_logs("sec_read")[-1]
    assert audit.event_type == "read_no_reply_followup"
    assert audit.payload["status"] == "sent"
    assert audit.payload["agent_disclosed"] is True


def test_send_read_no_reply_followup_guarded_fails_closed_when_delivery_raises(tmp_path):
    delivery = _FailingDelivery(RuntimeError("browser unavailable"))
    toolbox, store, _delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        delivery=delivery,
    )

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
    )

    assert result.ok is False
    assert result.status == "send_failed"
    assert result.error_message == "browser unavailable"
    assert result.data["delivery"]["ok"] is False
    assert result.data["delivery"]["status"] == "send_failed"
    assert result.data["message_sent"] is False
    assert len(delivery.calls) == 1
    assert store.list_audit_logs("sec_read") == []


def test_send_read_no_reply_followup_guarded_does_not_repeat_disclosure(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="read_no_reply_followup",
            entity_type="security_id",
            entity_id="sec_read",
            payload={
                "security_id": "sec_read",
                "status": "sent",
                "agent_disclosed": True,
            },
        )
    )

    result = toolbox.send_read_no_reply_followup_guarded(
        security_id="sec_read",
        message="您好，想跟进一下这个岗位。",
        target={"company": "测试公司"},
    )

    assert result.ok is True
    assert result.status == "sent"
    assert delivery.calls[0]["message"] == "您好，想跟进一下这个岗位。"


def test_decide_auto_action_retries_proactive_resume_after_text_only_send(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path)
    toolbox.context.config.proactive_resume_enabled = True
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="conv_001",
            payload={
                "conversation_id": "conv_001",
                "status": "sent",
                "action": {"send_attachment_resume": True},
                "delivery": {"ok": True, "message_sent": True, "resume_sent": False},
            },
        )
    )
    draft = DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="您好，工作还在看的，方便的话可以继续沟通。",
        intent="smalltalk",
    )
    store.save_draft(draft)

    result = toolbox.decide_auto_action(draft_id=draft.draft_id)

    assert result.ok is True
    assert result.data["action"]["send_attachment_resume"] is True
    assert result.data["action"]["attachment_required"] is False
    assert delivery.calls == []
