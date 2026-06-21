from pathlib import Path

import pytest

from boss_agent_cli.rag_reply.auto_actions import (
    AutoReplyAction,
    build_action_for_draft,
)
from boss_agent_cli.rag_reply.adapters.boss_automation import BossAutomationError
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
    "technical_question",
    "general_question",
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
            "我这边通常工作日 20:00 后，周末全天方便面试。"
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


class _StructuredRaisingSyncer:
    def sync_messages(self, *, conversation_id=None):
        raise BossAutomationError(
            "TOKEN_REFRESH_FAILED",
            "stoken expired",
            recoverable=True,
            recovery_action="boss login",
        )


class _PipelineProvider:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = 0

    def list_pipeline_candidates(self):
        self.calls += 1
        return self.candidates


class _FailingPipelineProvider:
    def list_pipeline_candidates(self):
        raise BossAutomationError(
            "TOKEN_REFRESH_FAILED",
            "stoken expired",
            recoverable=True,
            recovery_action="boss login",
        )


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


def test_run_once_skips_processed_platform_message_after_security_id_rotation(tmp_path):
    store = _store(tmp_path)
    raw_old = {
        "mid": 354743700415492,
        "securityId": "old_sec",
        "time": 1781746548734,
        "from": {"uid": 755278482, "name": "李HR"},
    }
    raw_new = {
        "mid": 354743700415492,
        "securityId": "new_sec",
        "time": 1781746548734,
        "from": {"uid": 755278482, "name": "李HR"},
    }
    store.save_message(
        MessageRecord(
            message_id="boss_msg_old_sec_1781746548734_oldhash",
            conversation_id="boss_conv_old_sec",
            message_text="对方已查看了您的附件简历",
            direction="inbound",
            raw=raw_old,
        )
    )
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="boss_conv_old_sec",
            payload={
                "message_id": "boss_msg_old_sec_1781746548734_oldhash",
                "status": "sent",
            },
        )
    )
    store.save_conversation(
        ConversationRecord(
            conversation_id="boss_conv_755278482",
            source="boss_sync",
            state={"security_id": "new_sec"},
        )
    )
    store.save_message(
        MessageRecord(
            message_id="boss_msg_755278482_354743700415492",
            conversation_id="boss_conv_755278482",
            message_text="对方已查看了您的附件简历",
            direction="inbound",
            raw=raw_new,
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
    )

    result = watcher.run_once()

    assert result.processed == 0
    assert result.skipped == 2
    assert delivery.calls == []
    assert store.list_drafts() == []


def test_run_once_dedupes_with_precomputed_message_index(tmp_path, monkeypatch):
    store = _store(tmp_path)
    for idx in range(50):
        store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id=f"conv_noise_{idx}",
                payload={"message_id": f"missing_{idx}", "status": "sent"},
            )
        )
    store.save_message(
        MessageRecord(
            message_id="boss_msg_old_sec_1781746548734_oldhash",
            conversation_id="boss_conv_old_sec",
            message_text="对方已查看了您的附件简历",
            direction="outbound",
            raw={"mid": 354743700415492, "securityId": "old_sec"},
        )
    )
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="boss_conv_old_sec",
            payload={
                "message_id": "boss_msg_old_sec_1781746548734_oldhash",
                "status": "sent",
            },
        )
    )
    store.save_message(
        MessageRecord(
            message_id="boss_msg_new_sec_1781746548734_newhash",
            conversation_id="boss_conv_new_sec",
            message_text="对方已查看了您的附件简历",
            direction="inbound",
            raw={"mid": 354743700415492, "securityId": "new_sec"},
        )
    )
    monkeypatch.setattr(
        store,
        "get_message",
        lambda message_id: pytest.fail(f"unexpected per-audit lookup: {message_id}"),
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
    )

    result = watcher.run_once()

    assert result.processed == 0
    assert result.skipped == 1
    assert delivery.calls == []
    assert store.list_drafts() == []


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


