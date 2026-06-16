import sys
import time
from typing import Any, cast

LOGIN_PAGE_URL = "https://www.zhipin.com/web/user/"
HOME_URL = "https://www.zhipin.com/"
_DEFAULT_CDP_URL = "http://localhost:9222"

# 超时常量（秒/毫秒）
_CDP_PROBE_TIMEOUT = 3           # CDP 探测 HTTP 超时（秒）
_NAV_TIMEOUT_MS = 15000          # 页面导航超时（毫秒）
_NETWORKIDLE_GRACE_MS = 3000     # 首页进入 networkidle 的额外宽限（毫秒）
_POST_LOGIN_WAIT = 3             # 登录成功后等待 cookie 传播（秒）
_STOKEN_GENERATION_WAIT = 2      # stoken 生成等待（秒）

_PLATFORM_BROWSER_CONFIG: dict[str, dict[str, str]] = {
	"zhipin": {
		"login_page_url": LOGIN_PAGE_URL,
		"home_url": HOME_URL,
		"cookie_domain": "zhipin",
		"success_cookie": "wt2",
	},
	"zhilian": {
		"login_page_url": "https://passport.zhaopin.com/v5/login",
		"home_url": "https://www.zhaopin.com/",
		"cookie_domain": "zhaopin",
		"success_cookie": "zp_token",
	},
}

_RAW_CDP_TARGET_PATTERNS: dict[str, tuple[str, ...]] = {
	"zhipin": ("/web/geek/chat", "/web/geek", "www.zhipin.com"),
	"zhilian": ("zhaopin.com",),
}


def _sync_playwright() -> Any:
	try:
		from patchright.sync_api import sync_playwright
	except ModuleNotFoundError:
		try:
			from playwright.sync_api import sync_playwright
		except ModuleNotFoundError as exc:
			raise RuntimeError("patchright / playwright 均未安装；仅在浏览器登录或浏览器兼容流需要时安装该依赖") from exc
	return sync_playwright


def _get_platform_config(platform: str) -> dict[str, str]:
	config = _PLATFORM_BROWSER_CONFIG.get(platform)
	if config is None:
		raise ValueError(f"unsupported platform: {platform}")
	return config


def _extract_zhilian_client_id(page: Any) -> str:
	try:
		return cast("str", page.evaluate("""
			() => {
				const keys = ["x-zp-client-id", "x_zp_client_id", "clientId"];
				for (const key of keys) {
					const value = window.localStorage.getItem(key) || window.sessionStorage.getItem(key);
					if (value) return value;
				}
				return '';
			}
		"""))
	except Exception:
		return ""


