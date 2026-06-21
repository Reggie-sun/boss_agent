import json
from pathlib import Path

from click.testing import CliRunner

from boss_agent_cli.main import cli
from boss_agent_cli.rag_reply.profile_service import ProfileService
from boss_agent_cli.rag_reply.store import RagReplyStore


def _json(output: str) -> dict:
	return _envelope(output)["data"]


def _envelope(output: str) -> dict:
	return json.loads(output)


def test_agent_profile_create_list_config_and_bind(tmp_path: Path):
	runner = CliRunner()
	create = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)
	assert create.exit_code == 0
	assert _envelope(create.output)["command"] == "agent-profile-create"
	profile = _json(create.output)["profile"]
	profile_id = profile["profile_id"]
	assert profile["knowledge_base_id"] == f"kb_{profile_id}"

	list_result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"list",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
		],
	)
	assert list_result.exit_code == 0
	assert _json(list_result.output)["profiles"][0]["profile_id"] == profile_id

	config = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"config",
			"set",
			"--tenant-id",
			"tenant_001",
			"--profile-id",
			profile_id,
			"--contact-phone",
			"13800138000",
			"--contact-wechat",
			"reggie-ai",
			"--interview-windows",
			"工作日 20:00 后",
			"--reply-auto-send-enabled",
		],
	)
	assert config.exit_code == 0
	assert _envelope(config.output)["command"] == "agent-profile-config-set"
	assert _json(config.output)["config"]["reply_auto_send_enabled"] is True

	config_get = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"config",
			"get",
			"--profile-id",
			profile_id,
		],
	)
	assert config_get.exit_code == 0
	assert _envelope(config_get.output)["command"] == "agent-profile-config-get"
	assert _json(config_get.output)["config"]["contact_wechat"] == "reggie-ai"
	assert _json(config_get.output)["config"]["outreach_auto_send_enabled"] is False

	bind = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"conversation",
			"bind-profile",
			"--conversation-id",
			"conv_001",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			profile_id,
		],
	)
	assert bind.exit_code == 0
	assert _envelope(bind.output)["command"] == "agent-conversation-bind-profile"
	assert _json(bind.output)["binding"]["knowledge_base_id"] == f"kb_{profile_id}"

	current = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"conversation",
			"profile",
			"--conversation-id",
			"conv_001",
		],
	)
	assert current.exit_code == 0
	assert _envelope(current.output)["command"] == "agent-conversation-profile"
	assert _json(current.output)["binding"]["profile_id"] == profile_id


def test_agent_conversation_bind_profile_rejects_cross_scope_profile(tmp_path: Path):
	runner = CliRunner()
	create = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)
	assert create.exit_code == 0
	profile = _json(create.output)["profile"]
	profile_id = profile["profile_id"]
	assert profile["knowledge_base_id"] == f"kb_{profile_id}"

	bind = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"conversation",
			"bind-profile",
			"--conversation-id",
			"conv_cross_scope",
			"--tenant-id",
			"tenant_002",
			"--user-id",
			"user_002",
			"--profile-id",
			profile_id,
		],
	)

	assert bind.exit_code == 1
	envelope = _envelope(bind.output)
	assert envelope["ok"] is False
	assert envelope["command"] == "agent-conversation-bind-profile"
	assert envelope["error"]["code"] == "PROFILE_SCOPE_MISMATCH"
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	assert ProfileService(store).get_conversation_binding("conv_cross_scope") is None


def test_agent_profile_create_accepts_system_generated_knowledge_base_id(tmp_path: Path):
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)

	assert result.exit_code == 0
	profile = _json(result.output)["profile"]
	assert profile["knowledge_base_id"] == f"kb_{profile['profile_id']}"


def test_agent_conversation_bind_profile_rejects_cross_scope_overwrite(tmp_path: Path):
	runner = CliRunner()
	first = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
			"--knowledge-base-id",
			"kb_ai",
		],
	)
	assert first.exit_code == 0
	first_profile_id = _json(first.output)["profile"]["profile_id"]
	second = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_002",
			"--user-id",
			"user_002",
			"--name",
			"后端工程师",
			"--target-title",
			"Backend Engineer",
			"--knowledge-base-id",
			"kb_backend",
		],
	)
	assert second.exit_code == 0
	second_profile_id = _json(second.output)["profile"]["profile_id"]
	first_bind = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"conversation",
			"bind-profile",
			"--conversation-id",
			"conv_shared",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			first_profile_id,
		],
	)
	assert first_bind.exit_code == 0

	second_bind = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"conversation",
			"bind-profile",
			"--conversation-id",
			"conv_shared",
			"--tenant-id",
			"tenant_002",
			"--user-id",
			"user_002",
			"--profile-id",
			second_profile_id,
		],
	)

	assert second_bind.exit_code == 1
	envelope = _envelope(second_bind.output)
	assert envelope["ok"] is False
	assert envelope["command"] == "agent-conversation-bind-profile"
	assert envelope["error"]["code"] == "CONVERSATION_SCOPE_MISMATCH"
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	binding = ProfileService(store).get_conversation_binding("conv_shared")
	assert binding.tenant_id == "tenant_001"
	assert binding.user_id == "user_001"
	assert binding.profile_id == first_profile_id
	assert binding.knowledge_base_id == "kb_ai"