def test_passive_watcher_passes_live_target_identity_to_delivery(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            recruiter_id="boss_recruiter_530232561",
            state={
                "security_id": "api_sec_001",
                "gid": "530232561",
                "friend_id": "530232561",
                "uid": "530232561",
                "encrypt_boss_id": "enc_boss_001",
                "recruiter_name": "李HR",
                "company": "测试公司",
                "title": "HRBP",
            },
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
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert delivery.calls[0]["security_id"] == "api_sec_001"
    assert delivery.calls[0]["target"] == {
        "recruiter_name": "李HR",
        "company": "测试公司",
        "title": "HRBP",
        "security_id": "api_sec_001",
        "gid": "530232561",
        "friend_id": "530232561",
        "uid": "530232561",
        "encrypt_boss_id": "enc_boss_001",
        "recruiter_id": "boss_recruiter_530232561",
    }


def test_passive_watcher_records_tool_steps_for_sent_reply(tmp_path):
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
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert result.tasks[0]["status"] == "sent"
    assert [step["tool"] for step in result.tasks[0]["tool_steps"]] == [
        "create_rag_draft",
        "decide_auto_action",
        "resolve_boss_target",
        "send_boss_reply_guarded",
        "record_watcher_audit",
    ]
    assert delivery.calls[0]["security_id"] == "sec_001"


def test_passive_watcher_tool_graph_blocks_missing_security_id(tmp_path):
    store = _store(tmp_path)
    store.save_conversation(
        ConversationRecord(conversation_id="conv_001", source="boss_sync")
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
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_message"] == "missing_security_id"
    assert result.tasks[0]["tool_steps"][-1]["tool"] == "record_watcher_audit"
    assert delivery.calls == []


def test_passive_watcher_resume_share_sends_attachment_resume(tmp_path):
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
            message_text="可以发我一份简历吗",
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
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert result.tasks[0]["intent"] == "resume_share_request"
    assert result.tasks[0]["action"]["send_attachment_resume"] is True
    assert delivery.calls[0]["send_attachment_resume"] is True
    assert delivery.calls[0]["resume_file"] == config.resume_attachment_path


def test_passive_watcher_sends_proactive_resume_after_first_boss_reply(tmp_path):
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
            message_text="你好",
            direction="inbound",
            created_at="2026-06-17T08:00:00+00:00",
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    config.proactive_resume_enabled = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    first = watcher.run_once(live_sync=True)

    assert first.processed == 1
    assert first.tasks[0]["action"]["send_attachment_resume"] is True
    assert delivery.calls[0]["send_attachment_resume"] is True
    assert delivery.calls[0]["resume_file"] == config.resume_attachment_path

    store.save_message(
        MessageRecord(
            message_id="msg_002",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
            created_at="2026-06-17T08:01:00+00:00",
        )
    )

    second = watcher.run_once(live_sync=True)

    assert second.processed == 1
    assert second.tasks[0]["action"]["send_attachment_resume"] is False
    assert len(delivery.calls) == 2
    assert delivery.calls[1]["send_attachment_resume"] is False


def test_passive_watcher_processes_read_no_reply_pipeline_candidate(tmp_path):
    store = _store(tmp_path)
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    pipeline_provider = _PipelineProvider(
        [
            {
                "stage": "read_no_reply",
                "security_id": "sec_read",
                "company": "测试公司",
                "title": "AI 工程师",
            }
        ]
    )
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
        pipeline_candidate_provider=pipeline_provider,
    )

    result = watcher.run_once(live_sync=True)

    assert pipeline_provider.calls == 1
    assert result.processed == 1
    assert result.blocked == 0
    assert result.tasks[0]["stage"] == "read_no_reply"
    assert result.tasks[0]["security_id"] == "sec_read"
    assert result.tasks[0]["status"] == "dry_run"
    assert result.tasks[0]["action"]["kind"] == "send_read_no_reply_followup"
    assert result.tasks[0]["delivery"] == {"ok": True, "status": "dry_run"}
    assert [step["tool"] for step in result.tasks[0]["tool_steps"]] == [
        "send_read_no_reply_followup_guarded",
        "record_watcher_audit",
    ]
    assert delivery.calls == []


def test_passive_watcher_limits_read_no_reply_pipeline_candidates_per_cycle(tmp_path):
    store = _store(tmp_path)
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    config.read_no_reply_followup_limit_per_cycle = 1
    pipeline_provider = _PipelineProvider(
        [
            {"stage": "read_no_reply", "security_id": "sec_first"},
            {"stage": "read_no_reply", "security_id": "sec_second"},
        ]
    )
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
        pipeline_candidate_provider=pipeline_provider,
    )

    result = watcher.run_once(live_sync=True)

    assert pipeline_provider.calls == 1
    assert result.processed == 1
    assert result.tasks == [
        {
            "message_id": "",
            "conversation_id": "",
            "draft_id": "",
            "intent": "read_no_reply",
            "stage": "read_no_reply",
            "security_id": "sec_first",
            "status": "dry_run",
            "error_message": "",
            "dry_run": True,
            "action": {
                "kind": "send_read_no_reply_followup",
                "message": (
                    "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前"
                    "是否还在招聘？如果方便的话可以继续沟通，我这边对岗位方向比较感兴趣。"
                ),
            },
            "delivery": {"ok": True, "status": "dry_run"},
            "target": {
                "recruiter_name": "",
                "company": "",
                "title": "",
                "security_id": "sec_first",
                "gid": "",
                "friend_id": "",
                "uid": "",
                "encrypt_boss_id": "",
                "recruiter_id": "",
            },
            "tool_steps": [
                {
                    "tool": "send_read_no_reply_followup_guarded",
                    "ok": True,
                    "status": "dry_run",
                    "error_code": "",
                    "error_message": "",
                },
                {
                    "tool": "record_watcher_audit",
                    "ok": True,
                    "status": "audit_recorded",
                    "error_code": "",
                    "error_message": "",
                },
            ],
        }
    ]
    assert delivery.calls == []


