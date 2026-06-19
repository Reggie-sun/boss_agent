import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import boss_agent_cli.commands.rag as rag_commands
from boss_agent_cli.commands.chat_reply import ChatReplyExecutionResult
from boss_agent_cli.ai.config import AIConfigStore
from boss_agent_cli.main import cli
from boss_agent_cli.rag_reply.adapters.boss_automation import SyncJobsResult, SyncMessagesResult
from boss_agent_cli.rag_reply.models import AuditLogRecord, ConversationRecord, DraftRecord, MessageRecord, RecruiterRecord
from boss_agent_cli.rag_reply.service import BossRagReplyService
from boss_agent_cli.rag_reply.store import RagReplyStore
from boss_agent_cli.rag_reply.watcher_config import WatcherConfig


def test_rag_group_is_registered():
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "rag", "--help"])
	assert result.exit_code == 0
	assert "Boss Agent workflow commands. Legacy alias: rag." in result.output


def test_agent_group_alias_is_registered():
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "agent", "--help"])
	assert result.exit_code == 0
	assert "Boss Agent workflow commands. Legacy alias: rag." in result.output


def test_rag_sync_messages_requires_explicit_opt_in(tmp_path: Path):
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "sync-messages"])
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["ok"] is False
	assert parsed["command"] == "rag-sync-messages"
	assert parsed["error"]["code"] == "RAG_READ_NOT_ENABLED"
	assert parsed["error"]["recoverable"] is True
	assert parsed["hints"]["manual_action_required"] is True


def test_rag_init_creates_store(tmp_path: Path):
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "init"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["status"] == "initialized"


def test_rag_review_and_approve_round_trip(tmp_path: Path, monkeypatch):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	draft = DraftRecord.new(
		conversation_id="conv_001",
		source_message_id="msg_001",
		draft_text="这是候选草稿",
		intent="project_question",
	)
	store.save_draft(draft)
	monkeypatch.setattr("boss_agent_cli.rag_reply.service.copy_text", lambda text: True)
	runner = CliRunner()

	review_result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "review", "--draft-id", draft.draft_id])
	assert review_result.exit_code == 0
	review_payload = json.loads(review_result.output)
	assert review_payload["ok"] is True
	assert review_payload["data"]["draft_text"] == "这是候选草稿"

	approve_result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "approve", draft.draft_id, "--copy"])
	assert approve_result.exit_code == 0
	approve_payload = json.loads(approve_result.output)
	assert approve_payload["ok"] is True
	assert approve_payload["data"]["draft"]["send_allowed"] is False
	assert approve_payload["data"]["approval_event"]["copied_to_clipboard"] is True


def test_rag_thread_returns_conversation_memory(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_draft(
		DraftRecord.new(
			conversation_id="conv_001",
			source_message_id="msg_001",
			draft_text="这是候选草稿",
			intent="project_question",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="msg_001",
			conversation_id="conv_001",
			message_text="你这个RAG项目具体做了什么？",
			direction="inbound",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="draftmsg_msg_001",
			conversation_id="conv_001",
			message_text="这是候选草稿",
			direction="outbound",
			message_type="draft",
			source="rag_draft_memory",
		)
	)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "rag", "thread", "--conversation-id", "conv_001"],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "rag-thread"
	assert len(parsed["data"]["messages"]) == 2
	assert parsed["data"]["messages"][1]["role"] == "assistant"


def test_rag_ask_persists_frontend_turn_and_returns_thread(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="demo-session-001", source="frontend_bridge"))
	store.save_message(
		MessageRecord(
			message_id="msg_prev",
			conversation_id="demo-session-001",
			message_text="之前聊过多轮对话能力吗？",
			direction="inbound",
			source="frontend_prompt",
		)
	)
	store.save_message(
		MessageRecord(
			message_id="draftmsg_msg_prev",
			conversation_id="demo-session-001",
			message_text="可以，我会把上下文一起带给 RAG。",
			direction="outbound",
			message_type="draft",
			source="rag_draft_memory",
		)
	)
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: SimpleNamespace(
				ok=True,
				answer="这次已经接到同一份持久 memory 了。",
				citations=[{"id": "c1"}],
				reasoning_summary={"steps": ["memory", "rag"]},
				raw_response={"answer": "这次已经接到同一份持久 memory 了。"},
				error_message=None,
				audit_status="draft_created",
				send_allowed=False,
				approval_required=True,
			)
		),
	)
	monkeypatch.setattr(rag_commands, "_build_service", lambda ctx: service)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"rag",
			"ask",
			"--conversation-id",
			"demo-session-001",
			"--question",
			"你这个RAG项目具体做了什么？",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "rag-ask"
	assert parsed["data"]["answer"] == "这次已经接到同一份持久 memory 了。"
	assert parsed["data"]["thread"][-1]["role"] == "assistant"
	assert len(parsed["data"]["thread"]) == 4
	assert store.list_messages("demo-session-001")[-2].source == "frontend_prompt"
	assert store.list_messages("demo-session-001")[-1].source == "rag_draft_memory"


