from unittest.mock import MagicMock, patch

import pytest

from boss_agent_cli.auth.browser import (
	HOME_URL,
	LOGIN_PAGE_URL,
	_NAV_TIMEOUT_MS,
	_NETWORKIDLE_GRACE_MS,
	login_via_cdp,
	login_via_browser,
	refresh_stoken,
	refresh_stoken_via_cdp,
)


def _mock_playwright_context(mock_browser: MagicMock) -> MagicMock:
	mock_chromium = MagicMock()
	mock_chromium.launch.return_value = mock_browser
	mock_playwright = MagicMock()
	mock_playwright.chromium = mock_chromium
	mock_context_manager = MagicMock()
	mock_context_manager.__enter__ = MagicMock(return_value=mock_playwright)
	mock_context_manager.__exit__ = MagicMock(return_value=False)
	return mock_context_manager


def _mock_cdp_playwright(mock_context: MagicMock) -> tuple[MagicMock, MagicMock, MagicMock]:
	mock_page = MagicMock()
	mock_context.new_page.return_value = mock_page

	mock_browser = MagicMock()
	mock_browser.contexts = [mock_context]

	mock_playwright = MagicMock()
	mock_playwright.chromium.connect_over_cdp.return_value = mock_browser

	mock_launcher = MagicMock()
	mock_launcher.start.return_value = mock_playwright
	return mock_launcher, mock_playwright, mock_page


@patch("boss_agent_cli.auth.browser.probe_cdp", return_value="ws://localhost/devtools/browser")
@patch("boss_agent_cli.auth.browser.time.sleep", return_value=None)
def test_login_via_cdp_stops_playwright_on_timeout(mock_sleep, mock_probe_cdp):
	mock_context = MagicMock()
	mock_context.cookies.return_value = []
	mock_launcher, mock_playwright, mock_page = _mock_cdp_playwright(mock_context)

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: mock_launcher):
		with pytest.raises(TimeoutError):
			login_via_cdp(timeout=1)

	mock_page.close.assert_called_once()
	mock_playwright.stop.assert_called_once()


@patch("boss_agent_cli.auth.browser._extract_stoken", return_value="fresh-stoken")
@patch("boss_agent_cli.auth.browser.time.sleep", return_value=None)
@patch("boss_agent_cli.auth.browser.probe_cdp", return_value="ws://localhost/devtools/browser")
def test_login_via_cdp_extracts_stoken_after_warming_home(mock_probe_cdp, mock_sleep, mock_extract_stoken):
	mock_context = MagicMock()
	mock_context.cookies.side_effect = [
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}],
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}, {"name": "__zp_stoken__", "value": "s", "domain": ".zhipin.com"}],
	]
	mock_launcher, mock_playwright, mock_page = _mock_cdp_playwright(mock_context)
	mock_page.evaluate.return_value = "UA"

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: mock_launcher):
		result = login_via_cdp(timeout=1, platform="zhipin")

	assert result["stoken"] == "fresh-stoken"
	assert result["user_agent"] == "UA"
	assert all(call.args[0] != LOGIN_PAGE_URL for call in mock_page.goto.call_args_list)
	mock_page.goto.assert_any_call(HOME_URL, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
	mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=_NETWORKIDLE_GRACE_MS)
	mock_extract_stoken.assert_called_once_with(mock_page)
	mock_page.close.assert_called_once()
	mock_playwright.stop.assert_called_once()


@patch("boss_agent_cli.auth.browser._extract_existing_token_via_raw_cdp")
@patch("boss_agent_cli.auth.browser.probe_cdp", return_value="ws://localhost/devtools/browser")
def test_login_via_cdp_reuses_existing_raw_cdp_token(mock_probe_cdp, mock_extract_existing):
	mock_extract_existing.return_value = {
		"cookies": {"wt2": "token", "__zp_stoken__": "fresh-stoken"},
		"stoken": "fresh-stoken",
		"user_agent": "UA",
	}

	with patch("boss_agent_cli.auth.browser._sync_playwright") as mock_sync_playwright:
		result = login_via_cdp(timeout=1, platform="zhipin")

	assert result["stoken"] == "fresh-stoken"
	assert result["user_agent"] == "UA"
	mock_extract_existing.assert_called_once_with(cdp_url=None, platform="zhipin")
	mock_sync_playwright.assert_not_called()


