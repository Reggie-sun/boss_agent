from unittest.mock import patch, MagicMock

import httpx
import pytest

from boss_agent_cli.api.browser_client import (
	CDP_DEFAULT_URL,
	HOME_URL,
	_BROWSER_FETCH_TIMEOUT_MS,
	_CDP_CONNECT_TIMEOUT_MS,
	_HEADLESS_NETWORKIDLE_GRACE_MS,
	_NAV_TIMEOUT_MS,
	BrowserChannelUnavailable,
	BrowserSession,
)


def test_browser_session_defaults():
	session = BrowserSession(cookies={"wt2": "abc"}, user_agent="test-ua")
	assert session._is_cdp is False
	assert session._started is False
	assert session._cookies == {"wt2": "abc"}


def test_fetch_ws_url_success():
	with patch("httpx.get") as mock_get:
		mock_resp = MagicMock()
		mock_resp.json.return_value = {"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"}
		mock_get.return_value = mock_resp
		ws = BrowserSession._fetch_ws_url("http://127.0.0.1:9222")
		assert ws == "ws://127.0.0.1:9222/devtools/browser/abc"


def test_fetch_ws_url_failure():
	with patch("httpx.get", side_effect=httpx.ConnectError("connection refused")):
		ws = BrowserSession._fetch_ws_url("http://127.0.0.1:9222")
		assert ws is None


def test_fetch_ws_url_invalid_json_returns_none():
	with patch("httpx.get") as mock_get:
		mock_resp = MagicMock()
		mock_resp.json.side_effect = ValueError("invalid json")
		mock_get.return_value = mock_resp

		ws = BrowserSession._fetch_ws_url("http://127.0.0.1:9222")

		assert ws is None


def test_fetch_ws_url_missing_websocket_debugger_url_returns_none():
	with patch("httpx.get") as mock_get:
		mock_resp = MagicMock()
		mock_resp.json.return_value = {"Browser": "Chrome"}
		mock_get.return_value = mock_resp

		ws = BrowserSession._fetch_ws_url("http://127.0.0.1:9222")

		assert ws is None


def test_fetch_ws_url_non_object_json_returns_none():
	with patch("httpx.get") as mock_get:
		mock_resp = MagicMock()
		mock_resp.json.return_value = ["not", "a", "devtools", "object"]
		mock_get.return_value = mock_resp

		ws = BrowserSession._fetch_ws_url("http://127.0.0.1:9222")

		assert ws is None


def test_read_devtools_active_port_missing(tmp_path):
	with patch("boss_agent_cli.api.browser_client._CHROME_USER_DATA_CANDIDATES", [tmp_path / "nonexistent"]):
		ws = BrowserSession._read_devtools_active_port()
		assert ws is None


def test_read_devtools_active_port_found(tmp_path):
	port_file = tmp_path / "DevToolsActivePort"
	port_file.write_text("9222\n/devtools/browser/test-id\n")
	with patch("boss_agent_cli.api.browser_client._CHROME_USER_DATA_CANDIDATES", [tmp_path]):
		ws = BrowserSession._read_devtools_active_port()
		assert ws == "ws://127.0.0.1:9222/devtools/browser/test-id"


def test_close_cdp_mode_reused_context_not_closed():
	"""CDP 复用用户 context 时 close() 只关闭 page，不关闭 context"""
	session = BrowserSession(cookies={}, user_agent="")
	session._is_cdp = True
	session._own_context = False  # 复用的 context
	session._started = True
	session._page = MagicMock()
	session._context = MagicMock()
	session._browser = MagicMock()
	session._pw = MagicMock()

	session.close()

	session._page.close.assert_called_once()
	session._context.close.assert_not_called()  # 不关闭用户的 context
	session._browser.close.assert_not_called()