def test_agent_ask_uses_agent_command_name(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: SimpleNamespace(
				ok=True,
				answer="现在通过 agent ask 暴露这条链路。",
				citations=[],
				reasoning_summary=None,
				raw_response={},
				error_message=None,
				audit_status="draft_created",
				send_allowed=False,
				approval_required=True,
			)
		),
	)
	monkeypatch.setattr(rag_commands, "_build_service", lambda ctx: service)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"ask",
			"--conversation-id",
			"demo-session-agent",
			"--question",
			"你这个RAG项目具体做了什么？",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-ask"


def test_agent_send_uses_agent_command_name(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(
		ConversationRecord(
			conversation_id="conv_send_001",
			source="frontend_bridge",
			state={"security_id": "sec_001"},
		)
	)
	draft = DraftRecord.new(
		conversation_id="conv_send_001",
		source_message_id="msg_send_001",
		draft_text="您好，这是我整理好的项目经历。",
		intent="resume_share_request",
	)
	store.save_draft(draft)
	monkeypatch.setattr(
		rag_commands,
		"execute_chat_reply",
		lambda ctx, **kwargs: ChatReplyExecutionResult(
			security_id=kwargs["security_id"],
			message=kwargs["message"],
			send_resume=kwargs["send_resume"],
			message_sent=True,
			resume_sent=True,
			results=["消息已发送", "在线简历已发送"],
		),
	)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"send",
			draft.draft_id,
			"--send-resume",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-send"
	assert parsed["data"]["security_id"] == "sec_001"
	assert parsed["data"]["resume_sent"] is True
	assert parsed["data"]["results"] == ["消息已发送", "在线简历已发送"]


def test_cli_watcher_delivery_forwards_target_identity(monkeypatch):
	seen: dict[str, object] = {}

	def _fake_execute(ctx, **kwargs):
		seen.update(kwargs)
		return ChatReplyExecutionResult(
			security_id=kwargs["security_id"],
			message=kwargs["message"],
			send_resume=kwargs["send_resume"],
			message_sent=True,
			resume_sent=False,
			results=["消息已发送"],
		)

	monkeypatch.setattr(rag_commands, "execute_chat_reply", _fake_execute)
	delivery = rag_commands._CliWatcherDelivery(SimpleNamespace())

	result = delivery.send(
		security_id="api_sec_001",
		message="hello",
		target={
			"recruiter_name": "李HR",
			"company": "测试公司",
			"title": "HRBP",
			"gid": "530232561",
			"friend_id": "530232561",
			"uid": "530232561",
			"encrypt_boss_id": "enc_boss_001",
			"recruiter_id": "boss_recruiter_530232561",
		},
	)

	assert result["ok"] is True
	assert seen["security_id"] == "api_sec_001"
	assert seen["message"] == "hello"
	assert seen["target_recruiter_name"] == "李HR"
	assert seen["target_company"] == "测试公司"
	assert seen["target_title"] == "HRBP"
	assert seen["target_gid"] == "530232561"
	assert seen["target_friend_id"] == "530232561"
	assert seen["target_uid"] == "530232561"
	assert seen["target_encrypt_boss_id"] == "enc_boss_001"
	assert seen["target_recruiter_id"] == "boss_recruiter_530232561"


def test_cli_watcher_delivery_keeps_attachment_request_as_attachment_delivery(monkeypatch):
	seen: dict[str, object] = {}

	def _fake_execute(ctx, **kwargs):
		seen.update(kwargs)
		return ChatReplyExecutionResult(
			security_id=kwargs["security_id"],
			message=kwargs["message"],
			send_resume=kwargs["send_resume"],
			message_sent=False,
			resume_sent=True,
			results=["附件简历已发送: resume.pdf"],
			resume_file_path=str(kwargs["resume_file_path"]),
		)

	monkeypatch.setattr(rag_commands, "execute_chat_reply", _fake_execute)
	delivery = rag_commands._CliWatcherDelivery(SimpleNamespace())

	result = delivery.send(
		security_id="api_sec_001",
		message="可以的，我发您简历。",
		send_attachment_resume=True,
		resume_file="/tmp/resume.pdf",
	)

	assert result["ok"] is True
	assert result["resume_sent"] is True
	assert result["requested_resume_file"] == "/tmp/resume.pdf"
	assert result["message_sent"] is False
	assert seen["send_resume"] is False
	assert seen["send_attachment_resume"] is True
	assert seen["resume_file_path"] == "/tmp/resume.pdf"


def test_agent_send_attachment_resume_does_not_send_draft_text(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(
		ConversationRecord(
			conversation_id="conv_attachment_001",
			source="frontend_bridge",
			state={"security_id": "sec_attachment"},
		)
	)
	draft = DraftRecord.new(
		conversation_id="conv_attachment_001",
		source_message_id="msg_attachment_001",
		draft_text="这段文字不应该作为聊天消息发出去。",
		intent="resume_share_request",
	)
	store.save_draft(draft)
	resume_file = tmp_path / "resume.pdf"
	resume_file.write_bytes(b"%PDF-1.4\n")
	seen: dict[str, object] = {}

	def _fake_execute(ctx, **kwargs):
		seen.update(kwargs)
		return ChatReplyExecutionResult(
			security_id=kwargs["security_id"],
			message=kwargs["message"],
			send_resume=kwargs["send_resume"],
			message_sent=False,
			resume_sent=True,
			results=["附件简历已发送: resume.pdf"],
			resume_file_path=str(resume_file),
		)

	monkeypatch.setattr(rag_commands, "execute_chat_reply", _fake_execute)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"send",
			draft.draft_id,
			"--send-attachment-resume",
			"--resume-file",
			str(resume_file),
			"--target-recruiter-name",
			"张HR",
			"--target-company",
			"测试公司",
			"--target-title",
			"招聘经理",
		],
	)

	assert result.exit_code == 0
	assert seen["send_resume"] is False
	assert seen["send_attachment_resume"] is True
	assert seen["resume_file_path"] == str(resume_file)
	assert seen["target_recruiter_name"] == "张HR"
	assert seen["target_company"] == "测试公司"
	assert seen["target_title"] == "招聘经理"
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["message_sent"] is False
	assert parsed["data"]["resume_sent"] is True
	assert parsed["data"]["send_attachment_resume"] is True
	assert parsed["data"]["resume_file"] == str(resume_file)
	assert parsed["data"]["target"] == {
		"recruiter_name": "张HR",
		"company": "测试公司",
		"title": "招聘经理",
	}


