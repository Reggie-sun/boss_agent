from pathlib import Path

import pytest

from boss_agent_cli.rag_reply.auto_actions import (
    AutoReplyAction,
    build_action_for_draft,
)
from boss_agent_cli.rag_reply.models import (
    AuditLogRecord,
    ConversationRecord,
    DraftRecord,
    MessageRecord,
)
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher import BossPassiveWatcher
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig, WatcherConfigError


DRAFT_TEXT_INTENTS = [
    "project_question",
    "resume_question",
    "smalltalk",
    "resignation_status",
    "personal_status",
    "job_location_acceptance",
]


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
        send_enabled=True,
        require_send_enabled=True,
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


@pytest.mark.parametrize("intent", DRAFT_TEXT_INTENTS)
def test_draft_text_intents_send_non_empty_draft_text(tmp_path, intent):
    action = build_action_for_draft(_draft(intent, "我是项目回答"), _config(tmp_path))

    assert action == AutoReplyAction(
        kind="send_text",
        message="我是项目回答",
        status_after_send="sent",
        send_attachment_resume=False,
        blocked_reason="",
    )


@pytest.mark.parametrize("intent", DRAFT_TEXT_INTENTS)
def test_draft_text_intents_block_empty_drafts(tmp_path, intent):
    action = build_action_for_draft(_draft(intent, "  "), _config(tmp_path))

    assert action == AutoReplyAction(
        kind="block",
        status_after_send="rag_failed",
        blocked_reason="empty_draft",
    )


def test_resume_share_request_sends_text_and_attachment(tmp_path):
    config = _config(tmp_path)
    action = build_action_for_draft(
        _draft("resume_share_request", "可以的，我发您附件简历。"), config
    )

    assert action.kind == "send_text"
    assert action.send_attachment_resume is True
    assert action.resume_file == config.resume_attachment_path


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


@pytest.mark.parametrize("intent", ["interview_time", "availability_or_schedule"])
def test_interview_intents_use_configured_window_reply(tmp_path, intent):
    action = build_action_for_draft(_draft(intent, ""), _config(tmp_path))

    assert action == AutoReplyAction(
        kind="send_text",
        message=(
            "可以的，我这边通常工作日 20:00 后，周末全天方便面试。"
            "您可以发几个可选时间，我确认后会尽快回复。"
        ),
    )


def test_contact_exchange_uses_fixed_contact_reply(tmp_path):
    action = build_action_for_draft(_draft("contact_exchange", ""), _config(tmp_path))

    assert action.message == "我的手机号是 13800138000，微信号是 reggie-ai。"
    assert action.kind == "send_text"


def test_salary_or_offer_sends_preset_draft_when_available(tmp_path):
    action = build_action_for_draft(
        _draft("salary_or_offer", "当前薪资和期望薪资按候选人预设回复。"),
        _config(tmp_path),
    )

    assert action.kind == "send_text"
    assert action.message == "当前薪资和期望薪资按候选人预设回复。"
    assert action.status_after_send == "sent"


def test_salary_or_offer_sends_handoff_and_blocks_after_send(tmp_path):
    action = build_action_for_draft(_draft("salary_or_offer", ""), _config(tmp_path))

    assert "薪资相关问题需要候选人本人确认后回复" in action.message
    assert action.status_after_send == "blocked_manual_required"


def test_unknown_intent_blocks(tmp_path):
    action = build_action_for_draft(_draft("unsafe_or_unclear", ""), _config(tmp_path))

    assert action.kind == "block"
    assert action.blocked_reason == "intent_not_allowlisted"


class _FakeRagResult:
    ok = True
    answer = "RAG 回答"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "answered"
    send_allowed = False
    approval_required = True


class _FakeRagAdapter:
    def answer(self, *, rag_question: str, session_id: str, mode: str = "accurate"):
        return _FakeRagResult()


class _IntegrationRagResult:
    ok = True
    answer = "您好，我主要负责企业级 RAG 的检索链路和回答编排。"
    citations = []
    reasoning_summary = None
    raw_response = {}
    error_message = None
    audit_status = "draft_created"
    send_allowed = False
    approval_required = True


class _IntegrationRagAdapter:
    def answer(self, **kwargs):
        return _IntegrationRagResult()


class _RecordingDelivery:
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
            "results": ["sent"],
        }


class _Syncer:
    def __init__(self, store=None):
        self.calls = 0
        self.store = store

    def sync_messages(self, *, conversation_id=None):
        self.calls += 1
        if self.store is not None:
            self.store.save_message(
                MessageRecord(
                    message_id="msg_001",
                    conversation_id="conv_001",
                    message_text="介绍下你的 RAG 项目",
                    direction="inbound",
                )
            )
        return {
            "count": 1,
            "conversation_ids": ["conv_001"],
            "message_ids": ["msg_001"],
        }


class _FailingSyncer:
    def __init__(self):
        self.calls = 0

    def sync_messages(self, *, conversation_id=None):
        self.calls += 1
        return {"ok": False, "status": "read_disabled"}


class _RaisingSyncer:
    def sync_messages(self, *, conversation_id=None):
        raise RuntimeError("bridge_unavailable")