def test_agent_profile_rag_auth_set_stores_reference_without_secret(tmp_path: Path):
	runner = CliRunner()
	create = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)
	assert create.exit_code == 0
	profile_id = _json(create.output)["profile"]["profile_id"]

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"rag-auth",
			"set",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			profile_id,
			"--auth-mode",
			"bearer",
			"--credential-ref",
			"RAG_PROFILE_AI_TOKEN",
			"--scope-type",
			"category_id",
			"--scope-id",
			"cat_ai",
		],
	)

	assert result.exit_code == 0
	binding = _json(result.output)["binding"]
	assert binding["auth_mode"] == "bearer"
	assert binding["credential_ref"] == "[REDACTED]"
	assert binding["scope_type"] == "category_id"
	assert binding["scope_id"] == "cat_ai"
	assert "RAG_PROFILE_AI_TOKEN" not in result.output
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	stored = ProfileService(store).get_profile_rag_auth_binding(profile_id)
	assert stored.credential_ref == "RAG_PROFILE_AI_TOKEN"
	assert stored.scope_type == "category_id"
	assert stored.scope_id == "cat_ai"


def test_agent_profile_rag_auth_rejects_missing_profile_credential_ref(tmp_path: Path):
	runner = CliRunner()
	create = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)
	assert create.exit_code == 0
	profile_id = _json(create.output)["profile"]["profile_id"]

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"rag-auth",
			"set",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			profile_id,
			"--auth-mode",
			"bearer",
		],
	)

	assert result.exit_code == 1
	envelope = _envelope(result.output)
	assert envelope["ok"] is False
	assert envelope["command"] == "agent-profile-rag-auth-set"
	assert envelope["error"]["code"] == "RAG_AUTH_CREDENTIAL_REF_REQUIRED"
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	assert ProfileService(store).get_profile_rag_auth_binding(profile_id) is None


def test_agent_profile_upload_and_status_round_trip_source_file(tmp_path: Path):
	source = tmp_path / "resume.md"
	source.write_text("profile notes", encoding="utf-8")
	portfolio = tmp_path / "portfolio.md"
	portfolio.write_text("project portfolio", encoding="utf-8")
	runner = CliRunner()
	create = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"create",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--name",
			"AI 应用工程师",
			"--target-title",
			"AI Application Engineer",
		],
	)
	assert create.exit_code == 0
	profile_id = _json(create.output)["profile"]["profile_id"]

	upload = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"upload",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			profile_id,
			"--type",
			"resume",
			"--file",
			str(source),
		],
	)
	assert upload.exit_code == 0
	upload_record = _json(upload.output)["upload"]
	assert upload_record["source_filename"] == "resume.md"
	assert upload_record["source_type"] == "resume"
	assert upload_record["source_size_bytes"] == source.stat().st_size
	assert upload_record["rag_document_id"] == ""

	second_upload = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"upload",
			"--tenant-id",
			"tenant_001",
			"--user-id",
			"user_001",
			"--profile-id",
			profile_id,
			"--type",
			"portfolio",
			"--file",
			str(portfolio),
		],
	)
	assert second_upload.exit_code == 0
	second_upload_record = _json(second_upload.output)["upload"]
	assert second_upload_record["source_filename"] == "portfolio.md"
	assert second_upload_record["source_type"] == "portfolio"
	assert second_upload_record["profile_id"] == profile_id

	status = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"profile",
			"upload-status",
			"--profile-id",
			profile_id,
		],
	)
	assert status.exit_code == 0
	uploads = _json(status.output)["uploads"]
	assert [upload["source_filename"] for upload in uploads] == ["resume.md", "portfolio.md"]
	assert {upload["profile_id"] for upload in uploads} == {profile_id}
	assert uploads[0]["upload_id"] == upload_record["upload_id"]
	assert uploads[1]["upload_id"] == second_upload_record["upload_id"]


def test_agent_usage_summary_returns_stable_json_object(tmp_path: Path):
	runner = CliRunner()

	result = runner.invoke(
		cli,
		[
			"--json",
			"--data-dir",
			str(tmp_path),
			"agent",
			"usage",
			"summary",
			"--tenant-id",
			"tenant_001",
		],
	)

	assert result.exit_code == 0
	data = _json(result.output)
	assert data["tenant_id"] == "tenant_001"
	assert data["user_id"] == ""
	assert data["profile_id"] == ""
	assert data["counters"] == []