def test_rag_send_alias_uses_rag_command_name(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_conversation(ConversationRecord(conversation_id="conv_send_002", source="frontend_bridge"))
	draft = DraftRecord.new(
		conversation_id="conv_send_002",
		source_message_id="msg_send_002",
		draft_text="您好，我可以补充一份简历。",
		intent="resume_share_request",
	)
	store.save_draft(draft)
	monkeypatch.setattr(
		rag_commands,
		"execute_chat_reply",
		lambda ctx, **kwargs: ChatReplyExecutionResult(
			security_id=kwargs["security_id"],
			message=kwargs["message"],
			send_resume=kwargs["send_resume"],
			message_sent=True,
			resume_sent=False,
			results=["消息已发送"],
		),
	)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"rag",
			"send",
			draft.draft_id,
			"--security-id",
			"sec_002",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "rag-send"
	assert parsed["data"]["security_id"] == "sec_002"
	assert parsed["data"]["resume_sent"] is False


def test_rag_ask_auto_sends_resume_when_enabled(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_send_enabled": True}),
		encoding="utf-8",
	)
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: SimpleNamespace(
				ok=True,
				answer="unused",
				citations=[],
				reasoning_summary=None,
				raw_response={},
				error_message=None,
				audit_status="draft_created",
				send_allowed=False,
				approval_required=True,
			)
		),
	)
	monkeypatch.setattr(rag_commands, "_build_service", lambda ctx: service)
	monkeypatch.setattr(
		rag_commands,
		"_send_resume_reply",
		lambda ctx, **kwargs: rag_commands.ResumeSendResult(
			attempted=True,
			status="sent",
			message_sent=True,
			resume_sent=True,
			messages=["消息已发送", "在线简历已发送"],
			security_id="sec_001",
		),
	)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"rag",
			"ask",
			"--conversation-id",
			"demo-session-002",
			"--question",
			"你好我对你很感兴趣可以发一份简历吗",
			"--security-id",
			"sec_001",
			"--auto-send-resume",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["draft"]["intent"] == "resume_share_request"
	assert parsed["data"]["delivery"] == {
		"attempted": True,
		"status": "sent",
		"message_sent": True,
		"resume_sent": True,
		"messages": ["消息已发送", "在线简历已发送"],
		"error_message": "",
		"security_id": "sec_001",
	}


def test_rag_ask_reports_disabled_resume_send_when_flag_off(monkeypatch, tmp_path: Path):
	monkeypatch.setenv("BOSS_RAG_SEND_ENABLED", "false")
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(
			answer=lambda **kwargs: SimpleNamespace(
				ok=True,
				answer="unused",
				citations=[],
				reasoning_summary=None,
				raw_response={},
				error_message=None,
				audit_status="draft_created",
				send_allowed=False,
				approval_required=True,
			)
		),
	)
	monkeypatch.setattr(rag_commands, "_build_service", lambda ctx: service)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"rag",
			"ask",
			"--conversation-id",
			"demo-session-003",
			"--question",
			"方便发一份简历过来吗？",
			"--security-id",
			"sec_001",
			"--auto-send-resume",
		],
	)

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["delivery"] == {
		"attempted": False,
		"status": "disabled",
		"message": "未开启 boss_rag_send_enabled，已跳过自动发送简历。",
	}


