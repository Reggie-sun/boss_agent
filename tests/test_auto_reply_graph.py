from dataclasses import dataclass

from boss_agent_cli.rag_reply.auto_graph import run_auto_reply_graph
from boss_agent_cli.rag_reply.models import DraftRecord, MessageRecord
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


@dataclass
class _Delivery:
    calls: list[dict]

    def send(
        self,
        *,
        security_id: str,
        message: str,
        send_attachment_resume: bool = False,
        resume_file: str = "",
        target: dict[str, str] | None = None,
    ) -> dict[str, object]:
        payload = {
            "security_id": security_id,
            "message": message,
            "send_attachment_resume": send_attachment_resume,
            "resume_file": resume_file,
            "target": target or {},
        }
        self.calls.append(payload)
        return {
            "ok": True,
            "status": "sent",
            "message_sent": True,
            "resume_sent": False,
        }


def _config(
    *,
    dry_run: bool,
    send_enabled: bool = True,
    require_send_enabled: bool = True,
) -> WatcherConfig:
    return WatcherConfig(
        enabled=True,
        dry_run=dry_run,
        live_sync=True,
        contact_phone="13800138000",
        contact_wechat="reggie-ai",
        interview_windows="工作日 20:00 后",
        resume_attachment_path="/tmp/resume.pdf",
        send_enabled=send_enabled,
        require_send_enabled=require_send_enabled,
    )


def _message() -> MessageRecord:
    return MessageRecord(
        message_id="msg_001",
        conversation_id="conv_001",
        message_text="介绍下你的 RAG 项目",
        direction="inbound",
    )


def _draft() -> DraftRecord:
    return DraftRecord.new(
        conversation_id="conv_001",
        source_message_id="msg_001",
        draft_text="您好，我主要负责企业级 RAG 的检索链路和回答编排。",
        intent="project_question",
    )


def test_auto_reply_graph_dry_run_records_send_without_delivery():
    delivery = _Delivery(calls=[])

    result = run_auto_reply_graph(
        message=_message(),
        draft=_draft(),
        config=_config(dry_run=True),
        resolve_security_id=lambda conversation_id: "sec_001",
        target_payload=lambda conversation_id: {"company": "测试公司"},
        delivery=delivery,
    )

    assert result.status == "sent"
    assert result.dry_run is True
    assert result.delivery == {"ok": True, "status": "dry_run"}
    assert result.action["message"].startswith("您好，我主要负责")
    assert delivery.calls == []


def test_auto_reply_graph_live_sends_when_enabled():
    delivery = _Delivery(calls=[])

    result = run_auto_reply_graph(
        message=_message(),
        draft=_draft(),
        config=_config(dry_run=False, send_enabled=True),
        resolve_security_id=lambda conversation_id: "sec_001",
        target_payload=lambda conversation_id: {"company": "测试公司"},
        delivery=delivery,
    )

    assert result.status == "sent"
    assert result.dry_run is False
    assert result.delivery["ok"] is True
    assert delivery.calls == [
        {
            "security_id": "sec_001",
            "message": "您好，我主要负责企业级 RAG 的检索链路和回答编排。",
            "send_attachment_resume": False,
            "resume_file": "",
            "target": {"company": "测试公司"},
        }
    ]


def test_auto_reply_graph_blocks_live_send_when_send_flag_disabled():
    delivery = _Delivery(calls=[])

    result = run_auto_reply_graph(
        message=_message(),
        draft=_draft(),
        config=_config(dry_run=False, send_enabled=False),
        resolve_security_id=lambda conversation_id: "sec_001",
        target_payload=lambda conversation_id: {"company": "测试公司"},
        delivery=delivery,
    )

    assert result.status == "blocked_manual_required"
    assert result.error_message == "boss_rag_send_enabled_disabled"
    assert delivery.calls == []


def test_auto_reply_graph_send_flag_is_required_even_when_gate_flag_disabled():
    delivery = _Delivery(calls=[])

    result = run_auto_reply_graph(
        message=_message(),
        draft=_draft(),
        config=_config(
            dry_run=False,
            send_enabled=False,
            require_send_enabled=False,
        ),
        resolve_security_id=lambda conversation_id: "sec_001",
        target_payload=lambda conversation_id: {"company": "测试公司"},
        delivery=delivery,
    )

    assert result.status == "blocked_manual_required"
    assert result.error_message == "boss_rag_send_enabled_disabled"
    assert delivery.calls == []


def test_auto_reply_graph_blocks_missing_security_id():
    delivery = _Delivery(calls=[])

    result = run_auto_reply_graph(
        message=_message(),
        draft=_draft(),
        config=_config(dry_run=False, send_enabled=True),
        resolve_security_id=lambda conversation_id: "",
        target_payload=lambda conversation_id: {"company": "测试公司"},
        delivery=delivery,
    )

    assert result.status == "blocked_manual_required"
    assert result.error_message == "missing_security_id"
    assert delivery.calls == []