def test_close_cdp_mode_own_context_closed():
	"""CDP 自建 context 时 close() 关闭 page 和 context"""
	session = BrowserSession(cookies={}, user_agent="")
	session._is_cdp = True
	session._own_context = True  # 自建的 context
	session._started = True
	session._page = MagicMock()
	session._context = MagicMock()
	session._browser = MagicMock()
	session._pw = MagicMock()

	session.close()

	session._page.close.assert_called_once()
	session._context.close.assert_called_once()


def test_close_headless_mode_closes_browser():
	"""Headless 模式下 close() 关闭整个 browser"""
	session = BrowserSession(cookies={}, user_agent="")
	session._is_cdp = False
	session._started = True
	session._page = MagicMock()
	session._browser = MagicMock()
	session._pw = MagicMock()

	session.close()

	session._browser.close.assert_called_once()


def test_close_is_idempotent_when_cdp_resources_are_partial_and_raise():
	session = BrowserSession(cookies={}, user_agent="")
	session._is_cdp = True
	session._own_context = True
	session._started = True
	session._page = MagicMock()
	session._context = MagicMock()
	session._pw = MagicMock()
	session._page.close.side_effect = RuntimeError("page already closed")
	session._context.close.side_effect = RuntimeError("context already closed")
	session._pw.stop.side_effect = RuntimeError("playwright already stopped")

	session.close()
	session.close()

	assert session._started is False
	assert session._page.close.call_count == 2
	assert session._context.close.call_count == 2
	assert session._pw.stop.call_count == 2


def test_close_is_idempotent_when_headless_resources_are_partial_and_raise():
	session = BrowserSession(cookies={}, user_agent="")
	session._is_cdp = False
	session._started = True
	session._browser = MagicMock()
	session._pw = MagicMock()
	session._browser.close.side_effect = RuntimeError("browser already closed")
	session._pw.stop.side_effect = RuntimeError("playwright already stopped")

	session.close()
	session.close()

	assert session._started is False
	assert session._browser.close.call_count == 2
	assert session._pw.stop.call_count == 2


def test_try_connect_reuses_existing_context():
	"""CDP 连接应复用用户现有 context，避免创建额外浏览器状态。"""
	session = BrowserSession(cookies={"wt2": "stale-cookie"}, user_agent="")
	session._pw = MagicMock()

	mock_browser = MagicMock()
	mock_user_context = MagicMock()
	mock_browser.contexts = [mock_user_context]
	mock_page = MagicMock()
	mock_user_context.new_page.return_value = mock_page

	session._pw.chromium.connect_over_cdp.return_value = mock_browser

	result = session._try_connect("ws://localhost:9222/test")

	assert result is True
	assert session._is_cdp is True
	assert session._own_context is False  # 复用，非自建
	assert session._context is mock_user_context  # 直接使用用户 context
	# 验证：没有创建新 context
	session._pw.chromium.connect_over_cdp.assert_called_once_with(
		"ws://localhost:9222/test",
		timeout=_CDP_CONNECT_TIMEOUT_MS,
	)
	mock_browser.new_context.assert_not_called()
	# 验证：不会把本地旧 cookie 回灌到用户 context，避免污染真实登录态
	mock_user_context.add_cookies.assert_not_called()
	# 验证：page 在用户 context 中创建
	mock_user_context.new_page.assert_called_once()


def test_try_connect_creates_new_context_when_none_exists():
	"""CDP 连接无已存在 context 时创建新 context 并注入 cookies"""
	session = BrowserSession(cookies={"wt2": "abc"}, user_agent="")
	session._pw = MagicMock()

	mock_browser = MagicMock()
	mock_browser.contexts = []  # 无已存在 context
	mock_new_context = MagicMock()
	mock_browser.new_context.return_value = mock_new_context
	mock_page = MagicMock()
	mock_new_context.new_page.return_value = mock_page

	session._pw.chromium.connect_over_cdp.return_value = mock_browser

	result = session._try_connect("ws://localhost:9222/test")

	assert result is True
	assert session._is_cdp is True
	assert session._own_context is True  # 自建
	session._pw.chromium.connect_over_cdp.assert_called_once_with(
		"ws://localhost:9222/test",
		timeout=_CDP_CONNECT_TIMEOUT_MS,
	)
	# 验证：创建了新 context
	mock_browser.new_context.assert_called_once()
	# 验证：cookies 被注入
	mock_new_context.add_cookies.assert_called_once()
	cookies_arg = mock_new_context.add_cookies.call_args[0][0]
	assert any(c["name"] == "wt2" for c in cookies_arg)