class _FakeBossAdapter:
	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		return None

	def sync_jobs(self, query=None):
		assert query == "golang"
		return SyncJobsResult(
			sync_batch_id="sync_jobs_001",
			source="search_jobs",
			synced_job_ids=["job_001"],
			count=1,
		)

	def sync_messages(self, conversation_id=None):
		assert conversation_id is None
		return SyncMessagesResult(
			import_batch_id="bosssync_001",
			conversation_ids=["boss_conv_sec_001"],
			message_ids=["boss_msg_sec_001_m_001"],
			count=1,
		)

	def list_recent_targets(self, *, limit=5):
		assert limit == 3
		return [
			rag_commands.RecentConversationTarget(
				conversation_id="boss_conv_sec_001",
				security_id="sec_001",
				job_id="job_001",
				recruiter_name="张HR",
				company="测试公司",
				title="AI 应用工程师",
				last_message="麻烦发一下简历",
				last_message_at="2026-06-15T12:00:00+00:00",
				unread_count=1,
			)
		]


def test_rag_sync_jobs_uses_boss_adapter(monkeypatch, tmp_path: Path):
	monkeypatch.setattr("boss_agent_cli.commands.rag._build_boss_adapter", lambda ctx: _FakeBossAdapter())
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "sync-jobs", "--query", "golang"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "rag-sync-jobs"
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["job_ids"] == ["job_001"]


def test_rag_sync_messages_uses_boss_adapter_after_opt_in(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_allow_message_read": True}),
		encoding="utf-8",
	)
	monkeypatch.setattr("boss_agent_cli.commands.rag._build_boss_adapter", lambda ctx: _FakeBossAdapter())
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "rag", "sync-messages"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "rag-sync-messages"
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["conversation_ids"] == ["boss_conv_sec_001"]


def test_rag_targets_uses_boss_adapter_after_opt_in(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_allow_message_read": True}),
		encoding="utf-8",
	)
	monkeypatch.setattr("boss_agent_cli.commands.rag._build_boss_adapter", lambda ctx: _FakeBossAdapter())
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "agent", "targets", "--limit", "3"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-targets"
	assert parsed["data"]["source"] == "boss_live"
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["targets"][0]["security_id"] == "sec_001"


def test_agent_watcher_status_returns_recent_tasks(tmp_path: Path):
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "agent", "watcher-status"],
	)

	assert result.exit_code == 0
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["command"] == "agent-watcher-status"
	assert payload["data"]["running"] is False
	assert payload["data"]["tasks"] == []


def test_agent_watcher_status_returns_flattened_recent_tasks(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="watcher_task",
			entity_type="conversation",
			entity_id="conv_001",
			payload={
				"conversation_id": "conv_001",
				"message_id": "msg_001",
				"intent": "project_question",
				"status": "sent",
			},
		)
	)
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "agent", "watcher-status"],
	)

	assert result.exit_code == 0
	payload = json.loads(result.output)
	task = payload["data"]["tasks"][0]
	assert task["conversation_id"] == "conv_001"
	assert task["message_id"] == "msg_001"
	assert task["intent"] == "project_question"
	assert task["status"] == "sent"


def test_agent_watcher_run_disabled_by_default(tmp_path: Path):
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "agent", "watcher-run", "--once"],
	)

	assert result.exit_code == 0
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["command"] == "agent-watcher-run"
	assert payload["data"]["status"] == "paused"
	assert payload["data"]["reason"] == "watcher_disabled"
	assert payload["data"]["tasks"] == []


def test_agent_watcher_run_once_enabled_returns_run_counts(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_watcher_enabled": True}),
		encoding="utf-8",
	)
	called = {"run_once": False}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			called["run_once"] = True
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=2,
				blocked=3,
				tasks=[{"message_id": "msg_001", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "agent", "watcher-run", "--once"],
	)

	assert result.exit_code == 0
	assert called["run_once"] is True
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["command"] == "agent-watcher-run"
	assert payload["data"]["processed"] == 1
	assert payload["data"]["skipped"] == 2
	assert payload["data"]["blocked"] == 3
	assert payload["data"]["tasks"] == [{"message_id": "msg_001", "status": "sent"}]