@patch("boss_agent_cli.auth.browser._extract_existing_token_via_raw_cdp", return_value=None)
@patch("boss_agent_cli.auth.browser.probe_cdp", return_value="ws://localhost/devtools/browser")
def test_login_via_cdp_reuses_existing_context_cookies_without_opening_login(mock_probe_cdp, mock_extract_existing):
	mock_context = MagicMock()
	mock_context.cookies.return_value = [
		{"name": "wt2", "value": "token", "domain": ".zhipin.com"},
		{"name": "__zp_stoken__", "value": "fresh-stoken", "domain": ".zhipin.com"},
	]
	mock_launcher, mock_playwright, mock_page = _mock_cdp_playwright(mock_context)
	mock_page.evaluate.return_value = "UA"

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: mock_launcher):
		result = login_via_cdp(timeout=1, platform="zhipin")

	assert result["cookies"]["wt2"] == "token"
	assert result["stoken"] == "fresh-stoken"
	assert result["user_agent"] == "UA"
	assert mock_page.goto.call_args_list == []
	mock_page.close.assert_called_once()
	mock_playwright.stop.assert_called_once()


@patch("boss_agent_cli.auth.browser.probe_cdp", return_value="ws://localhost/devtools/browser")
@patch("boss_agent_cli.auth.browser.time.sleep", return_value=None)
def test_login_via_cdp_stops_playwright_when_user_agent_extraction_fails(mock_sleep, mock_probe_cdp):
	mock_context = MagicMock()
	mock_context.cookies.side_effect = [
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}],
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}],
	]
	mock_launcher, mock_playwright, mock_page = _mock_cdp_playwright(mock_context)
	mock_page.evaluate.side_effect = RuntimeError("user agent unavailable")

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: mock_launcher):
		with pytest.raises(RuntimeError, match="user agent unavailable"):
			login_via_cdp(timeout=1)

	mock_page.close.assert_called_once()
	mock_playwright.stop.assert_called_once()


@patch("boss_agent_cli.auth.browser._extract_stoken", return_value="fresh-stoken")
@patch("boss_agent_cli.auth.browser.time.sleep", return_value=None)
def test_login_via_browser_tolerates_networkidle_timeout(mock_sleep, mock_extract_stoken):
	mock_page = MagicMock()
	mock_page.wait_for_load_state.side_effect = Exception("Timeout 30000ms exceeded")
	mock_page.evaluate.return_value = "UA"

	mock_context = MagicMock()
	mock_context.new_page.return_value = mock_page
	mock_context.cookies.side_effect = [
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}],
		[{"name": "wt2", "value": "token", "domain": ".zhipin.com"}],
	]

	mock_browser = MagicMock()
	mock_browser.new_context.return_value = mock_context

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: _mock_playwright_context(mock_browser)):
		result = login_via_browser(timeout=2, platform="zhipin")

	assert result["stoken"] == "fresh-stoken"
	assert result["user_agent"] == "UA"
	mock_browser.new_context.assert_called_once()
	mock_page.goto.assert_any_call(LOGIN_PAGE_URL, wait_until="domcontentloaded")
	mock_page.goto.assert_any_call(HOME_URL, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
	mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=_NETWORKIDLE_GRACE_MS)
	mock_extract_stoken.assert_called_once_with(mock_page)
	mock_browser.close.assert_called_once()


@patch("boss_agent_cli.auth.browser._extract_stoken", return_value="fresh-stoken")
def test_refresh_stoken_tolerates_networkidle_timeout(mock_extract_stoken):
	mock_page = MagicMock()
	mock_page.wait_for_load_state.side_effect = Exception("Timeout 30000ms exceeded")

	mock_context = MagicMock()
	mock_context.new_page.return_value = mock_page

	mock_browser = MagicMock()
	mock_browser.new_context.return_value = mock_context

	with patch("boss_agent_cli.auth.browser._sync_playwright", return_value=lambda: _mock_playwright_context(mock_browser)):
		result = refresh_stoken({"wt2": "cookie"}, "UA")

	assert result == "fresh-stoken"
	mock_browser.new_context.assert_called_once_with(user_agent="UA")
	mock_context.add_cookies.assert_called_once()
	mock_page.goto.assert_called_once_with(HOME_URL, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
	mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=_NETWORKIDLE_GRACE_MS)
	mock_extract_stoken.assert_called_once_with(mock_page)
	mock_browser.close.assert_called_once()


@patch("boss_agent_cli.auth.browser._extract_existing_token_via_raw_cdp")
def test_refresh_stoken_via_cdp_reuses_existing_raw_cdp_token(mock_extract_existing):
	mock_extract_existing.return_value = {
		"cookies": {"wt2": "token", "__zp_stoken__": "fresh-stoken"},
		"stoken": "fresh-stoken",
		"user_agent": "UA",
	}

	with patch("boss_agent_cli.auth.browser._sync_playwright") as mock_sync_playwright:
		result = refresh_stoken_via_cdp()

	assert result == "fresh-stoken"
	mock_extract_existing.assert_called_once_with(cdp_url=None, platform="zhipin")
	mock_sync_playwright.assert_not_called()