def test_start_headless_tolerates_networkidle_timeout():
	"""Headless 预热不应因 networkidle 等待超时而直接失败。"""
	logger = MagicMock()
	session = BrowserSession(cookies={"wt2": "abc"}, user_agent="UA", logger=logger)
	session._pw = MagicMock()

	mock_browser = MagicMock()
	mock_context = MagicMock()
	mock_page = MagicMock()
	mock_page.wait_for_load_state.side_effect = Exception("Timeout 30000ms exceeded")
	mock_context.new_page.return_value = mock_page
	mock_browser.new_context.return_value = mock_context
	session._pw.chromium.launch.return_value = mock_browser

	session._start_headless()

	assert session._started is True
	assert session._is_cdp is False
	mock_page.goto.assert_called_once_with(
		HOME_URL,
		wait_until="domcontentloaded",
		timeout=_NAV_TIMEOUT_MS,
	)
	mock_page.wait_for_load_state.assert_called_once_with(
		"networkidle",
		timeout=_HEADLESS_NETWORKIDLE_GRACE_MS,
	)
	logger.info.assert_any_call("[boss] CDP 不可用（提示：需以 --remote-debugging-port=9222 启动 Chrome），降级到 headless patchright")
	assert any(
		"headless 首页未进入 networkidle" in call.args[0]
		for call in logger.info.call_args_list
	)


def test_ensure_started_fails_closed_when_bridge_and_cdp_fail():
	session = BrowserSession(cookies={}, user_agent="")
	mock_pw = MagicMock()

	with (
		patch.object(session, "_try_bridge", return_value=False) as mock_try_bridge,
		patch("boss_agent_cli.api.browser_client._sync_playwright") as mock_sync_playwright,
		patch.object(session, "_try_cdp", return_value=False) as mock_try_cdp,
		patch.object(session, "_start_headless") as mock_start_headless,
	):
		mock_sync_playwright.return_value.return_value.start.return_value = mock_pw

		with pytest.raises(BrowserChannelUnavailable):
			session._ensure_started()

	assert session._started is False
	assert session._pw is None
	mock_try_bridge.assert_called_once()
	mock_sync_playwright.assert_called_once()
	mock_try_cdp.assert_called_once()
	mock_pw.stop.assert_called_once()
	mock_start_headless.assert_not_called()


def test_ensure_started_prefers_cdp_over_bridge_when_available():
	session = BrowserSession(cookies={}, user_agent="")
	mock_pw = MagicMock()

	def fake_sync_playwright():
		return MagicMock(start=MagicMock(return_value=mock_pw))
	fake_sync_playwright.__module__ = "playwright.sync_api"

	with (
		patch.object(session, "_try_bridge", return_value=True) as mock_try_bridge,
		patch("boss_agent_cli.api.browser_client._sync_playwright", return_value=fake_sync_playwright) as mock_sync_playwright,
		patch.object(session, "_try_cdp", return_value=True) as mock_try_cdp,
		patch.object(session, "_start_headless") as mock_start_headless,
	):
		session._ensure_started()

	mock_sync_playwright.assert_called_once()
	mock_try_cdp.assert_called_once()
	mock_try_bridge.assert_not_called()
	mock_pw.stop.assert_not_called()
	mock_start_headless.assert_not_called()