def test_agent_watcher_run_once_keeps_last_twenty_tasks(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_watcher_enabled": True}),
		encoding="utf-8",
	)

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			return rag_commands.WatcherRunResult(
				processed=0,
				skipped=25,
				blocked=0,
				tasks=[{"message_id": f"msg_{idx}", "status": "skipped_duplicate"} for idx in range(25)],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--json", "--data-dir", str(tmp_path), "agent", "watcher-run", "--once"],
	)

	assert result.exit_code == 0
	payload = json.loads(result.output)
	tasks = payload["data"]["tasks"]
	assert payload["data"]["skipped"] == 25
	assert len(tasks) == 20
	assert tasks[0]["message_id"] == "msg_5"
	assert tasks[-1]["message_id"] == "msg_24"


def test_build_passive_watcher_registers_pipeline_candidate_provider(monkeypatch, tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	service = BossRagReplyService(
		store=store,
		rag_adapter=SimpleNamespace(),
	)
	config = WatcherConfig(
		enabled=True,
		dry_run=True,
		live_sync=True,
		contact_phone="13800138000",
		contact_wechat="reggie-ai",
		interview_windows="工作日 20:00 后",
		resume_attachment_path=str(tmp_path / "resume.pdf"),
	)
	ctx = SimpleNamespace(obj={"data_dir": tmp_path, "config": {}, "logger": None})

	monkeypatch.setattr(rag_commands, "_build_service", lambda ctx: service)
	monkeypatch.setattr(rag_commands, "_build_watcher_config", lambda ctx: config)

	watcher = rag_commands._build_passive_watcher(ctx)

	assert watcher.pipeline_candidate_provider is watcher.message_syncer
	assert hasattr(watcher.pipeline_candidate_provider, "list_pipeline_candidates")


def test_agent_watcher_run_once_live_sync_passes_flag(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
				"boss_rag_allow_message_read": True,
			}
		),
		encoding="utf-8",
	)
	called = {"live_sync": None}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			called["live_sync"] = live_sync
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": "msg_001", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--once",
			"--live-sync",
		],
	)

	assert result.exit_code == 0
	assert called["live_sync"] is True
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["processed"] == 1


def test_agent_watcher_run_ensure_chat_page_runs_before_watcher(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_watcher_enabled": True}),
		encoding="utf-8",
	)
	events: list[str] = []

	def _ensure_chat_page(cdp_url):
		events.append(f"ensure:{cdp_url}")
		return {
			"ok": True,
			"status": "ready",
			"url": "https://www.zhipin.com/web/geek/chat",
		}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			events.append("run")
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": "msg_001", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "ensure_candidate_chat_page_via_cdp", _ensure_chat_page)
	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--once",
			"--ensure-chat-page",
		],
	)

	assert result.exit_code == 0
	assert events == ["ensure:http://localhost:9229", "run"]
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["chat_page"]["status"] == "ready"


def test_agent_watcher_run_ensure_chat_page_fails_closed(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_watcher_enabled": True}),
		encoding="utf-8",
	)
	called = {"build_watcher": False}

	def _ensure_chat_page(cdp_url):
		return {
			"ok": False,
			"code": "CDP_UNAVAILABLE",
			"message": "cannot reach CDP at http://localhost:9229/json/list",
			"recoverable": True,
			"recovery_action": "启动带 remote-debugging-port=9229 的 Chrome 后重试",
		}

	def _build_watcher(ctx):
		called["build_watcher"] = True
		return object()

	monkeypatch.setattr(rag_commands, "ensure_candidate_chat_page_via_cdp", _ensure_chat_page)
	monkeypatch.setattr(rag_commands, "_build_passive_watcher", _build_watcher)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--once",
			"--ensure-chat-page",
		],
	)

	assert result.exit_code == 1
	assert called["build_watcher"] is False
	payload = json.loads(result.output)
	assert payload["ok"] is False
	assert payload["command"] == "agent-watcher-run"
	assert payload["error"]["code"] == "CDP_UNAVAILABLE"


def test_agent_watcher_run_live_sync_read_disabled_records_recovery(
	monkeypatch, tmp_path: Path
):
	monkeypatch.setenv("BOSS_RAG_ALLOW_MESSAGE_READ", "false")
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
			}
		),
		encoding="utf-8",
	)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--once",
			"--live-sync",
		],
	)

	assert result.exit_code == 0
	payload = json.loads(result.output)
	assert payload["ok"] is True
	task = payload["data"]["tasks"][0]
	assert task["status"] == "blocked_manual_required"
	assert task["error_code"] == "RAG_READ_NOT_ENABLED"
	assert task["recoverable"] is True
	assert task["recovery_action"] == (
		"Set boss_rag_allow_message_read=true in config.json and retry."
	)


def test_agent_watcher_run_once_no_live_sync_overrides_config(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
			}
		),
		encoding="utf-8",
	)
	called = {"live_sync": None}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			called["live_sync"] = live_sync
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": "msg_001", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--once",
			"--no-live-sync",
		],
	)

	assert result.exit_code == 0
	assert called["live_sync"] is False
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["processed"] == 1