def _store(tmp_path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    return store


def _service(store):
    return BossRagReplyService(store=store, rag_adapter=_FakeRagAdapter())


def _integration_service(store):
    return BossRagReplyService(store=store, rag_adapter=_IntegrationRagAdapter())


def test_run_once_sends_contact_reply_and_writes_audit(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="test",
            state={
                "security_id": "sec_001",
                "recruiter_name": "张三",
                "company": "测试公司",
                "title": "AI 工程师",
            },
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="方便给个联系方式吗",
            direction="inbound",
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert delivery.calls[0]["message"] == "我的手机号是 13800138000，微信号是 reggie-ai。"
    audit = store.list_audit_logs("conv_001")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["status"] == "sent"


def test_run_once_dry_run_records_task_without_delivery(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="test",
            state={"security_id": "sec_001"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="方便给个联系方式吗",
            direction="inbound",
        )
    )
    config = _config(tmp_path)
    config.dry_run = True
    delivery = _RecordingDelivery()
    watcher = BossPassiveWatcher(
        store=store, service=_service(store), config=config, delivery=delivery
    )

    result = watcher.run_once()

    assert result.processed == 1
    assert delivery.calls == []
    assert result.tasks[0]["dry_run"] is True
    assert result.tasks[0]["delivery"]["status"] == "dry_run"
    audit = store.list_audit_logs("conv_001")[-1]
    assert audit.payload["dry_run"] is True
    assert audit.payload["delivery"]["status"] == "dry_run"


def test_run_once_skips_already_processed_message(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="test",
            state={"security_id": "sec_001"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_001",
            conversation_id="conv_001",
            message_text="你好",
            direction="inbound",
        )
    )
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="conv_001",
            payload={"message_id": "msg_001", "status": "sent"},
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.skipped == 1
    assert delivery.calls == []


def test_passive_watcher_syncs_live_messages_before_processing(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={"security_id": "sec_001"},
        )
    )
    syncer = _Syncer(store)
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=syncer,
    )

    result = watcher.run_once(live_sync=True)

    assert syncer.calls == 1
    assert result.processed == 1
    assert result.blocked == 0
    assert delivery.calls[0]["security_id"] == "sec_001"
    assert delivery.calls[0]["message"].startswith("您好，我主要负责")


def test_passive_watcher_blocks_live_sync_without_syncer(tmp_path):
    store = _store(tmp_path)
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
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.skipped == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "live_sync_unavailable"
    assert result.tasks[0]["live_sync"] is True
    assert delivery.calls == []
    assert store.list_drafts() == []
    audit = store.list_audit_logs("live_sync")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["error_message"] == "live_sync_unavailable"


def test_passive_watcher_blocks_live_delivery_without_live_sync(tmp_path):
    store = _store(tmp_path)
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
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = False
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
    )

    result = watcher.run_once(live_sync=False)

    assert result.processed == 0
    assert result.skipped == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "live_sync_required_for_delivery"
    assert result.tasks[0]["live_sync"] is False
    assert delivery.calls == []
    assert store.list_drafts() == []
    audit = store.list_audit_logs("live_sync")[-1]
    assert audit.payload["error_message"] == "live_sync_required_for_delivery"


def test_passive_watcher_blocks_failed_live_sync_result(tmp_path):
    store = _store(tmp_path)
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
    syncer = _FailingSyncer()
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=syncer,
    )

    result = watcher.run_once(live_sync=True)

    assert syncer.calls == 1
    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "read_disabled"
    assert result.tasks[0]["sync"]["status"] == "read_disabled"
    assert delivery.calls == []
    assert store.list_drafts() == []
    audit = store.list_audit_logs("live_sync")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["error_message"] == "read_disabled"


def test_passive_watcher_blocks_live_sync_exception(tmp_path):
    store = _store(tmp_path)
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
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_RaisingSyncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "bridge_unavailable"
    assert delivery.calls == []
    assert store.list_drafts() == []
    audit = store.list_audit_logs("live_sync")[-1]
    assert audit.payload["error_message"] == "bridge_unavailable"


def test_passive_watcher_respects_pause_control(tmp_path):
    store = _store(tmp_path)
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
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_control",
            entity_type="conversation",
            entity_id="conv_001",
            payload={"action": "pause", "conversation_id": "conv_001"},
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "paused"
    assert delivery.calls == []


def test_passive_watcher_respects_global_pause_and_resume(tmp_path):
    store = _store(tmp_path)
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
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_control",
            entity_type="conversation",
            entity_id="global",
            payload={"action": "pause", "conversation_id": None, "scope": "global"},
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    paused = watcher.run_once(live_sync=True)

    assert paused.processed == 0
    assert paused.blocked == 1
    assert paused.tasks[0]["status"] == "paused"
    assert delivery.calls == []

    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_control",
            entity_type="conversation",
            entity_id="global",
            payload={"action": "resume", "conversation_id": None, "scope": "global"},
        )
    )

    resumed = watcher.run_once(live_sync=True)

    assert resumed.processed == 1
    assert resumed.blocked == 0
    assert delivery.calls[0]["message"].startswith("您好，我主要负责")