def test_ensure_started_falls_back_to_bridge_after_cdp_fails():
	session = BrowserSession(cookies={}, user_agent="")
	mock_pw = MagicMock()

	def fake_sync_playwright():
		return MagicMock(start=MagicMock(return_value=mock_pw))
	fake_sync_playwright.__module__ = "playwright.sync_api"

	with (
		patch.object(session, "_try_bridge", return_value=True) as mock_try_bridge,
		patch("boss_agent_cli.api.browser_client._sync_playwright", return_value=fake_sync_playwright) as mock_sync_playwright,
		patch.object(session, "_try_cdp", return_value=False) as mock_try_cdp,
		patch.object(session, "_start_headless") as mock_start_headless,
	):
		session._ensure_started()

	mock_sync_playwright.assert_called_once()
	mock_try_cdp.assert_called_once()
	mock_try_bridge.assert_called_once()
	mock_pw.stop.assert_called_once()
	mock_start_headless.assert_not_called()


def test_ensure_started_skips_patchright_cdp_attach_and_fails_closed():
	session = BrowserSession(cookies={}, user_agent="")
	mock_pw = MagicMock()

	def fake_sync_playwright():
		return MagicMock(start=MagicMock(return_value=mock_pw))
	fake_sync_playwright.__module__ = "patchright.sync_api"

	with (
		patch.object(session, "_try_bridge", return_value=False) as mock_try_bridge,
		patch("boss_agent_cli.api.browser_client._sync_playwright", return_value=fake_sync_playwright) as mock_sync_playwright,
		patch.object(session, "_try_cdp", return_value=True) as mock_try_cdp,
		patch.object(session, "_start_headless") as mock_start_headless,
	):
		with pytest.raises(BrowserChannelUnavailable):
			session._ensure_started()

	mock_try_bridge.assert_called_once()
	mock_sync_playwright.assert_called_once()
	mock_try_cdp.assert_not_called()
	mock_pw.stop.assert_called_once()
	mock_start_headless.assert_not_called()


def test_try_cdp_attempts_http_ws_and_devtools_urls_before_falling_back():
	session = BrowserSession(cookies={}, user_agent="", cdp_url="http://127.0.0.1:9333")

	with (
		patch.object(session, "_try_connect", return_value=False) as mock_try_connect,
		patch.object(BrowserSession, "_fetch_ws_url", side_effect=[None, "ws://127.0.0.1:9222/devtools/browser/default"]) as mock_fetch_ws_url,
		patch.object(BrowserSession, "_read_devtools_active_port", return_value="ws://127.0.0.1:9222/devtools/browser/file") as mock_read_port,
	):
		result = session._try_cdp()

	assert result is False
	mock_read_port.assert_called_once()
	assert [call.args[0] for call in mock_try_connect.call_args_list] == [
		"http://127.0.0.1:9333",
		CDP_DEFAULT_URL,
		"ws://127.0.0.1:9222/devtools/browser/default",
		"ws://127.0.0.1:9222/devtools/browser/file",
	]
	assert [call.args[0] for call in mock_fetch_ws_url.call_args_list] == [
		"http://127.0.0.1:9333",
		CDP_DEFAULT_URL,
	]


def test_try_cdp_deduplicates_devtools_active_port_url():
	session = BrowserSession(cookies={}, user_agent="")

	with (
		patch.object(session, "_try_connect", return_value=False) as mock_try_connect,
		patch.object(BrowserSession, "_fetch_ws_url", return_value="ws://127.0.0.1:9222/devtools/browser/default") as mock_fetch_ws_url,
		patch.object(BrowserSession, "_read_devtools_active_port", return_value="ws://127.0.0.1:9222/devtools/browser/default") as mock_read_port,
	):
		result = session._try_cdp()

	assert result is False
	mock_read_port.assert_called_once()
	assert [call.args[0] for call in mock_try_connect.call_args_list] == [
		CDP_DEFAULT_URL,
		"ws://127.0.0.1:9222/devtools/browser/default",
	]
	assert [call.args[0] for call in mock_fetch_ws_url.call_args_list] == [CDP_DEFAULT_URL]