def test_agent_watcher_run_loop_rejects_zero_max_cycles(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps({"boss_rag_watcher_enabled": True}),
		encoding="utf-8",
	)
	called = {"build_watcher": False}

	def _build_watcher(ctx):
		called["build_watcher"] = True
		return object()

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", _build_watcher)
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--loop",
			"--max-cycles",
			"0",
		],
	)

	assert result.exit_code == 1
	assert called["build_watcher"] is False
	payload = json.loads(result.output)
	assert payload["ok"] is False
	assert payload["command"] == "agent-watcher-run"
	assert payload["error"]["code"] == "INVALID_PARAM"


def test_agent_watcher_run_loop_stops_at_max_cycles(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_live_sync": True,
				"boss_rag_watcher_poll_seconds": 5,
			}
		),
		encoding="utf-8",
	)
	calls = {"run_once": 0, "sleep": []}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			calls["run_once"] += 1
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": f"msg_{calls['run_once']}", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	monkeypatch.setattr(rag_commands.time, "sleep", lambda seconds: calls["sleep"].append(seconds))
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--loop",
			"--max-cycles",
			"2",
		],
	)

	assert result.exit_code == 0
	assert calls["run_once"] == 2
	assert calls["sleep"] == [5]
	payload = json.loads(result.output)
	assert payload["ok"] is True
	assert payload["data"]["status"] == "completed"
	assert payload["data"]["cycles"] == 2
	assert payload["data"]["processed"] == 2


def test_agent_watcher_run_loop_emits_per_cycle_progress(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_poll_seconds": 5,
			}
		),
		encoding="utf-8",
	)
	calls = {"run_once": 0, "sleep": []}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			calls["run_once"] += 1
			return rag_commands.WatcherRunResult(
				processed=calls["run_once"],
				skipped=1,
				blocked=0,
				tasks=[],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	monkeypatch.setattr(rag_commands.time, "sleep", lambda seconds: calls["sleep"].append(seconds))
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--loop",
			"--max-cycles",
			"2",
		],
	)

	output = "\n".join(part for part in (result.output, result.stderr) if part)
	assert result.exit_code == 0
	assert "Watcher cycle 1 processed 1 task(s), skipped 1, blocked 0." in output
	assert "Watcher cycle 2 processed 2 task(s), skipped 1, blocked 0." in output


def test_agent_watcher_run_loop_keeps_last_twenty_tasks(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_watcher_enabled": True,
				"boss_rag_watcher_poll_seconds": 5,
			}
		),
		encoding="utf-8",
	)
	calls = {"run_once": 0, "sleep": []}

	class _FakeWatcher:
		def run_once(self, *, live_sync=None):
			calls["run_once"] += 1
			return rag_commands.WatcherRunResult(
				processed=1,
				skipped=0,
				blocked=0,
				tasks=[{"message_id": f"msg_{calls['run_once']}", "status": "sent"}],
			)

	monkeypatch.setattr(rag_commands, "_build_passive_watcher", lambda ctx: _FakeWatcher())
	monkeypatch.setattr(rag_commands.time, "sleep", lambda seconds: calls["sleep"].append(seconds))
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-run",
			"--loop",
			"--max-cycles",
			"25",
		],
	)

	assert result.exit_code == 0
	assert calls["run_once"] == 25
	assert calls["sleep"] == [5] * 24
	payload = json.loads(result.output)
	tasks = payload["data"]["tasks"]
	assert payload["data"]["cycles"] == 25
	assert payload["data"]["processed"] == 25
	assert len(tasks) == 20
	assert tasks[0]["message_id"] == "msg_6"
	assert tasks[-1]["message_id"] == "msg_25"


def test_cli_watcher_message_syncer_normalizes_read_disabled_and_success(monkeypatch):
	def _build_disabled_adapter(ctx):
		raise AssertionError("read-disabled sync must not build Boss adapter")

	disabled_ctx = SimpleNamespace(obj={"config": {"boss_rag_allow_message_read": False}})
	monkeypatch.setattr(rag_commands, "_build_boss_adapter", _build_disabled_adapter)

	disabled = rag_commands._CliWatcherMessageSyncer(disabled_ctx).sync_messages(conversation_id="conv_001")

	assert disabled["ok"] is False
	assert disabled["status"] == "read_disabled"
	assert disabled["count"] == 0
	assert disabled["error_code"] == "RAG_READ_NOT_ENABLED"
	assert disabled["recoverable"] is True
	assert disabled["recovery_action"] == (
		"Set boss_rag_allow_message_read=true in config.json and retry."
	)

	class _FakeBossAdapter:
		def __enter__(self):
			return self

		def __exit__(self, exc_type, exc, tb):
			return None

		def sync_messages(self, conversation_id=None):
			assert conversation_id == "conv_001"
			return SyncMessagesResult(
				import_batch_id="bosssync_001",
				conversation_ids=["conv_001"],
				message_ids=["msg_001"],
				count=1,
			)

	enabled_ctx = SimpleNamespace(obj={"config": {"boss_rag_allow_message_read": True}})
	monkeypatch.setattr(rag_commands, "_build_boss_adapter", lambda ctx: _FakeBossAdapter())

	synced = rag_commands._CliWatcherMessageSyncer(enabled_ctx).sync_messages(conversation_id="conv_001")

	assert synced == {
		"ok": True,
		"status": "synced",
		"count": 1,
		"conversation_ids": ["conv_001"],
		"message_ids": ["msg_001"],
	}


