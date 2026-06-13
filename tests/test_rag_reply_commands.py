import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import boss_agent_cli.commands.rag as rag_commands
from boss_agent_cli.main import cli
from boss_agent_cli.rag_reply.adapters.boss_automation import SyncJobsResult, SyncMessagesResult
from boss_agent_cli.rag_reply.models import DraftRecord
from boss_agent_cli.rag_reply.store import RagReplyStore


def test_rag_group_is_registered():
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "rag", "--help"])
	assert result.exit_code == 0
	assert "Boss RAG reply workflow commands." in result.output


def test_rag_sync_messages_requires_explicit_opt_in():
	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "rag", "sync-messages"])
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


def test_rag_build_service_passes_rag_auth_config(monkeypatch, tmp_path: Path):
	(tmp_path / "config.json").write_text(
		json.dumps(
			{
				"boss_rag_rag_base_url": "http://127.0.0.1:8020",
				"boss_rag_rag_timeout_seconds": 11,
				"boss_rag_rag_api_key": "configured-rag-integration-key-123456",
				"boss_rag_rag_auth_mode": "x_api_key",
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

	monkeypatch.setattr(rag_commands, "RagHttpAdapter", _FakeRagHttpAdapter)
	ctx = SimpleNamespace(
		obj={
			"data_dir": tmp_path,
			"config": {
				"boss_rag_rag_base_url": "http://127.0.0.1:8020",
				"boss_rag_rag_timeout_seconds": 11,
				"boss_rag_rag_api_key": "configured-rag-integration-key-123456",
				"boss_rag_rag_auth_mode": "x_api_key",
			},
		}
	)

	service = rag_commands._build_service(ctx)

	assert service is not None
	assert captured == {
		"base_url": "http://127.0.0.1:8020",
		"timeout_seconds": 11,
		"api_key": "configured-rag-integration-key-123456",
		"auth_mode": "x_api_key",
	}
