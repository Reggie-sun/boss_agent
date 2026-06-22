"""commands/greet.py 覆盖率补齐测试。

覆盖 greet 成功路径、hook veto、batch-greet 完整执行链、rate-limit 停止、greet-limit 停止、失败重试。
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from boss_agent_cli.main import cli


_DEFAULT_AGENT_GREET_MESSAGE = "我是候选人的求职助理 Agent，您好，我对该岗位很感兴趣，希望能和您聊一聊。"


def _ctx_mock(mock_cls):
	instance = mock_cls.return_value
	instance.__enter__ = lambda self: self
	instance.__exit__ = lambda self, *a: None
	instance.unwrap_data.side_effect = lambda response: response.get("zpData") if "zpData" in response else response.get("data")
	return instance


def _make_raw_job(
	name: str = "Go 开发",
	security_id: str = "sec_x",
	welfare: list[str] | None = None,
	brand_scale: str = "100-499人",
) -> dict:
	return {
		"encryptJobId": f"job_{security_id}",
		"jobName": name,
		"brandName": "TestCo",
		"salaryDesc": "20K",
		"cityName": "北京",
		"areaDistrict": "海淀区",
		"jobExperience": "3-5年",
		"jobDegree": "本科",
		"skills": ["Golang"],
		"welfareList": welfare or [],
		"brandIndustry": "互联网",
		"brandScaleName": brand_scale,
		"brandStageName": "A轮",
		"bossName": "李",
		"bossTitle": "HR",
		"bossOnline": True,
		"securityId": security_id,
	}


# ── greet 成功路径 ─────────────────────────────────────────


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_greet_success_renders_message_and_records_cache(mock_cache_cls, mock_auth_cls, mock_get_platform, legacy_args):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.greet.return_value = {"code": 0, "zpData": {}}
	mock_platform.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "greet", "sec_001", "job_001"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["security_id"] == "sec_001"
	assert parsed["data"]["job_id"] == "job_001"
	assert "打招呼成功" in parsed["data"]["message"]

	mock_platform.greet.assert_called_once_with("sec_001", "job_001", _DEFAULT_AGENT_GREET_MESSAGE)
	mock_cache.record_greet.assert_called_once_with("sec_001", "job_001")


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_greet_custom_message_discloses_agent(mock_cache_cls, mock_auth_cls, mock_get_platform, legacy_args):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.greet.return_value = {"code": 0, "zpData": {}}
	mock_platform.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[*legacy_args, "greet", "sec_001", "job_001", "--message", "您好，对这个岗位感兴趣。"],
	)

	assert result.exit_code == 0
	mock_platform.greet.assert_called_once_with(
		"sec_001",
		"job_001",
		"我是候选人的求职助理 Agent，您好，对这个岗位感兴趣。",
	)


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_greet_custom_message_keeps_existing_agent_disclosure(mock_cache_cls, mock_auth_cls, mock_get_platform, legacy_args):
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_platform = _ctx_mock(mock_get_platform)
	mock_platform.greet.return_value = {"code": 0, "zpData": {}}
	mock_platform.is_success.return_value = True
	message = "我是候选人的求职助理 Agent，您好，对这个岗位感兴趣。"

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[*legacy_args, "greet", "sec_001", "job_001", "--message", message],
	)

	assert result.exit_code == 0
	mock_platform.greet.assert_called_once_with("sec_001", "job_001", message)


# Note: hook veto 分支已由 tests/test_hooks.py 独立覆盖，Click runner
# 不便注入 ctx.obj["hooks"]，此处不重复测试。


# ── batch-greet 真实执行路径 ─────────────────────────────


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_success_all(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, legacy_args):
	"""2 个职位全部打招呼成功。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("Go 1", "sec_1"), _make_raw_job("Go 2", "sec_2")]}
	}
	mock_client.greet.return_value = {"code": 0, "zpData": {}}
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "golang", "--count", "2"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["total_greeted"] == 2
	assert parsed["data"]["total_failed"] == 0
	assert len(parsed["data"]["greeted"]) == 2
	# 应调用 2 次 greet + 2 次 record_greet
	assert mock_client.greet.call_count == 2
	assert [call.args for call in mock_client.greet.call_args_list] == [
		("sec_1", "job_sec_1", _DEFAULT_AGENT_GREET_MESSAGE),
		("sec_2", "job_sec_2", _DEFAULT_AGENT_GREET_MESSAGE),
	]
	assert mock_cache.record_greet.call_count == 2
	mock_time.sleep.assert_called_once()


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_progress_json_reports_current_candidate(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
	mock_time,
	legacy_args,
):
	"""--progress-json 输出当前正在处理第几个候选，供前端显示真实进度。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("Go 1", "sec_1"), _make_raw_job("Go 2", "sec_2")]}
	}
	mock_client.greet.return_value = {"code": 0, "zpData": {}}
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[*legacy_args, "batch-greet", "golang", "--count", "2", "--progress-json"],
	)

	assert result.exit_code == 0, result.output
	events = [json.loads(line) for line in result.stderr.splitlines() if line.strip().startswith("{")]
	assert [event["current"] for event in events] == [1, 2]
	assert [event["total"] for event in events] == [2, 2]
	assert events[0]["title"] == "Go 1"
	assert events[0]["company"] == "TestCo"


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_dry_run_paginates_until_requested_count(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""Regression: Agent 自动 count > 1 时不能只看第一页的 1 个候选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.side_effect = [
		{
			"zpData": {
				"hasMore": True,
				"jobList": [_make_raw_job("Go 1", "sec_1")],
			},
		},
		{
			"zpData": {
				"hasMore": False,
				"jobList": [_make_raw_job("Go 2", "sec_2"), _make_raw_job("Go 3", "sec_3")],
			},
		},
	]
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "golang", "--count", "3", "--dry-run"])

	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 3
	assert [item["security_id"] for item in parsed["data"]["candidates"]] == ["sec_1", "sec_2", "sec_3"]
	assert mock_client.search_jobs.call_count == 2


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_dry_run_keeps_extended_scan_floor_for_local_filters(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
):
	"""本地筛选 count=1 时仍要允许继续翻页，避免第一页误空。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.side_effect = [
		{
			"zpData": {
				"hasMore": True,
				"jobList": [_make_raw_job("Go 1", "sec_1", brand_scale="100-499人")],
			},
		},
		{
			"zpData": {
				"hasMore": False,
				"jobList": [_make_raw_job("Go 2", "sec_2", brand_scale="10000人以上")],
			},
		},
	]
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "python", "--scale", "10000人以上", "--count", "1", "--dry-run"])

	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert [item["security_id"] for item in parsed["data"]["candidates"]] == ["sec_2"]
	assert mock_client.search_jobs.call_count == 2


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_rate_limited_stops_remaining(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, legacy_args):
	"""第 1 个成功，第 2 个 RATE_LIMITED 应中止剩余。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [
			_make_raw_job("A", "s1"),
			_make_raw_job("B", "s2"),
			_make_raw_job("C", "s3"),
		]}
	}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			return {"code": 0, "zpData": {}}
		raise RuntimeError("RATE_LIMITED 请求频率过高")

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "test", "--count", "3"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["stopped_reason"] == "RATE_LIMITED"


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_token_refresh_failed_stops_remaining(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, legacy_args):
	"""平台环境异常应立即中止，不继续把剩余候选打成失败。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [
			_make_raw_job("A", "s1"),
			_make_raw_job("B", "s2"),
			_make_raw_job("C", "s3"),
		]}
	}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			return {"code": 0, "zpData": {}}
		if sid == "s2":
			return {"code": 37, "message": "您的环境存在异常."}
		return {"code": 0, "zpData": {}}

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.side_effect = lambda response: response.get("code", 0) == 0
	mock_client.parse_error.side_effect = lambda response: (
		"TOKEN_REFRESH_FAILED",
		response.get("message", ""),
	)
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "test", "--count", "3"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 0
	assert parsed["data"]["stopped_reason"] == "TOKEN_REFRESH_FAILED"
	assert "环境存在异常" in parsed["data"]["stopped_error"]
	assert mock_client.greet.call_count == 2


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_auth_expired_preserves_prior_success(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, legacy_args):
	"""第 1 个成功后遇到 AUTH_EXPIRED，应保留成功数并停止剩余候选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [
			_make_raw_job("A", "s1"),
			_make_raw_job("B", "s2"),
			_make_raw_job("C", "s3"),
		]}
	}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			return {"code": 0, "zpData": {}}
		return {"code": 401, "message": "登录态过期"}

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.side_effect = lambda response: response.get("code", 0) == 0
	mock_client.parse_error.side_effect = lambda response: (
		"AUTH_EXPIRED",
		response.get("message", ""),
	)
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "test", "--count", "3"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 0
	assert parsed["data"]["stopped_reason"] == "AUTH_EXPIRED"
	assert "登录态过期" in parsed["data"]["stopped_error"]
	assert mock_client.greet.call_count == 2


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_browser_fetch_network_error_preserves_prior_success(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, legacy_args):
	"""第 1 个成功后遇到 browser fetch NETWORK_ERROR，应保留成功数并停止剩余候选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [
			_make_raw_job("A", "s1"),
			_make_raw_job("B", "s2"),
			_make_raw_job("C", "s3"),
		]}
	}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			return {"code": 0, "zpData": {}}
		return {"code": 500, "message": "Failed to fetch"}

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.side_effect = lambda response: response.get("code", 0) == 0
	mock_client.parse_error.side_effect = lambda response: (
		"NETWORK_ERROR",
		"平台请求失败：浏览器 fetch 未完成，请重试；如果连续失败，请刷新登录状态。",
	)
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "test", "--count", "3"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 0
	assert parsed["data"]["stopped_reason"] == "NETWORK_ERROR"
	assert "浏览器 fetch 未完成" in parsed["data"]["stopped_error"]
	assert mock_client.greet.call_count == 2


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_greet_limit_stops_remaining(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time):
	"""GREET_LIMIT 错误关键字也应触发停止。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("A", "s1"), _make_raw_job("B", "s2")]}
	}
	mock_client.greet.side_effect = RuntimeError("GREET_LIMIT 今日上限已达")
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "test", "--count", "2"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["stopped_reason"] == "GREET_LIMIT"
	assert parsed["data"]["total_greeted"] == 0


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_network_error_retries_once_then_skips(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time):
	"""普通网络错误：第一次重试仍失败 → 跳过该职位，继续下一个。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("A", "s1"), _make_raw_job("B", "s2")]}
	}
	# s1: 两次都失败（非 RATE_LIMITED / GREET_LIMIT）
	# s2: 成功
	call_counts = {"s1": 0}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			call_counts["s1"] += 1
			raise ConnectionError("network timeout")
		return {"code": 0, "zpData": {}}

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "test", "--count", "2"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 1
	# s1 应该被重试过 1 次（共调用 2 次）
	assert call_counts["s1"] == 2
	# s2 成功
	assert any(r["security_id"] == "s2" for r in parsed["data"]["greeted"])


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_network_error_first_retry_succeeds(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time):
	"""第一次失败但重试成功，应算 success 不是 failed。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("A", "s1")]}
	}

	call_count = {"n": 0}

	def greet_side_effect(sid, jid, msg=""):
		call_count["n"] += 1
		if call_count["n"] == 1:
			raise ConnectionError("transient")
		return {"code": 0, "zpData": {}}  # 第二次成功

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "test", "--count", "1"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 0


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_skips_already_greeted(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time):
	"""已打过招呼的职位应被 candidates 过滤掉。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	# s1 已打过招呼，s2 没
	mock_cache.is_greeted.side_effect = lambda sid: sid == "s1"
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("A", "s1"), _make_raw_job("B", "s2")]}
	}
	mock_client.greet.return_value = None
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "test", "--count", "5"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	# 只 s2 被打招呼
	assert parsed["data"]["total_greeted"] == 1
	assert mock_client.greet.call_count == 1
	assert mock_client.greet.call_args.args[0] == "s2"


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_reports_when_all_matches_already_greeted(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
	mock_time,
):
	"""搜索有结果但都已开聊时，不应误报为筛选没有岗位。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = True
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("A", "s1"), _make_raw_job("B", "s2")]}
	}
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "RAG", "--count", "10"])
	assert result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is False
	assert parsed["error"]["code"] == "NO_UNGREETED_CANDIDATES"
	assert "都已开聊" in parsed["error"]["message"]
	assert mock_client.greet.call_count == 0


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_respects_count_cap(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time):
	"""--count 最大 150，即使搜出 160 条也只处理 150 条。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job(f"Job {i}", f"s{i}") for i in range(160)]}
	}
	mock_client.greet.return_value = None
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "test", "--count", "999", "--dry-run"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	# --count 会被 cap 到 150
	assert parsed["data"]["count"] == 150


