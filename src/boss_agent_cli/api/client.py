import atexit
import random
import time
import weakref
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast

import httpx

from boss_agent_cli.api import endpoints
from boss_agent_cli.api.httpx_helpers import (
	add_stoken_to_get_params,
	browser_headers,
	merge_response_cookies,
	referer_header,
)
from boss_agent_cli.api.throttle import RequestThrottle

if TYPE_CHECKING:
	from boss_agent_cli.api.browser_client import BrowserSession
	from boss_agent_cli.auth.manager import AuthManager

_MAX_RETRIES = 3

# atexit safeguard: close any BossClient instances not explicitly closed
_OPEN_CLIENTS: weakref.WeakSet["BossClient"] = weakref.WeakSet()


def _close_open_clients() -> None:
	for client in list(_OPEN_CLIENTS):
		try:
			client.close()
		except Exception:
			pass


atexit.register(_close_open_clients)


class AuthError(Exception):
	pass


class AccountRiskError(Exception):
	"""BOSS 直聘风控拦截（code 36）：检测到异常行为。"""

	def __init__(self, message: str = "", is_cdp: bool = False):
		self.is_cdp = is_cdp
		super().__init__(message)


class BossClient:
	"""Hybrid API client: browser channel for high-risk ops, httpx for low-risk ops."""

	def __init__(self, auth_manager: "AuthManager", *, delay: tuple[float, float] = (1.5, 3.0), cdp_url: str | None = None) -> None:
		self._auth = auth_manager
		self._delay = delay
		self._client: httpx.Client | None = None
		self._browser_session: "BrowserSession | None" = None
		self._throttle = RequestThrottle(delay)
		self._cdp_url = cdp_url
		self._closed = False
		_OPEN_CLIENTS.add(self)

	def _get_client(self) -> httpx.Client:
		if self._client is None:
			token = self._auth.get_token()
			headers = browser_headers(endpoints.DEFAULT_HEADERS, token)
			self._client = httpx.Client(
				base_url=endpoints.BASE_URL,
				cookies=token.get("cookies", {}),
				headers=headers,
				follow_redirects=True,
				timeout=30,
			)
		return self._client

	def _get_browser(self) -> "BrowserSession":
		if self._browser_session is None:
			from boss_agent_cli.api.browser_client import BrowserSession
			token = self._auth.get_token()
			self._browser_session = BrowserSession(
				cookies=token.get("cookies", {}),
				user_agent=token.get("user_agent", ""),
				delay=self._delay,
				cdp_url=self._cdp_url,
				logger=getattr(self._auth, '_logger', None),
			)
		return self._browser_session

	# ── Anti-detection delays (httpx channel) ────────────────────────

	def _headers_for(self, url: str) -> dict[str, str]:
		return referer_header(url, endpoints.REFERER_MAP, f"{endpoints.BASE_URL}/")

	def _merge_cookies(self, resp: httpx.Response) -> None:
		merge_response_cookies(self._get_client(), resp)

	# ── httpx request (low-risk ops) ─────────────────────────────────

	def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
		"""httpx 请求，循环重试（最多 _MAX_RETRIES 次），替代递归调用。"""
		for attempt in range(_MAX_RETRIES + 1):
			client = self._get_client()
			token = self._auth.get_token()
			stoken = token.get("stoken", "")

			add_stoken_to_get_params(method, kwargs, stoken)

			self._throttle.wait()

			extra_headers = self._headers_for(url)
			resp = client.request(method, url, headers=extra_headers, **kwargs)
			self._throttle.mark()
			self._merge_cookies(resp)

			# 403 或安全验证 → 刷新 token 重试
			if resp.status_code == 403 or "安全验证" in resp.text:
				if attempt >= _MAX_RETRIES:
					raise AuthError("Token 刷新后仍被拒绝，请重新登录")
				backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
				time.sleep(backoff)
				self._auth.force_refresh(cdp_url=self._cdp_url)
				self._client = None
				continue

			resp.raise_for_status()
			data = resp.json()
			code = data.get("code")

			# stoken 过期 → 刷新重试
			if code == endpoints.CODE_STOKEN_EXPIRED and attempt < _MAX_RETRIES:
				backoff = (2 ** attempt) + random.uniform(0.5, 1.5)
				time.sleep(backoff)
				self._auth.force_refresh(cdp_url=self._cdp_url)
				self._client = None
				continue

			# 频率限制 → 冷却重试
			if code == endpoints.CODE_RATE_LIMITED and attempt < _MAX_RETRIES:
				cooldown = min(60, 10 * (2 ** attempt))
				time.sleep(cooldown)
				continue

			return cast("dict[str, Any]", data)

		raise AuthError("请求失败，已达最大重试次数")

	# ── Browser request (high-risk ops) ──────────────────────────────

	def _browser_request(self, method: str, url: str, *, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
		result = self._get_browser().request(method, url, params=params, data=data)
		code = result.get("code")
		if code == endpoints.CODE_ACCOUNT_RISK:
			msg = result.get("message", "账户存在异常行为")
			browser = self._get_browser()
			is_cdp = getattr(browser, "_is_cdp", False)
			mode = "CDP" if is_cdp else ("Bridge" if getattr(browser, "_is_bridge", False) else "headless patchright")
			raise AccountRiskError(
				f"BOSS 直聘风控拦截 (code {code}): {msg}。"
				f"当前浏览器模式: {mode}。"
				f"建议：停止自动化访问并回到 BOSS 直聘官方页面手动处理。",
				is_cdp=is_cdp,
			)
		return result

	# ── Public API ───────────────────────────────────────────────────
	# High-risk: search, recommend, greet, job_card → browser channel
	# Low-risk: status, me, cities, schema, detail → httpx channel

	def search_jobs(self, query: str, **filters: Any) -> dict[str, Any]:
		params: dict[str, Any] = {"query": query, "page": filters.get("page", 1)}
		if raw_params := filters.get("raw_params"):
			params.update(raw_params)
		if city := filters.get("city"):
			code = endpoints.CITY_CODES.get(city)
			if code is None:
				raise ValueError(f"未知城市: {city}")
			params["city"] = code
		if salary := filters.get("salary"):
			code = filters.get("salary_code") or endpoints.SALARY_CODES.get(salary)
			if code:
				params["salary"] = code
		if exp := filters.get("experience"):
			code = filters.get("experience_code") or endpoints.EXPERIENCE_CODES.get(exp)
			if code:
				params["experience"] = code
		if edu := filters.get("education"):
			code = filters.get("education_code") or endpoints.EDUCATION_CODES.get(edu)
			if code:
				params["degree"] = code
		if scale := filters.get("scale"):
			code = filters.get("scale_code") or endpoints.SCALE_CODES.get(scale)
			if code:
				params["scale"] = code
		if industry := filters.get("industry"):
			code = filters.get("industry_code") or endpoints.INDUSTRY_CODES.get(industry)
			if code:
				params["industry"] = code
		if stage := filters.get("stage"):
			code = filters.get("stage_code") or endpoints.STAGE_CODES.get(stage)
			if code:
				params["stage"] = code
		if job_type := filters.get("job_type"):
			code = filters.get("job_type_code") or endpoints.JOB_TYPE_CODES.get(job_type)
			if code:
				params["jobType"] = code
		return self._browser_request("GET", endpoints.SEARCH_URL, params=params)

	def recommend_jobs(self, page: int = 1) -> dict[str, Any]:
		params = {"page": page}
		return self._browser_request("GET", endpoints.RECOMMEND_URL, params=params)

	def greet(self, security_id: str, job_id: str, message: str = "") -> dict[str, Any]:
		data = {
			"securityId": security_id,
			"jobId": job_id,
			"greeting": message or "您好，我对该岗位很感兴趣，希望能和您聊一聊。",
		}
		return self._browser_request("POST", endpoints.GREET_URL, data=data)

	def apply(self, security_id: str, job_id: str, lid: str = "", message: str = "") -> dict[str, Any]:
		"""全自动投递：发送立即沟通请求，平台自动附带在线简历。"""
		data: dict[str, Any] = {
			"securityId": security_id,
			"jobId": job_id,
		}
		if lid:
			data["lid"] = lid
		if message:
			data["greeting"] = message
		return self._browser_request("POST", endpoints.GREET_URL, data=data)

	def job_card(self, security_id: str, lid: str = "") -> dict[str, Any]:
		"""httpx 优先 + 浏览器降级获取职位卡片信息。"""
		try:
			return self.job_card_httpx(security_id, lid)
		except Exception:
			pass
		params = {"securityId": security_id, "lid": lid}
		return self._browser_request("GET", endpoints.JOB_CARD_URL, params=params)

	def job_card_httpx(self, security_id: str, lid: str = "") -> dict[str, Any]:
		"""通过 httpx 通道获取职位卡片信息（低延迟）。"""
		params = {"securityId": security_id, "lid": lid}
		return self._request("GET", endpoints.JOB_CARD_URL, params=params)

	# ── Low-risk: httpx channel ──────────────────────────────────────

	def job_detail(self, job_id: str) -> dict[str, Any]:
		params = {"encryptJobId": job_id}
		return self._request("GET", endpoints.DETAIL_URL, params=params)

	def user_info(self) -> dict[str, Any]:
		return self._request("GET", endpoints.USER_INFO_URL)

	def resume_baseinfo(self) -> dict[str, Any]:
		return self._request("GET", endpoints.RESUME_BASEINFO_URL)

	def resume_expect(self) -> dict[str, Any]:
		return self._request("GET", endpoints.RESUME_EXPECT_URL)

	def deliver_list(self, page: int = 1) -> dict[str, Any]:
		params = {"page": page}
		return self._request("GET", endpoints.DELIVER_LIST_URL, params=params)

	def friend_list(self, page: int = 1) -> dict[str, Any]:
		params = {"page": page}
		return self._request("GET", endpoints.FRIEND_LIST_URL, params=params)

	def interview_data(self) -> dict[str, Any]:
		return self._request("GET", endpoints.INTERVIEW_DATA_URL)

	def job_history(self, page: int = 1) -> dict[str, Any]:
		params = {"page": page}
		return self._request("GET", endpoints.JOB_HISTORY_URL, params=params)

	def chat_history(self, gid: str, security_id: str, *, page: int = 1, count: int = 20) -> dict[str, Any]:
		"""获取与指定好友的聊天消息历史。"""
		params = {"gid": gid, "securityId": security_id, "page": page, "c": count, "src": 0}
		return self._request("GET", endpoints.CHAT_HISTORY_URL, params=params)

	def friend_label(self, friend_id: str, label_id: int, friend_source: int = 0, *, remove: bool = False) -> dict[str, Any]:
		"""添加或移除好友标签。"""
		url = endpoints.FRIEND_LABEL_DELETE_URL if remove else endpoints.FRIEND_LABEL_ADD_URL
		params = {"friendId": friend_id, "friendSource": friend_source, "labelId": label_id}
		return self._request("GET", url, params=params)

	def exchange_contact(self, security_id: str, uid: str, name: str, exchange_type: int = 1) -> dict[str, Any]:
		"""请求交换联系方式（1=手机, 2=微信）。"""
		data = {"type": exchange_type, "securityId": security_id, "uniqueId": uid, "name": name}
		return self._browser_request("POST", endpoints.EXCHANGE_REQUEST_URL, data=data)

	_SEND_MSG_SCRIPT = '''(async () => {{
		const sid = "{security_id}";
		const content = "{content}";
		try {{
			// 1. 通过 boss-list 找到好友并打开对话
			const ulc = document.querySelector(".user-list-content");
			if (!ulc || !ulc.__vue__) return {{ ok: false, error: "user-list-content not found" }};
			const bossList = ulc.__vue__.$parent;
			const list = bossList.list || [];
			let friend = list.find(f => (f.securityId || "").includes(sid.substring(0, 30)) || (f.encryptBossId || "").includes(sid.substring(0, 30)));
			if (!friend) friend = list[0]; // fallback: 第一个好友用于测试
			if (!friend) return {{ ok: false, error: "no friends in list" }};
			bossList.handleOpenChat(friend);

			// 2. 等 chat-input 出现
			let chatInput = null;
			for (let i = 0; i < 20; i++) {{
				await new Promise(r => setTimeout(r, 500));
				chatInput = document.querySelector(".chat-input[contenteditable=\\"true\\"]");
				if (chatInput) break;
			}}
			if (!chatInput) return {{ ok: false, error: "chat-input not found after open" }};

			// 3. 填入内容
			chatInput.focus();
			chatInput.innerText = content;
			chatInput.dispatchEvent(new Event("input", {{ bubbles: true }}));
			chatInput.dispatchEvent(new Event("change", {{ bubbles: true }}));

			// 4. 等发送按钮 enabled
			await new Promise(r => setTimeout(r, 500));
			const sendBtn = document.querySelector(".btn-send:not(.disabled)");
			if (sendBtn) {{
				sendBtn.click();
				return {{ ok: true, method: "handleOpenChat+dom", friendName: friend.name }};
			}}

			// fallback: 按 Enter 发送 (contenteditable + Enter 键)
			chatInput.dispatchEvent(new KeyboardEvent("keydown", {{ key: "Enter", code: "Enter", keyCode: 13, bubbles: true }}));
			return {{ ok: true, method: "handleOpenChat+enter", friendName: friend.name }};
		}} catch(e) {{ return {{ ok: false, error: e.message }}; }}
	}})()'''

	_SEND_RESUME_SCRIPT = '''(async () => {{
		const sid = "{security_id}";
		try {{
			const ig = window.iGeekRoot;
			if (!ig || !ig.ChatDialog) return {{ ok: false, error: "no iGeekRoot" }};
			const cs = window.chatStore;
			let fd = null;
			const friends = cs.friends || {{}};
			for (const [k, v] of Object.entries(friends)) {{
				if (typeof v === "string" && v.includes(sid)) {{
					const info = cs.getFriendInfoById(v);
					if (info) {{ fd = info; break; }}
				}}
			}}
			if (!fd) fd = cs.getFriendInfoById(Object.values(friends)[0]);
			if (!fd) return {{ ok: false, error: "friend not found" }};
			ig.ChatDialog.openSendOnlineResume({{
				securityId: fd.securityId || fd.encryptBossId || sid,
				mid: fd.mid || "",
				friendSource: fd.friendSource || 1,
			}});
			await new Promise(r => setTimeout(r, 2000));
			const confirmBtns = [...document.querySelectorAll("button")]
				.filter(b => b.textContent.includes("发送") || b.textContent.includes("确认") || b.textContent.includes("投递"));
			if (confirmBtns.length > 0) {{ confirmBtns[0].click(); }}
			return {{ ok: true, method: "openSendOnlineResume" }};
		}} catch(e) {{ return {{ ok: false, error: e.message }}; }}
	}})()'''

	def _navigate_to_chat(self) -> None:
		"""确保 CDP 页面在候选人聊天页，等待 chatStore 就绪。"""
		browser = self._get_browser()
		browser._ensure_started()
		chat_url = "https://www.zhipin.com/web/geek/chat"
		# 始终导航到干净的聊天 URL（避免旧 query 参数干扰）
		try:
			browser._page.goto(chat_url, wait_until="domcontentloaded", timeout=15000)
		except Exception:
			try:
				browser._page.goto(chat_url, wait_until="commit", timeout=10000)
			except Exception:
				pass
		# 等待 bossList.list 就绪（聊天列表加载完成）
		import time as _time
		for _ in range(15):
			try:
				ready = browser._page.evaluate(
					"() => { const ulc = document.querySelector('.user-list-content'); return !!(ulc && ulc.__vue__ && ulc.__vue__.$parent && ulc.__vue__.$parent.list && ulc.__vue__.$parent.list.length > 0); }"
				)
				if ready:
					return
			except Exception:
				pass
			_time.sleep(1)

	def send_chat_message(self, security_id: str, content: str) -> dict[str, Any]:
		"""通过 CDP 在候选人聊天页发送文字消息。"""
		self._navigate_to_chat()
		browser = self._get_browser()
		escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
		script = self._SEND_MSG_SCRIPT.format(security_id=security_id, content=escaped)
		try:
			result = browser._page.evaluate(script)
			if isinstance(result, dict) and result.get("ok"):
				return {"code": 0, "message": "消息已发送", "method": result.get("method", "cdp")}
			return {"code": -1, "message": str(result.get("error", "发送失败")), "detail": result}
		except Exception as exc:
			return {"code": -1, "message": f"发送失败: {exc}"}

	def send_resume(self, security_id: str) -> dict[str, Any]:
		"""通过 CDP 自动发送在线简历给指定招聘者。"""
		self._navigate_to_chat()
		browser = self._get_browser()
		script = self._SEND_RESUME_SCRIPT.format(security_id=security_id)
		try:
			result = browser._page.evaluate(script)
			if isinstance(result, dict) and result.get("ok"):
				return {"code": 0, "message": "简历已发送", "method": result.get("method", "cdp")}
			return {"code": -1, "message": str(result.get("error", "发送失败")), "detail": result}
		except Exception as exc:
			return {"code": -1, "message": f"发送简历失败: {exc}"}

	def resume_status(self) -> dict[str, Any]:
		"""查询简历完整度和在线状态。"""
		return self._request("GET", endpoints.RESUME_STATUS_URL)

	def geek_get_job(self, security_id: str) -> dict[str, Any]:
		"""查询与某招聘者的互动关系（是否已打招呼等）。"""
		params = {"securityId": security_id}
		return self._request("GET", endpoints.GEEK_GET_JOB_URL, params=params)

	# ── Lifecycle ────────────────────────────────────────────────────

	def close(self) -> None:
		"""Release httpx client and browser session. Idempotent."""
		if self._closed:
			return
		self._closed = True
		if self._browser_session:
			self._browser_session.close()
			self._browser_session = None
		if self._client:
			self._client.close()
			self._client = None
		_OPEN_CLIENTS.discard(self)

	def __enter__(self) -> "BossClient":
		return self

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_val: BaseException | None,
		exc_tb: TracebackType | None,
	) -> None:
		self.close()