def test_passive_watcher_throttles_read_no_reply_after_recent_followup(tmp_path):
    store = _store(tmp_path)
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="read_no_reply_followup",
            entity_type="security_id",
            entity_id="sec_recent",
            payload={"security_id": "sec_recent", "status": "sent"},
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    config.read_no_reply_followup_min_interval_seconds = 300
    pipeline_provider = _PipelineProvider(
        [{"stage": "read_no_reply", "security_id": "sec_next"}]
    )
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
        pipeline_candidate_provider=pipeline_provider,
    )

    result = watcher.run_once(live_sync=True)

    assert pipeline_provider.calls == 0
    assert result.processed == 0
    assert result.skipped == 0
    assert result.blocked == 0
    assert result.tasks == []
    assert delivery.calls == []


def test_passive_watcher_skips_processed_read_no_reply_pipeline_candidate(tmp_path):
    store = _store(tmp_path)
    store.append_audit_log(
        AuditLogRecord.new(
            event_type="watcher_task",
            entity_type="security_id",
            entity_id="sec_read",
            payload={
                "security_id": "sec_read",
                "stage": "read_no_reply",
                "intent": "read_no_reply",
                "status": "dry_run",
            },
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    pipeline_provider = _PipelineProvider(
        [{"stage": "read_no_reply", "security_id": "sec_read"}]
    )
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
        pipeline_candidate_provider=pipeline_provider,
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.skipped == 1
    assert result.tasks == [
        {
            "security_id": "sec_read",
            "stage": "read_no_reply",
            "status": "skipped_duplicate",
        }
    ]
    assert delivery.calls == []


def test_passive_watcher_blocks_failed_pipeline_candidate_discovery(tmp_path):
    store = _store(tmp_path)
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
        pipeline_candidate_provider=_FailingPipelineProvider(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_code"] == "TOKEN_REFRESH_FAILED"
    assert result.tasks[0]["error_message"] == "stoken expired"
    assert result.tasks[0]["recoverable"] is True
    assert delivery.calls == []


def test_passive_watcher_processes_only_latest_inbound_per_conversation(tmp_path):
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
            message_text="你好",
            direction="inbound",
            created_at="2026-06-17T08:00:00+00:00",
        )
    )
    store.save_message(
        MessageRecord(
            message_id="msg_002",
            conversation_id="conv_001",
            message_text="介绍下你的 RAG 项目",
            direction="inbound",
            created_at="2026-06-17T08:01:00+00:00",
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

    assert result.processed == 1
    assert len(delivery.calls) == 1
    assert result.tasks[0]["message_id"] == "msg_002"


def test_passive_watcher_retries_unsent_rag_failure_before_failure_limit(tmp_path):
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
            event_type="watcher_task",
            entity_type="conversation",
            entity_id="conv_001",
            payload={
                "message_id": "msg_001",
                "status": "rag_failed",
                "error_message": "empty_draft",
                "action": {"kind": "block"},
                "delivery": {},
            },
        )
    )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 1
    assert result.skipped == 0
    assert result.tasks[0]["message_id"] == "msg_001"
    assert result.tasks[0]["status"] == "sent"
    assert result.tasks[0]["delivery"]["status"] == "dry_run"
    assert delivery.calls == []


def test_passive_watcher_stops_retrying_unsent_rag_failure_at_failure_limit(tmp_path):
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
    for _ in range(3):
        store.append_audit_log(
            AuditLogRecord.new(
                event_type="watcher_task",
                entity_type="conversation",
                entity_id="conv_001",
                payload={
                    "message_id": "msg_001",
                    "status": "rag_failed",
                    "error_message": "empty_draft",
                    "action": {"kind": "block"},
                    "delivery": {},
                },
            )
        )
    delivery = _RecordingDelivery()
    config = _config(tmp_path)
    config.dry_run = True
    config.live_sync = True
    config.max_failures_per_conversation = 3
    watcher = BossPassiveWatcher(
        store=store,
        service=_integration_service(store),
        config=config,
        delivery=delivery,
        message_syncer=_Syncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.skipped == 1
    assert result.tasks == [
        {
            "message_id": "msg_001",
            "status": "skipped_retry_limit",
            "error_message": "max_failures_reached",
            "failure_count": 3,
        }
    ]
    assert delivery.calls == []


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


def test_passive_watcher_records_recovery_metadata_for_structured_sync_error(tmp_path):
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
        message_syncer=_StructuredRaisingSyncer(),
    )

    result = watcher.run_once(live_sync=True)

    assert result.processed == 0
    assert result.blocked == 1
    assert result.tasks[0]["status"] == "blocked_manual_required"
    assert result.tasks[0]["error_code"] == "TOKEN_REFRESH_FAILED"
    assert result.tasks[0]["error_message"] == "stoken expired"
    assert result.tasks[0]["recoverable"] is True
    assert result.tasks[0]["recovery_action"] == "boss login"
    assert delivery.calls == []
    assert store.list_drafts() == []
    audit = store.list_audit_logs("live_sync")[-1]
    assert audit.payload["error_code"] == "TOKEN_REFRESH_FAILED"


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