def test_agent_watcher_pause_and_resume_write_control_audit(tmp_path: Path):
	runner = CliRunner()
	pause = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-pause",
			"--conversation-id",
			"conv_001",
		],
	)
	resume = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"watcher-resume",
			"--conversation-id",
			"conv_001",
		],
	)

	assert pause.exit_code == 0
	assert resume.exit_code == 0
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	logs = [
		entry
		for entry in store.list_audit_logs("conv_001")
		if entry.event_type == "watcher_control"
	]
	assert [entry.payload["action"] for entry in logs] == ["pause", "resume"]


def test_rag_targets_falls_back_to_cached_targets_when_live_read_disabled(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_recruiter(
		RecruiterRecord(
			recruiter_id="recruiter_001",
			display_name="李HR",
			company="缓存公司",
		)
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id="boss_conv_cached_001",
			source="boss_sync",
			job_id="job_cached_001",
			recruiter_id="recruiter_001",
			last_message_at="2026-06-15T12:00:00+00:00",
			state={
				"security_id": "sec_cached_001",
				"title": "后端工程师",
				"company": "缓存公司",
				"last_msg": "最近方便沟通吗？",
			},
		)
	)
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "agent", "targets"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-targets"
	assert parsed["data"]["live_read_enabled"] is False
	assert parsed["data"]["source"] == "cache"
	assert parsed["data"]["targets"][0]["security_id"] == "sec_cached_001"


def test_rag_targets_excludes_frontend_bridge_cache_records(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_recruiter(
		RecruiterRecord(
			recruiter_id="recruiter_001",
			display_name="李HR",
			company="缓存公司",
		)
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id="boss_conv_cached_001",
			source="boss_sync",
			job_id="job_cached_001",
			recruiter_id="recruiter_001",
			last_message_at="2026-06-15T12:00:00+00:00",
			state={
				"security_id": "sec_cached_001",
				"title": "后端工程师",
				"company": "缓存公司",
				"last_msg": "最近方便沟通吗？",
			},
		)
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id="smoke-frontend-session",
			source="frontend_bridge",
			last_message_at="2026-06-16T12:00:00+00:00",
			state={
				"origin": "interview-simulator",
				"security_id": "sec_frontend_only",
			},
		)
	)
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "agent", "targets"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-targets"
	assert parsed["data"]["count"] == 1
	assert [item["conversation_id"] for item in parsed["data"]["targets"]] == ["boss_conv_cached_001"]


def test_rag_targets_dedupes_legacy_security_id_cache_records(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.save_recruiter(
		RecruiterRecord(
			recruiter_id="boss_recruiter_755278482",
			display_name="李HR",
			company="缓存公司",
		)
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id="boss_conv_sec_old_001",
			source="boss_sync",
			job_id="job_resume",
			recruiter_id="boss_recruiter_755278482",
			last_message_at="2026-06-16T12:00:00+00:00",
			state={
				"security_id": "sec_old_001",
				"gid": "755278482",
				"friend_id": "755278482",
				"uid": "755278482",
				"title": "HRBP",
				"company": "缓存公司",
				"last_msg": "对方已查看了您的附件简历",
			},
		)
	)
	store.save_conversation(
		ConversationRecord(
			conversation_id="boss_conv_sec_old_002",
			source="boss_sync",
			job_id="job_resume",
			recruiter_id="boss_recruiter_755278482",
			last_message_at="2026-06-15T12:00:00+00:00",
			state={
				"security_id": "sec_old_002",
				"gid": "755278482",
				"friend_id": "755278482",
				"uid": "755278482",
				"title": "HRBP",
				"company": "缓存公司",
				"last_msg": "对方已查看了您的附件简历",
			},
		)
	)
	runner = CliRunner()

	result = runner.invoke(cli, ["--json", "--data-dir", str(tmp_path), "agent", "targets"])

	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["command"] == "agent-targets"
	assert parsed["data"]["count"] == 1
	assert [item["conversation_id"] for item in parsed["data"]["targets"]] == ["boss_conv_sec_old_001"]