@patch("boss_agent_cli.commands.greet.random.uniform", return_value=1.0)
@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_uses_random_delay_between_successes(mock_cache_cls, mock_auth_cls, mock_client_cls, mock_time, mock_uniform):
	"""每条成功开聊之间使用 1~10s 随机间隔。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [_make_raw_job("Go 1", "sec_1"), _make_raw_job("Go 2", "sec_2")]}
	}
	mock_client.greet.return_value = {"code": 0, "zpData": {}}
	mock_client.is_success.return_value = True
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "golang", "--count", "2"])
	assert result.exit_code == 0
	mock_uniform.assert_called_with(1.0, 10.0)
	mock_time.sleep.assert_called_with(1.0)


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_welfare_filter_dry_run(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""batch-greet 支持复用福利筛选 pipeline。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [
				_make_raw_job("Go 双休", "sec_1", welfare=["双休"]),
				_make_raw_job("Go 单休", "sec_2", welfare=["五险一金"]),
			],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "golang", "--welfare", "双休", "--count", "2", "--dry-run"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_1"
	assert "welfare_match" in parsed["data"]["candidates"][0]


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_welfare_keeps_software_jobs_when_filtering_internet(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
):
	"""RAG 岗常见计算机软件标签不应被 broad 互联网筛选误杀。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	software_job = _make_raw_job("RAG 工程师", "sec_software", welfare=["周末双休"])
	software_job["brandIndustry"] = "计算机软件"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [software_job],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"batch-greet",
			"RAG",
			"--industry",
			"互联网",
			"--welfare",
			"双休",
			"--count",
			"1",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_software"
	assert "双休(标签)" in parsed["data"]["candidates"][0]["welfare_match"]