def test_request_returns_browser_evaluation_json_and_marks_throttle():
	session = BrowserSession(cookies={}, user_agent="")
	session._started = True
	session._page = MagicMock()
	session._throttle = MagicMock()
	expected = {"code": 0, "zpData": {"jobs": []}}
	session._page.evaluate.return_value = expected

	result = session.request(
		"POST",
		"https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
		params={"query": "python", "page": 1},
		data={"city": "101020100"},
	)

	assert result == expected
	session._throttle.wait.assert_called_once()
	session._throttle.mark.assert_called_once()
	evaluate_script, evaluate_args = session._page.evaluate.call_args.args
	assert "fetch(fetchUrl, options)" in evaluate_script
	assert evaluate_args == {
		"method": "POST",
		"url": "https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
		"params": {"query": "python", "page": 1},
		"data": {"city": "101020100"},
		"referer": "https://www.zhipin.com/web/geek/job",
		"timeoutMs": _BROWSER_FETCH_TIMEOUT_MS,
	}


def test_request_passes_fetch_timeout_to_browser_evaluation():
	session = BrowserSession(cookies={}, user_agent="")
	session._started = True
	session._page = MagicMock()
	session._throttle = MagicMock()
	session._page.evaluate.return_value = {"code": -1, "message": "browser fetch timeout after 30000ms", "zpData": {}}

	session.request(
		"GET",
		"https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
		params={"query": "rag"},
	)

	evaluate_script, evaluate_args = session._page.evaluate.call_args.args
	assert "AbortController" in evaluate_script
	assert "setTimeout" in evaluate_script
	assert "clearTimeout(timeoutId)" in evaluate_script
	assert evaluate_args["timeoutMs"] == _BROWSER_FETCH_TIMEOUT_MS


def test_request_sets_fetch_referrer_option_instead_of_forbidden_header():
	session = BrowserSession(cookies={}, user_agent="")
	session._started = True
	session._page = MagicMock()
	session._throttle = MagicMock()
	session._page.evaluate.return_value = {"code": 0, "zpData": {}}

	session.request(
		"POST",
		"https://www.zhipin.com/wapi/zpgeek/friend/add.json",
		data={"securityId": "sec_1", "jobId": "job_1"},
	)

	evaluate_script, evaluate_args = session._page.evaluate.call_args.args
	assert "referrer: referer" in evaluate_script
	assert "'Referer': referer" not in evaluate_script
	assert evaluate_args["referer"] == "https://www.zhipin.com/web/geek/chat"


def test_request_retries_when_browser_evaluation_context_is_destroyed():
	session = BrowserSession(cookies={}, user_agent="")
	session._started = True
	session._page = MagicMock()
	session._throttle = MagicMock()
	expected = {"code": 0, "zpData": {"jobs": [{"securityId": "abc"}]}}
	session._page.evaluate.side_effect = [
		Exception("Page.evaluate: Execution context was destroyed, most likely because of a navigation."),
		expected,
	]

	result = session.request(
		"GET",
		"https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
		params={"query": "AI Agent"},
	)

	assert result == expected
	assert session._page.evaluate.call_count == 2
	session._page.wait_for_load_state.assert_called_once_with("domcontentloaded", timeout=5000)
	session._throttle.mark.assert_called_once()


def test_request_returns_failed_fetch_when_browser_evaluation_context_keeps_navigating():
	session = BrowserSession(cookies={}, user_agent="")
	session._started = True
	session._page = MagicMock()
	session._throttle = MagicMock()
	session._page.evaluate.side_effect = [
		Exception("Page.evaluate: Execution context was destroyed, most likely because of a navigation."),
		Exception("Cannot find context with specified id"),
		Exception("Page.evaluate: Execution context was destroyed, most likely because of a navigation."),
	]

	result = session.request(
		"GET",
		"https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
		params={"query": "RAG", "city": "101210100", "salary": "405"},
	)

	assert result == {"code": -1, "message": "Failed to fetch", "zpData": {}}
	assert session._page.evaluate.call_count == 3
	assert session._page.wait_for_load_state.call_count == 3
	session._throttle.mark.assert_called_once()