def test_rag_build_service_passes_rag_auth_config(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_rag_base_url": "http://127.0.0.1:8020",
				"boss_rag_rag_timeout_seconds": 11,
				"boss_rag_rag_api_key": "configured-rag-integration-key-123456",
				"boss_rag_rag_auth_mode": "x_api_key",
				"boss_rag_salary_reply": "当前薪资和期望薪资按候选人预设回复。",
			}
		),
		encoding="utf-8",
	)
	captured = {}

	class _FakeRagHttpAdapter:
		def __init__(self, *, base_url, timeout_seconds, api_key=None, auth_mode="none"):
			captured["base_url"] = base_url
			captured["timeout_seconds"] = timeout_seconds
			captured["api_key"] = api_key
			captured["auth_mode"] = auth_mode

	class _FakeFallbackAdapter:
		def __init__(self, *, ai_service):
			captured["fallback_model"] = ai_service.model
			captured["fallback_base_url"] = ai_service.base_url

	class _FakeAgentAnswerAdapter:
		def __init__(self, *, ai_service):
			captured["agent_model"] = ai_service.model
			captured["agent_base_url"] = ai_service.base_url

	monkeypatch.setattr(rag_commands, "RagHttpAdapter", _FakeRagHttpAdapter)
	monkeypatch.setattr(rag_commands, "AIFallbackAdapter", _FakeFallbackAdapter)
	monkeypatch.setattr(rag_commands, "AgentAnswerAdapter", _FakeAgentAnswerAdapter)
	monkeypatch.setattr(rag_commands, "_resolve_store", lambda ctx: "store")
	monkeypatch.setenv("BOSS_AGENT_MACHINE_ID", "test-machine")
	ai_store = AIConfigStore(tmp_path)
	ai_store.save_config(
		ai_provider="openai",
		ai_model="gpt-4o-mini",
		ai_base_url="https://api.openai.com/v1",
	)
	ai_store.save_api_key("test-key")
	ctx = SimpleNamespace(
		obj={
			"data_dir": tmp_path,
			"config": {
				"boss_rag_rag_base_url": "http://127.0.0.1:8020",
				"boss_rag_rag_timeout_seconds": 11,
				"boss_rag_rag_api_key": "configured-rag-integration-key-123456",
				"boss_rag_rag_auth_mode": "x_api_key",
				"boss_rag_salary_reply": "当前薪资和期望薪资按候选人预设回复。",
			},
		}
	)

	service = rag_commands._build_service(ctx)

	assert service is not None
	assert service.salary_reply == "当前薪资和期望薪资按候选人预设回复。"
	assert captured == {
		"base_url": "http://127.0.0.1:8020",
		"timeout_seconds": 11,
		"api_key": "configured-rag-integration-key-123456",
		"auth_mode": "x_api_key",
		"fallback_model": "gpt-4o-mini",
		"fallback_base_url": "https://api.openai.com/v1",
		"agent_model": "gpt-4o-mini",
		"agent_base_url": "https://api.openai.com/v1",
	}


def test_rag_build_service_skips_optional_ai_helpers_without_ai_config(monkeypatch, tmp_path: Path):
	captured = {}

	class _FakeRagHttpAdapter:
		def __init__(self, *, base_url, timeout_seconds, api_key=None, auth_mode="none"):
			captured["base_url"] = base_url
			captured["timeout_seconds"] = timeout_seconds
			captured["api_key"] = api_key
			captured["auth_mode"] = auth_mode

	class _FakeFallbackAdapter:
		def __init__(self, *, ai_service):
			captured["fallback_model"] = ai_service.model if ai_service else None

	class _FakeAgentAnswerAdapter:
		def __init__(self, *, ai_service):
			captured["agent_ai_service"] = ai_service

	monkeypatch.setattr(rag_commands, "RagHttpAdapter", _FakeRagHttpAdapter)
	monkeypatch.setattr(rag_commands, "AIFallbackAdapter", _FakeFallbackAdapter)
	monkeypatch.setattr(rag_commands, "AgentAnswerAdapter", _FakeAgentAnswerAdapter)
	monkeypatch.setattr(rag_commands, "_resolve_store", lambda ctx: "store")
	ctx = SimpleNamespace(
		obj={
			"data_dir": tmp_path,
			"config": {
				"boss_rag_rag_base_url": "http://127.0.0.1:8020",
				"boss_rag_rag_timeout_seconds": 11,
				"boss_rag_rag_api_key": "shared-rag-key-abc123",
				"boss_rag_rag_auth_mode": "x_api_key",
			},
		}
	)

	service = rag_commands._build_service(ctx)

	assert service is not None
	assert captured == {
		"base_url": "http://127.0.0.1:8020",
		"timeout_seconds": 11,
		"api_key": "shared-rag-key-abc123",
		"auth_mode": "x_api_key",
		"agent_ai_service": None,
	}