@patch("boss_agent_cli.commands.greet.time")
@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_environment_abnormal_without_explicit_code_stops_as_token_refresh_failed(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
	mock_time,
	legacy_args,
):
	"""message-only 的环境异常也应归到 token 刷新失败，而不是风控。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mock_client.search_jobs.return_value = {
		"zpData": {"jobList": [
			_make_raw_job("A", "s1"),
			_make_raw_job("B", "s2"),
			_make_raw_job("C", "s3"),
		]}
	}

	def greet_side_effect(sid, jid, msg=""):
		if sid == "s1":
			return {"code": 0, "zpData": {}}
		if sid == "s2":
			return {"code": -1, "message": "您的环境存在异常."}
		return {"code": 0, "zpData": {}}

	mock_client.greet.side_effect = greet_side_effect
	mock_client.is_success.side_effect = lambda response: response.get("code", 0) == 0
	mock_client.parse_error.side_effect = lambda response: ("UNKNOWN", response.get("message", ""))
	mock_time.sleep = MagicMock()

	runner = CliRunner()
	result = runner.invoke(cli, [*legacy_args, "batch-greet", "test", "--count", "3"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["data"]["total_greeted"] == 1
	assert parsed["data"]["total_failed"] == 0
	assert parsed["data"]["stopped_reason"] == "TOKEN_REFRESH_FAILED"
	assert "环境存在异常" in parsed["data"]["stopped_error"]
	assert mock_client.greet.call_count == 2


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_welfare_keeps_deep_learning_jobs_when_filtering_ai(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
):
	"""深度学习卡片标签应兼容人工智能筛选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	deep_learning_job = _make_raw_job("深度学习 RAG 工程师", "sec_deep", welfare=["五天工作制"])
	deep_learning_job["brandIndustry"] = "深度学习"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [deep_learning_job],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"batch-greet",
			"RAG",
			"--industry",
			"人工智能",
			"--welfare",
			"双休",
			"--count",
			"1",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_deep"
	assert "双休(标签)" in parsed["data"]["candidates"][0]["welfare_match"]


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_accepts_local_industry_direction_choice(
	mock_cache_cls,
	mock_auth_cls,
	mock_client_cls,
):
	"""Regression: 前端传机器学习时不能在 Click 参数层直接失败。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	ml_job = _make_raw_job("机器学习 RAG 工程师", "sec_ml")
	ml_job["brandIndustry"] = "机器学习"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [ml_job],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"batch-greet",
			"RAG",
			"--industry",
			"机器学习",
			"--count",
			"1",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_ml"


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_custom_salary_range_uses_local_filter(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""BOSS 未映射的新薪资范围走本地预筛，避免未知 code 直接打空。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	low_salary = _make_raw_job("低薪", "sec_low")
	low_salary["salaryDesc"] = "5-7K"
	high_salary = _make_raw_job("匹配", "sec_high")
	high_salary["salaryDesc"] = "10-12K"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [low_salary, high_salary],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "golang", "--salary", "9-12K", "--count", "2", "--dry-run"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_high"


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_custom_salary_range_keeps_overlapping_salary(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""12-24K 应保留 15-30K 这类重叠薪资，避免筛选误报无候选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	below_salary = _make_raw_job("低薪", "sec_low")
	below_salary["salaryDesc"] = "5-7K"
	overlap_salary = _make_raw_job("重叠", "sec_overlap")
	overlap_salary["salaryDesc"] = "15-30K"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [below_salary, overlap_salary],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(cli, ["batch-greet", "RAG", "--salary", "12-24K", "--count", "2", "--dry-run"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_overlap"


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_applies_company_and_job_type_filters(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""batch-greet 普通筛选也要复用本地预筛，避免直接开聊不匹配职位。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mismatch = _make_raw_job("不匹配", "sec_bad")
	mismatch["brandIndustry"] = "金融"
	mismatch["brandScaleName"] = "20-99人"
	mismatch["brandStageName"] = "未融资"
	mismatch["jobTypeName"] = "实习"
	match = _make_raw_job("匹配", "sec_good")
	match["jobTypeName"] = "全职"
	mock_client.search_jobs.return_value = {
		"zpData": {
			"hasMore": False,
			"jobList": [mismatch, match],
		},
	}
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"batch-greet",
			"golang",
			"--industry",
			"互联网",
			"--scale",
			"100-499人",
			"--stage",
			"A轮",
			"--job-type",
			"全职",
			"--count",
			"2",
			"--dry-run",
		],
	)
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_good"


@patch("boss_agent_cli.commands.greet.get_platform_instance")
@patch("boss_agent_cli.commands.greet.AuthManager")
@patch("boss_agent_cli.commands.greet.CacheStore")
def test_batch_greet_scans_more_pages_for_company_filters(mock_cache_cls, mock_auth_cls, mock_client_cls):
	"""本地公司筛选可能筛空第一页，应继续翻页寻找可开聊候选。"""
	mock_cache = _ctx_mock(mock_cache_cls)
	mock_cache.is_greeted.return_value = False
	mock_client = _ctx_mock(mock_client_cls)
	mismatch = _make_raw_job("第一页不匹配", "sec_bad")
	mismatch["cityName"] = "广州"
	mismatch["brandIndustry"] = "金融"
	match = _make_raw_job("第二页匹配", "sec_good")
	match["cityName"] = "广州"
	match["brandIndustry"] = "人工智能"
	mock_client.search_jobs.side_effect = [
		{
			"zpData": {
				"hasMore": True,
				"jobList": [mismatch],
			},
		},
		{
			"zpData": {
				"hasMore": False,
				"jobList": [match],
			},
		},
	]
	mock_client.is_success.return_value = True

	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"batch-greet",
			"AI Agent",
			"--city",
			"广州",
			"--industry",
			"人工智能",
			"--job-type",
			"全职",
			"--count",
			"3",
			"--dry-run",
		],
	)
	assert result.exit_code == 0, result.output
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["count"] == 1
	assert parsed["data"]["candidates"][0]["security_id"] == "sec_good"
	assert mock_client.search_jobs.call_count == 2
