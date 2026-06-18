from boss_agent_cli.rag_reply.agent_tools import BossAgentToolContext, BossAgentToolbox
from boss_agent_cli.rag_reply.models import ConversationRecord, MessageRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.tool_graph import run_tool_reply_graph
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


class _ResumeRagResult(_RagResult):
    answer = "可以的，我这边通过 BOSS 直聘发送附件简历给您。"


class _RagAdapter:
    def __init__(self, result=None):
        self.result = result or _RagResult()

    def answer(self, **kwargs):
        return self.result


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
        }


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


def _toolbox(tmp_path, *, dry_run=False, send_enabled=True, rag_result=None):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    service = BossRagReplyService(store=store, rag_adapter=_RagAdapter(rag_result))
    delivery = _Delivery()
    context = BossAgentToolContext(
        store=store,
        service=service,
        config=_config(tmp_path, dry_run=dry_run, send_enabled=send_enabled),
        delivery=delivery,
        message_syncer=None,
    )
    return BossAgentToolbox(context), store, delivery


def _message(store, *, text="介绍下你的 RAG 项目", security_id="sec_001"):
    store.save_conversation(
        ConversationRecord(
            conversation_id="conv_001",
            source="boss_sync",
            state={
                "security_id": security_id,
                "recruiter_name": "李HR",
                "company": "测试公司",
                "title": "AI 工程师",
            },
        )
    )
    message = MessageRecord(
        message_id="msg_001",
        conversation_id="conv_001",
        message_text=text,
        direction="inbound",
    )
    store.save_message(message)
    return message


def test_tool_reply_graph_calls_guarded_tools_and_records_audit(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    message = _message(store)

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "sent"
    assert result.intent == "project_question"
    assert result.task["message_id"] == "msg_001"
    assert result.task["status"] == "sent"
    assert [step["tool"] for step in result.tool_steps] == [
        "create_rag_draft",
        "decide_auto_action",
        "resolve_boss_target",
        "send_boss_reply_guarded",
        "record_watcher_audit",
    ]
    assert delivery.calls[0]["security_id"] == "sec_001"
    assert delivery.calls[0]["message"].startswith("您好，我主要负责")
    audit = store.list_audit_logs("conv_001")[-1]
    assert audit.event_type == "watcher_task"
    assert audit.payload["tool_steps"][-1]["tool"] == "record_watcher_audit"


def test_tool_reply_graph_blocks_missing_security_id_without_delivery(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=False, send_enabled=True)
    message = _message(store, security_id="")

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "blocked_manual_required"
    assert result.error_message == "missing_security_id"
    assert delivery.calls == []
    assert result.task["status"] == "blocked_manual_required"
    assert result.task["tool_steps"][-2]["tool"] == "resolve_boss_target"
    assert result.task["tool_steps"][-1]["tool"] == "record_watcher_audit"


def test_tool_reply_graph_dry_run_records_delivery_without_real_send(tmp_path):
    toolbox, store, delivery = _toolbox(tmp_path, dry_run=True, send_enabled=True)
    message = _message(store)

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "sent"
    assert result.task["dry_run"] is True
    assert result.task["delivery"] == {"ok": True, "status": "dry_run"}
    assert delivery.calls == []


def test_tool_reply_graph_resume_share_sends_attachment_not_plain_text(tmp_path):
    toolbox, store, delivery = _toolbox(
        tmp_path,
        dry_run=False,
        send_enabled=True,
        rag_result=_ResumeRagResult(),
    )
    message = _message(store, text="可以发我一份简历吗")

    result = run_tool_reply_graph(message=message, toolbox=toolbox)

    assert result.status == "sent"
    assert result.intent == "resume_share_request"
    assert result.task["action"]["send_attachment_resume"] is True
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "可以的，我这边通过 BOSS 直聘发送附件简历给您。",
            "send_attachment_resume": True,
            "resume_file": toolbox.context.config.resume_attachment_path,
            "target": {
                "recruiter_name": "李HR",
                "company": "测试公司",
                "title": "AI 工程师",
                "security_id": "sec_001",
                "gid": "",
                "friend_id": "",
                "uid": "",
                "encrypt_boss_id": "",
                "recruiter_id": "",
            },
        }
    ]