def _warm_home_for_runtime(page: Any, home_url: str, *, stage: str) -> None:
	"""预热首页运行时；networkidle 只尽力等待，不作为必须条件。"""
	try:
		page.goto(home_url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
	except Exception as e:
		print(f"[boss] {stage}：首页导航未在预期时间完成（{e}），继续尝试提取凭证", file=sys.stderr)
	try:
		page.wait_for_load_state("networkidle", timeout=_NETWORKIDLE_GRACE_MS)
	except Exception as e:
		print(f"[boss] {stage}：首页未进入 networkidle（{e}），继续提取凭证", file=sys.stderr)


def probe_cdp(cdp_url: str | None = None) -> str | None:
	"""探测 CDP 是否可用，返回 WebSocket URL 或 None。"""
	import httpx
	base = cdp_url or _DEFAULT_CDP_URL
	try:
		resp = httpx.get(f"{base}/json/version", timeout=_CDP_PROBE_TIMEOUT)
		return cast("str | None", resp.json().get("webSocketDebuggerUrl"))
	except (httpx.HTTPError, ValueError, KeyError):
		return None


def login_via_cdp(*, cdp_url: str | None = None, timeout: int = 120, platform: str = "zhipin") -> dict[str, Any]:
	"""
	通过 CDP 连接用户 Chrome 扫码登录。
	返回 token dict，失败抛异常。
	"""
	config = _get_platform_config(platform)
	login_page_url = config["login_page_url"]
	home_url = config["home_url"]
	cookie_domain = config["cookie_domain"]
	success_cookie = config["success_cookie"]
	ws_url = probe_cdp(cdp_url)
	if not ws_url:
		raise ConnectionError("CDP 不可用，请先运行 boss-chrome 启动带调试端口的 Chrome")

	existing_token = _extract_existing_token_via_raw_cdp(cdp_url=cdp_url, platform=platform)
	if existing_token is not None:
		print("[boss] 复用当前 CDP 页面中的有效登录态。", file=sys.stderr)
		return existing_token

	pw = _sync_playwright()().start()
	browser = pw.chromium.connect_over_cdp(ws_url)
	ctx = browser.contexts[0] if browser.contexts else browser.new_context()
	page = ctx.new_page()

	try:
		all_cookies = {c["name"]: c["value"] for c in ctx.cookies() if cookie_domain in c.get("domain", "")}
		if platform == "zhipin" and all_cookies.get(success_cookie):
			ua = page.evaluate("navigator.userAgent")
			stoken = str(all_cookies.get("__zp_stoken__", "") or "")
			if stoken:
				print("[boss] 复用当前 CDP profile 中的有效登录 cookie。", file=sys.stderr)
				return {"cookies": all_cookies, "stoken": stoken, "user_agent": ua}
			try:
				_warm_home_for_runtime(page, home_url, stage="CDP 已有登录 cookie，补全 stoken")
			except Exception:
				pass
			all_cookies = {c["name"]: c["value"] for c in ctx.cookies() if cookie_domain in c.get("domain", "")}
			stoken = _extract_stoken(page) or str(all_cookies.get("__zp_stoken__", "") or "")
			return {"cookies": all_cookies, "stoken": stoken, "user_agent": ua}

		print("[boss] 正在 CDP Chrome 中打开登录页...", file=sys.stderr)
		try:
			page.goto(
				login_page_url,
				wait_until="commit", timeout=_NAV_TIMEOUT_MS,
			)
		except Exception:
			pass

		print(f"[boss] 请在 Chrome 中扫码登录，等待中...（超时 {timeout}s）", file=sys.stderr)

		for i in range(timeout):
			time.sleep(1)
			cookies = ctx.cookies()
			success = [c for c in cookies if c["name"] == success_cookie and cookie_domain in c.get("domain", "")]
			if success:
				print("[boss] 检测到登录成功！", file=sys.stderr)
				break
			if i > 0 and i % 15 == 0:
				print(f"[boss] 等待中... {i}s", file=sys.stderr)
		else:
			raise TimeoutError(f"CDP 扫码登录超时（{timeout}s）")

		time.sleep(_POST_LOGIN_WAIT)
		try:
			_warm_home_for_runtime(page, home_url, stage="CDP 登录后回到首页")
		except Exception:
			pass
		all_cookies = {c["name"]: c["value"] for c in ctx.cookies() if cookie_domain in c.get("domain", "")}
		ua = page.evaluate("navigator.userAgent")
		stoken = _extract_stoken(page) if platform == "zhipin" else ""
		x_zp_client_id = _extract_zhilian_client_id(page) if platform == "zhilian" else ""

		result: dict[str, Any] = {"cookies": all_cookies, "stoken": stoken, "user_agent": ua}
		if x_zp_client_id:
			result["x_zp_client_id"] = x_zp_client_id
		return result
	finally:
		try:
			page.close()
		finally:
			pw.stop()


def login_via_browser(*, timeout: int = 120, platform: str = "zhipin") -> dict[str, Any]:
	"""
	使用 patchright（Playwright 兼容 fork）打开登录页。
	双重检测登录成功：监听 API 响应 + 轮询 wt2 cookie。
	"""
	config = _get_platform_config(platform)
	login_page_url = config["login_page_url"]
	home_url = config["home_url"]
	cookie_domain = config["cookie_domain"]
	success_cookie = config["success_cookie"]
	with _sync_playwright()() as p:
		browser = p.chromium.launch(headless=False)
		context = browser.new_context(
			viewport={"width": 1280, "height": 800},
			locale="zh-CN",
			timezone_id="Asia/Shanghai",
		)
		page = context.new_page()

		page.goto(login_page_url, wait_until="domcontentloaded")
		print("已打开 BOSS 直聘登录页。", file=sys.stderr)
		print(f"请扫码或手机号登录（超时 {timeout} 秒）...", file=sys.stderr)

		# 双重检测：API 响应 或 wt2 cookie 出现，任一触发即认为登录成功
		login_detected = False

		def _on_response(response: Any) -> None:
			nonlocal login_detected
			url = response.url
			if (url.startswith("https://www.zhipin.com/wapi/zppassport/qrcode/loginConfirm")
				or url.startswith("https://www.zhipin.com/wapi/zppassport/qrcode/dispatcher")
				or url.startswith("https://www.zhipin.com/wapi/zppassport/login/phoneV2")):
				login_detected = True

		page.on("response", _on_response)

		deadline = time.time() + timeout
		while time.time() < deadline and not login_detected:
			# 也通过 cookie 检测（覆盖 API 匹配不上的情况）
			try:
				cookies_list = context.cookies()
				if any(c["name"] == success_cookie and cookie_domain in c.get("domain", "") for c in cookies_list):
					login_detected = True
					break
			except Exception:
				pass
			time.sleep(1)

		if not login_detected:
			browser.close()
			raise TimeoutError(f"扫码登录超时（{timeout}秒）")

		print("检测到登录成功，正在提取凭证...", file=sys.stderr)
		time.sleep(_POST_LOGIN_WAIT)

		# 跳转主站提取完整 cookies 和 stoken
		_warm_home_for_runtime(page, home_url, stage="登录后回到首页")

		cookies_list = context.cookies()
		cookies = {c["name"]: c["value"] for c in cookies_list if cookie_domain in c.get("domain", "")}
		user_agent = page.evaluate("navigator.userAgent")
		stoken = _extract_stoken(page) if platform == "zhipin" else ""
		x_zp_client_id = _extract_zhilian_client_id(page) if platform == "zhilian" else ""

		browser.close()

	result: dict[str, Any] = {
		"cookies": cookies,
		"stoken": stoken,
		"user_agent": user_agent,
	}
	if x_zp_client_id:
		result["x_zp_client_id"] = x_zp_client_id
	return result


def refresh_stoken_via_cdp(cdp_url: str | None = None) -> str:
	"""通过 CDP Chrome 刷新 stoken（指纹一致，不会被拒）。"""
	existing_token = _extract_existing_token_via_raw_cdp(cdp_url=cdp_url, platform="zhipin")
	if existing_token is not None and existing_token.get("stoken"):
		return cast("str", existing_token["stoken"])

	ws_url = probe_cdp(cdp_url)
	if not ws_url:
		raise ConnectionError("CDP 不可用")

	pw = _sync_playwright()().start()
	browser = pw.chromium.connect_over_cdp(ws_url)
	ctx = browser.contexts[0] if browser.contexts else browser.new_context()
	page = ctx.new_page()

	try:
		page.goto(HOME_URL, wait_until="commit", timeout=15000)
	except Exception:
		pass
	time.sleep(_STOKEN_GENERATION_WAIT)

	stoken = _extract_stoken(page)
	page.close()
	pw.stop()

	if not stoken:
		raise RuntimeError("CDP 刷新 stoken 失败：页面未生成 stoken")
	return stoken


def refresh_stoken(cookies: dict[str, Any], user_agent: str) -> str:
	"""通过 headless patchright 刷新 stoken（兜底方案）。"""
	with _sync_playwright()() as p:
		browser = p.chromium.launch(headless=True)
		context = browser.new_context(user_agent=user_agent)
		context.add_cookies([
			{"name": name, "value": value, "domain": ".zhipin.com", "path": "/"}
			for name, value in cookies.items()
		])
		page = context.new_page()
		_warm_home_for_runtime(page, HOME_URL, stage="刷新 stoken")
		stoken = _extract_stoken(page)
		browser.close()

	return stoken


def _extract_stoken(page: Any) -> str:
	try:
		stoken = page.evaluate("""
			() => {
				const match = document.cookie.match(/__zp_stoken__=([^;]+)/);
				return match ? match[1] : '';
			}
		""")
		if not stoken:
			stoken = page.evaluate("() => window.__zp_stoken__ || ''")
		return cast("str", stoken)
	except Exception:
		return ""


def _extract_existing_token_via_raw_cdp(*, cdp_url: str | None = None, platform: str = "zhipin") -> dict[str, Any] | None:
	"""Best-effort: directly read credentials from an already-open user tab via raw CDP.

	This avoids `patchright.connect_over_cdp()` in environments where attach is
	flaky, while still reusing the exact Chrome profile the user is actively using.
	"""
	config = _get_platform_config(platform)
	target_ws = _pick_existing_platform_tab_ws(cdp_url or _DEFAULT_CDP_URL, platform=platform)
	if not target_ws:
		return None

	try:
		payload = _read_platform_token_via_cdp(target_ws, platform=platform)
	except Exception:
		return None

	cookies = payload.get("cookies", {})
	if not isinstance(cookies, dict) or not cookies.get(config["success_cookie"]):
		return None

	result: dict[str, Any] = {
		"cookies": cookies,
		"user_agent": str(payload.get("user_agent") or ""),
		"stoken": str(payload.get("stoken") or ""),
	}
	if platform == "zhilian":
		client_id = str(payload.get("x_zp_client_id") or "")
		if client_id:
			result["x_zp_client_id"] = client_id
	return result


def _pick_existing_platform_tab_ws(cdp_http_url: str, *, platform: str) -> str | None:
	import json as _json
	import urllib.request

	list_url = cdp_http_url.rstrip("/") + "/json"
	patterns = _RAW_CDP_TARGET_PATTERNS.get(platform, ())
	try:
		with urllib.request.urlopen(list_url, timeout=_CDP_PROBE_TIMEOUT) as resp:
			tabs = _json.load(resp)
	except Exception:
		return None

	for pattern in patterns:
		for tab in tabs:
			if tab.get("type") != "page":
				continue
			url = str(tab.get("url") or "")
			if pattern in url and tab.get("webSocketDebuggerUrl"):
				return cast("str", tab["webSocketDebuggerUrl"])
	return None


def _read_platform_token_via_cdp(target_ws: str, *, platform: str) -> dict[str, Any]:
	import json as _json

	import websockets.sync.client as _ws_client

	config = _get_platform_config(platform)
	domain_fragment = config["cookie_domain"]
	urls = [config["home_url"], config["login_page_url"]]
	if platform == "zhipin":
		urls.append("https://www.zhipin.com/web/geek/chat")

	with _ws_client.connect(target_ws, max_size=4 * 1024 * 1024) as ws:
		requests = [
			{"id": 1, "method": "Network.enable"},
			{"id": 2, "method": "Runtime.enable"},
			{"id": 3, "method": "Network.getCookies", "params": {"urls": urls}},
			{
				"id": 4,
				"method": "Runtime.evaluate",
				"params": {
					"expression": """
						(() => JSON.stringify({
							userAgent: navigator.userAgent || '',
							stoken: window.__zp_stoken__ || '',
							clientId:
								window.localStorage.getItem('x-zp-client-id') ||
								window.localStorage.getItem('x_zp_client_id') ||
								window.localStorage.getItem('clientId') ||
								window.sessionStorage.getItem('x-zp-client-id') ||
								window.sessionStorage.getItem('x_zp_client_id') ||
								window.sessionStorage.getItem('clientId') ||
								''
						}))()
					""",
					"returnByValue": True,
					"awaitPromise": True,
				},
			},
		]
		for request in requests:
			ws.send(_json.dumps(request))

		deadline = time.time() + 10.0
		cookies: dict[str, Any] = {}
		user_agent = ""
		stoken = ""
		client_id = ""
		pending = {1, 2, 3, 4}

		while pending and time.time() < deadline:
			raw = ws.recv(timeout=max(0.1, deadline - time.time()))
			msg = _json.loads(raw)
			msg_id = msg.get("id")
			if msg_id not in pending:
				continue
			if msg.get("error"):
				raise RuntimeError(f"CDP request failed: {msg['error']}")
			pending.remove(msg_id)

			if msg_id == 3:
				cookies = {
					item["name"]: item["value"]
					for item in msg.get("result", {}).get("cookies", [])
					if domain_fragment in str(item.get("domain") or "")
				}
				continue

			if msg_id == 4:
				try:
					payload = _json.loads(msg.get("result", {}).get("result", {}).get("value") or "{}")
				except Exception:
					payload = {}
				user_agent = str(payload.get("userAgent") or "")
				stoken = str(payload.get("stoken") or "")
				client_id = str(payload.get("clientId") or "")

		if pending:
			raise RuntimeError("CDP credential extraction timed out")

	return {
		"cookies": cookies,
		"user_agent": user_agent,
		"stoken": stoken or str(cookies.get("__zp_stoken__", "") or ""),
		"x_zp_client_id": client_id,
	}
