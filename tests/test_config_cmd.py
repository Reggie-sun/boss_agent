"""config 命令测试 — 覆盖查看、设置、重置配置项。"""

import json
import os
from typing import Any

from click.testing import CliRunner, Result

from boss_agent_cli.main import cli


_ERROR_KEYS = {"code", "message", "recoverable", "recovery_action"}


def _assert_single_stdout_json_error(result: Result, *, command: str, code: str) -> dict[str, Any]:
	"""Agent-facing error output must stay machine-consumable on stdout only."""
	assert result.exit_code == 1
	assert result.stderr == ""
	assert result.output.strip()
	assert "\n" not in result.output.strip()
	parsed = json.loads(result.output)
	assert parsed["ok"] is False
	assert parsed["schema_version"] == "1.0"
	assert parsed["command"] == command
	assert parsed["data"] is None
	assert parsed["pagination"] is None
	assert set(parsed["error"]) == _ERROR_KEYS
	assert parsed["error"]["code"] == code
	assert isinstance(parsed["error"]["message"], str)
	assert isinstance(parsed["error"]["recoverable"], bool)
	return parsed


def _invoke(*args, tmp_path=None):
	runner = CliRunner()
	cli_args = []
	if tmp_path is not None:
		cli_args.extend(["--data-dir", str(tmp_path)])
	cli_args.extend(args)
	result = runner.invoke(cli, cli_args)
	return result.exit_code, json.loads(result.output) if result.output.strip() else None


# ── config list ─────────────────────────────────────────────────────


def test_config_list_returns_all_defaults(monkeypatch, tmp_path):
	"""无自定义配置时应返回全部默认项。"""
	for env_name in (
		"BOSS_RAG_RAG_BASE_URL",
		"BOSS_RAG_RAG_AUTH_MODE",
		"BOSS_RAG_RAG_API_KEY",
		"RAG_API_KEY",
		"RAG_AUTH_API_KEY",
		"BOSS_BATCH_GREET_AUTO_ENABLED",
	):
		os.environ.pop(env_name, None)
	monkeypatch.chdir(tmp_path)
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	assert parsed["ok"] is True
	items = parsed["data"]["items"]
	keys = {item["key"] for item in items}
	assert "log_level" in keys
	assert "cdp_url" in keys
	assert "request_delay" in keys
	assert "low_risk_mode" not in keys
	for item in items:
		assert item["source"] == "默认值"


def test_config_list_shows_user_overrides(tmp_path):
	"""有自定义配置时应标记为用户配置。"""
	config_file = tmp_path / "config.json"
	config_file.write_text('{"log_level": "debug"}', encoding="utf-8")
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	log_item = next(i for i in parsed["data"]["items"] if i["key"] == "log_level")
	assert log_item["value"] == "debug"
	assert log_item["source"] == "用户配置"


def test_config_list_shows_environment_override(monkeypatch, tmp_path):
	"""环境变量覆盖时应标记为环境变量来源。"""
	monkeypatch.setenv("RAG_API_KEY", "env-rag-key")
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	api_key_item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_rag_rag_api_key")
	assert api_key_item["source"] == "环境变量:RAG_API_KEY"


def test_config_list_shows_rag_auth_api_key_environment_override(monkeypatch, tmp_path):
	"""兼容历史 RAG_AUTH_API_KEY 时应标记真实环境变量来源。"""
	monkeypatch.setenv("RAG_AUTH_API_KEY", "env-rag-auth-key")
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	api_key_item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_rag_rag_api_key")
	assert api_key_item["source"] == "环境变量:RAG_AUTH_API_KEY"


def test_config_list_loads_dotenv_from_cwd(monkeypatch, tmp_path):
	"""当前工作目录存在 .env 时应自动读取 Boss RAG 环境变量。"""
	for env_name in ("BOSS_RAG_RAG_BASE_URL", "BOSS_RAG_RAG_AUTH_MODE", "BOSS_RAG_RAG_API_KEY", "RAG_API_KEY", "RAG_AUTH_API_KEY"):
		monkeypatch.delenv(env_name, raising=False)
	monkeypatch.chdir(tmp_path)
	(tmp_path / ".env").write_text(
		"BOSS_RAG_RAG_BASE_URL=http://127.0.0.1:8020\n"
		"BOSS_RAG_RAG_AUTH_MODE=x_api_key\n"
		"RAG_AUTH_API_KEY=test-dotenv-key\n",
		encoding="utf-8",
	)
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	base_url_item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_rag_rag_base_url")
	auth_mode_item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_rag_rag_auth_mode")
	api_key_item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_rag_rag_api_key")
	assert base_url_item["value"] == "http://127.0.0.1:8020"
	assert base_url_item["source"] == "环境变量:BOSS_RAG_RAG_BASE_URL"
	assert auth_mode_item["value"] == "x_api_key"
	assert auth_mode_item["source"] == "环境变量:BOSS_RAG_RAG_AUTH_MODE"
	assert api_key_item["value"] == "test-dotenv-key"
	assert api_key_item["source"] == "环境变量:RAG_AUTH_API_KEY"


