import json
from unittest.mock import patch, ANY

from click.testing import CliRunner

from boss_agent_cli.main import cli


def _ctx_mock(mock_cls):
	instance = mock_cls.return_value
	instance.__enter__ = lambda self: self
	instance.__exit__ = lambda self, *a: None
	return instance


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_success(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 0, "zpData": {}}

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "apply", "sec_001", "job_001"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["security_id"] == "sec_001"
	assert parsed["data"]["job_id"] == "job_001"
	assert parsed["data"]["mode"] == "immediate_chat_apply"
	mock_cache.record_apply.assert_called_once_with("sec_001", "job_001", resume_name="")


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_success_with_message(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 0, "zpData": {}}

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "apply", "sec_001", "job_001", "--message", "你好，我对这个岗位很感兴趣"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["greeting"] == "你好，我对这个岗位很感兴趣"
	mock_platform.apply.assert_called_once_with("sec_001", "job_001", lid="", message="你好，我对这个岗位很感兴趣")


@patch("boss_agent_cli.commands.apply.ResumeStore")
@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_with_resume_generates_auto_message(mock_cache_cls, mock_auth_cls, mock_get_platform, mock_resume_store_cls):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 0, "zpData": {}}

	mock_resume_store = mock_resume_store_cls.return_value
	from boss_agent_cli.resume.models import ResumeData
	mock_resume_store.get.return_value = ResumeData(
		name="my_resume",
		title="我的简历",
		center_title=False,
		personal_info=None,
		job_intention=None,
		modules=[],
		avatar="",
	)

	runner = CliRunner()
	result = runner.invoke(cli, [
		"--json", "apply", "sec_001", "job_001",
		"--resume", "my_resume",
		"--title", "Python开发",
		"--company", "XX科技",
	])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["mode"] == "auto_apply"
	assert parsed["data"]["resume"]["name"] == "my_resume"
	assert "my_resume" in parsed["data"]["greeting"]
	assert "Python开发" in parsed["data"]["greeting"]
	mock_cache.record_apply.assert_called_once_with("sec_001", "job_001", resume_name="my_resume")
	mock_cache.link_resume_to_job.assert_called_once_with("my_resume", "sec_001", "job_001", "Python开发", "XX科技")


@patch("boss_agent_cli.commands.apply.ResumeStore")
@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_with_resume_and_custom_message(mock_cache_cls, mock_auth_cls, mock_get_platform, mock_resume_store_cls):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 0, "zpData": {}}

	mock_resume_store = mock_resume_store_cls.return_value
	from boss_agent_cli.resume.models import ResumeData
	mock_resume_store.get.return_value = ResumeData(
		name="my_resume",
		title="我的简历",
		center_title=False,
		personal_info=None,
		job_intention=None,
		modules=[],
		avatar="",
	)

	runner = CliRunner()
	result = runner.invoke(cli, [
		"--json", "apply", "sec_001", "job_001",
		"--resume", "my_resume",
		"--message", "自定义消息",
	])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["greeting"] == "自定义消息"
	mock_platform.apply.assert_called_once_with("sec_001", "job_001", lid="", message="自定义消息")


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_success_for_zhilian_http_style_code(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 200, "data": {}}
	mock_platform.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "apply", "sec_001", "job_001"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	mock_cache.record_apply.assert_called_once_with("sec_001", "job_001", resume_name="")


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_zhilian_hints_use_platform_specific_commands(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 200, "data": {}}
	mock_platform.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "--platform", "zhilian", "apply", "sec_001", "job_001"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["hints"]["next_actions"][0] == "boss --platform zhilian me --section deliver"
	assert parsed["hints"]["next_actions"][1] == "boss --platform zhilian chat"


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_duplicate_is_blocked(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["apply", "sec_001", "job_001"])
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["error"]["code"] == "ALREADY_APPLIED"


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_duplicate_zhilian_hints_use_platform_specific_commands(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "--platform", "zhilian", "apply", "sec_001", "job_001"])
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["hints"]["next_actions"][0] == "boss --platform zhilian me --section deliver"
	assert parsed["hints"]["next_actions"][1] == "boss --platform zhilian chat"


@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_failure_does_not_record_local_state(mock_cache_cls, mock_auth_cls, mock_get_platform):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.apply.return_value = {"code": 1, "message": "失败"}
	mock_platform.is_success.return_value = False
	mock_platform.parse_error.return_value = ("NETWORK_ERROR", "失败")

	runner = CliRunner()
	result = runner.invoke(cli, ["apply", "sec_001", "job_001"])
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["error"]["code"] == "NETWORK_ERROR"
	mock_cache.record_apply.assert_not_called()


@patch("boss_agent_cli.commands.apply.ResumeStore")
@patch("boss_agent_cli.commands.apply.get_platform_instance")
@patch("boss_agent_cli.commands.apply.AuthManager")
@patch("boss_agent_cli.commands.apply.CacheStore")
def test_apply_resume_not_found(mock_cache_cls, mock_auth_cls, mock_get_platform, mock_resume_store_cls):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_applied.return_value = False
	mock_resume_store = mock_resume_store_cls.return_value
	mock_resume_store.get.return_value = None

	runner = CliRunner()
	result = runner.invoke(cli, ["--json", "apply", "sec_001", "job_001", "--resume", "nonexistent"])
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["error"]["code"] == "RESUME_NOT_FOUND"


def test_apply_is_exposed_in_schema():
	runner = CliRunner()
	result = runner.invoke(cli, ["schema"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert "apply" in parsed["data"]["commands"]
	assert "--resume" in str(parsed["data"]["commands"]["apply"])
	assert "--message" in str(parsed["data"]["commands"]["apply"])