def test_config_list_loads_batch_greet_auto_opt_in_from_dotenv(monkeypatch, tmp_path):
	"""显式 .env opt-in 后，批量开聊自动化开关应进入运行时 config。"""
	monkeypatch.delenv("BOSS_BATCH_GREET_AUTO_ENABLED", raising=False)
	monkeypatch.chdir(tmp_path)
	(tmp_path / ".env").write_text(
		"BOSS_BATCH_GREET_AUTO_ENABLED=true\n",
		encoding="utf-8",
	)
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert code == 0
	item = next(i for i in parsed["data"]["items"] if i["key"] == "boss_batch_greet_auto_enabled")
	assert item["value"] is True
	assert item["source"] == "环境变量:BOSS_BATCH_GREET_AUTO_ENABLED"


def test_config_without_subcommand_shows_list(tmp_path):
	"""不带子命令时应等同于 config list。"""
	code, parsed = _invoke("config", tmp_path=tmp_path)
	assert code == 0
	assert "items" in parsed["data"]


# ── config get ──────────────────────────────────────────────────────


def test_config_get_valid_key(tmp_path):
	"""获取已知配置项应返回值和默认值。"""
	code, parsed = _invoke("config", "get", "log_level", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["key"] == "log_level"
	assert parsed["data"]["value"] == "error"
	assert parsed["data"]["default"] == "error"


def test_config_get_unknown_key(tmp_path):
	"""获取未知配置项应返回 Agent 可消费的 stdout JSON 错误包络。"""
	runner = CliRunner()
	result = runner.invoke(cli, ["--data-dir", str(tmp_path), "config", "get", "nonexistent"])
	parsed = _assert_single_stdout_json_error(result, command="config", code="INVALID_PARAM")
	assert "可用项" in parsed["error"]["message"]
	assert parsed["hints"] is None


# ── config set ──────────────────────────────────────────────────────


def test_config_set_string_value(tmp_path):
	"""设置字符串类型配置项。"""
	code, parsed = _invoke("config", "set", "log_level", "debug", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["key"] == "log_level"
	assert parsed["data"]["value"] == "debug"
	# 验证持久化
	config_file = tmp_path / "config.json"
	saved = json.loads(config_file.read_text())
	assert saved["log_level"] == "debug"


def test_config_set_int_value(tmp_path):
	"""设置整数类型配置项。"""
	code, parsed = _invoke("config", "set", "batch_greet_max", "5", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["value"] == 5


def test_config_set_list_value(tmp_path):
	"""设置列表类型配置项。"""
	code, parsed = _invoke("config", "set", "request_delay", "2.0,4.0", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["value"] == [2.0, 4.0]


def test_config_set_null_value(tmp_path):
	"""设置可空配置项为 null。"""
	# 先设一个值
	_invoke("config", "set", "cdp_url", "http://localhost:9222", tmp_path=tmp_path)
	# 再重置为 null
	code, parsed = _invoke("config", "set", "cdp_url", "null", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["value"] is None


def test_config_set_unknown_key(tmp_path):
	"""设置未知配置项应返回 Agent 可消费的 stdout JSON 错误包络。"""
	runner = CliRunner()
	result = runner.invoke(cli, ["--data-dir", str(tmp_path), "config", "set", "bad_key", "val"])
	parsed = _assert_single_stdout_json_error(result, command="config", code="INVALID_PARAM")
	assert "可用项" in parsed["error"]["message"]


def test_config_commands_do_not_expose_internal_low_risk_policy(tmp_path):
	"""低风险策略不是普通用户配置项，不通过 config 命令提供恢复路径。"""
	for args in (
		("get", "low_risk_mode"),
		("set", "low_risk_mode", "false"),
		("reset", "low_risk_mode"),
	):
		code, parsed = _invoke("config", *args, tmp_path=tmp_path)
		assert code == 1
		assert parsed["error"]["code"] == "INVALID_PARAM"
		assert "low_risk_mode" not in parsed["error"]["message"]


# ── config reset ────────────────────────────────────────────────────


def test_config_reset_restores_default(tmp_path):
	"""重置配置项应恢复默认值并从文件中移除。"""
	# 先设置
	_invoke("config", "set", "log_level", "debug", tmp_path=tmp_path)
	# 再重置
	code, parsed = _invoke("config", "reset", "log_level", tmp_path=tmp_path)
	assert code == 0
	assert parsed["data"]["value"] == "error"
	assert parsed["data"]["restored"] is True
	# 验证文件中已移除
	config_file = tmp_path / "config.json"
	saved = json.loads(config_file.read_text())
	assert "log_level" not in saved


def test_config_reset_unknown_key(tmp_path):
	"""重置未知配置项应返回 Agent 可消费的 stdout JSON 错误包络。"""
	runner = CliRunner()
	result = runner.invoke(cli, ["--data-dir", str(tmp_path), "config", "reset", "bad_key"])
	parsed = _assert_single_stdout_json_error(result, command="config", code="INVALID_PARAM")
	assert "可用项" in parsed["error"]["message"]


# ── JSON 信封格式 ──────────────────────────────────────────────────


def test_config_json_envelope_structure(tmp_path):
	"""验证 config 输出符合 JSON 信封规范。"""
	code, parsed = _invoke("config", "list", tmp_path=tmp_path)
	assert "ok" in parsed
	assert "schema_version" in parsed
	assert "command" in parsed
	assert "data" in parsed
	assert parsed["command"] == "config"
