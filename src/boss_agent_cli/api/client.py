import atexit
import random
import time
from pathlib import Path
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
			code = filters.get("salary_code") or (
				salary if str(salary).isdigit() else endpoints.SALARY_CODES.get(salary)
			)
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

	_CHAT_TARGET_HELPER_SCRIPT = '''
		function findTargetFriend(list, sid, target) {
			const value = (input) => String(input ?? "").trim();
			const normalize = (input) => value(input).replace(/\\s+/g, "").replace(/\\.\\.\\.$/, "").toLowerCase();
			const stripRecruiterPrefix = (input) => value(input).replace(/^boss_recruiter_/, "");
			const publicSummary = (friend) => ({
				name: friend.name || friend.bossName || friend.friendName || "",
				company: friend.brandName || friend.companyName || friend.company || "",
				title: friend.title || friend.sourceTitle || friend.positionName || friend.jobName || "",
				friendId: value(friend.friendId || friend.friend_id || friend.uid),
				uid: value(friend.uid),
				securityIdPrefix: value(friend.securityId).slice(0, 12),
				encryptBossIdPrefix: value(friend.encryptBossId).slice(0, 12),
			});
			const exactKeys = [
				target.gid,
				target.friend_id,
				target.friendId,
				target.uid,
				target.unique_id,
				target.uniqueId,
				stripRecruiterPrefix(target.recruiter_id),
				stripRecruiterPrefix(target.recruiterId),
			].map(value).filter(Boolean);
			const encryptedKeys = [
				sid,
				target.security_id,
				target.securityId,
				target.encrypt_boss_id,
				target.encryptBossId,
			].map(value).filter(item => item.length >= 12);
			const friendIdentityValues = (friend) => ({
				exact: [
					friend.friendId,
					friend.friend_id,
					friend.uid,
					friend.gid,
					friend.uniqueId,
					friend.mid,
				].map(value).filter(Boolean),
				encrypted: [
					friend.securityId,
					friend.encryptBossId,
					friend.encryptUid,
					friend.encryptJobId,
				].map(value).filter(Boolean),
			});
			const byIdentity = list.filter(friend => {
				const values = friendIdentityValues(friend);
				if (exactKeys.some(key => values.exact.includes(key))) return true;
				return encryptedKeys.some(key => {
					const keyPrefix = key.slice(0, Math.min(30, key.length));
					return values.encrypted.some(item =>
						item.includes(keyPrefix) || (item.length >= 12 && key.includes(item.slice(0, Math.min(30, item.length))))
					);
				});
			});
			if (byIdentity.length === 1) return { ok: true, friend: byIdentity[0] };
			if (byIdentity.length > 1) {
				return {
					ok: false,
					error: "target friend ambiguous",
					candidates: byIdentity.slice(0, 8).map(publicSummary),
				};
			}

			const targetName = normalize(target.recruiter_name || target.recruiterName || target.name);
			const targetCompany = normalize(target.company);
			const targetTitle = normalize(target.title);
			if (targetName) {
				const identityMatches = list.filter(friend => {
					const item = {
						name: normalize(friend.name || friend.bossName || friend.friendName),
						company: normalize(friend.brandName || friend.companyName || friend.company),
						title: normalize(friend.title || friend.sourceTitle || friend.positionName || friend.jobName),
					};
					const nameMatch = item.name === targetName;
					const companyMatch = targetCompany && item.company && (
						item.company === targetCompany || item.company.includes(targetCompany) || targetCompany.includes(item.company)
					);
					const titleMatch = targetTitle && item.title && (
						item.title === targetTitle || item.title.includes(targetTitle) || targetTitle.includes(item.title)
					);
					return nameMatch && (companyMatch || titleMatch);
				});
				if (identityMatches.length === 1) return { ok: true, friend: identityMatches[0] };
				if (identityMatches.length > 1) {
					return {
						ok: false,
						error: "target friend ambiguous by identity",
						candidates: identityMatches.slice(0, 8).map(publicSummary),
					};
				}
				const nameMatches = list.filter(friend => normalize(friend.name || friend.bossName || friend.friendName) === targetName);
				if (nameMatches.length === 1) return { ok: true, friend: nameMatches[0] };
				if (nameMatches.length > 1) {
					return {
						ok: false,
						error: "target friend ambiguous by name",
						candidates: nameMatches.slice(0, 8).map(publicSummary),
					};
				}
			}
			return {
				ok: false,
				error: "target friend not found",
				target: {
					recruiter_name: target.recruiter_name || target.recruiterName || "",
					company: target.company || "",
					title: target.title || "",
					gid: target.gid || "",
					friend_id: target.friend_id || target.friendId || "",
					securityIdPrefix: value(sid).slice(0, 12),
				},
				candidates: list.slice(0, 8).map(publicSummary),
			};
		}
	'''

	_SEND_MSG_SCRIPT = '''async ({ sid, content, target }) => {
%s
		try {
			// 1. 通过 boss-list 找到好友并打开对话
			const ulc = document.querySelector(".user-list-content");
			if (!ulc || !ulc.__vue__) return { ok: false, error: "user-list-content not found" };
			const bossList = ulc.__vue__.$parent;
			const list = bossList.list || [];
			const match = findTargetFriend(list, sid, target || {});
			if (!match.ok) return match;
			const friend = match.friend;
			bossList.handleOpenChat(friend);

			// 2. 等 chat-input 出现
			let chatInput = null;
			for (let i = 0; i < 20; i++) {
				await new Promise(r => setTimeout(r, 500));
				chatInput = document.querySelector(".chat-input[contenteditable=\\"true\\"]");
				if (chatInput) break;
			}
			if (!chatInput) return { ok: false, error: "chat-input not found after open" };

			// 3. 填入内容
			chatInput.focus();
			chatInput.innerText = content;
			chatInput.dispatchEvent(new Event("input", { bubbles: true }));
			chatInput.dispatchEvent(new Event("change", { bubbles: true }));

			// 4. 等发送按钮 enabled
			await new Promise(r => setTimeout(r, 500));
			const sendBtn = document.querySelector(".btn-send:not(.disabled)");
			if (sendBtn) {
				sendBtn.click();
				return { ok: true, method: "handleOpenChat+dom", friendName: friend.name };
			}

			// fallback: 按 Enter 发送 (contenteditable + Enter 键)
			chatInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
			return { ok: true, method: "handleOpenChat+enter", friendName: friend.name };
		} catch(e) { return { ok: false, error: e.message }; }
	}''' % _CHAT_TARGET_HELPER_SCRIPT

	_SEND_RESUME_SCRIPT = '''async ({ sid, target }) => {
%s
		try {
			const ulc = document.querySelector(".user-list-content");
			const bossList = ulc && ulc.__vue__ && ulc.__vue__.$parent;
			const list = (bossList && bossList.list) || [];
			const match = findTargetFriend(list, sid, target || {});
			if (!match.ok) return match;
			const friend = match.friend;
			if (bossList && friend) bossList.handleOpenChat(friend);
			await new Promise(r => setTimeout(r, 1000));
			const ig = window.iGeekRoot;
			if (!ig || !ig.ChatDialog) return { ok: false, error: "no iGeekRoot" };
			ig.ChatDialog.openSendOnlineResume({
				securityId: friend.securityId || friend.encryptBossId || sid,
				mid: friend.mid || friend.uid || friend.friendId || "",
				friendSource: friend.friendSource || 1,
			});
			await new Promise(r => setTimeout(r, 2000));
			const confirmBtns = [...document.querySelectorAll("button")]
				.filter(b => b.textContent.includes("发送") || b.textContent.includes("确认") || b.textContent.includes("投递"));
			if (confirmBtns.length > 0) { confirmBtns[0].click(); }
			return { ok: true, method: "openSendOnlineResume" };
		} catch(e) { return { ok: false, error: e.message }; }
	}''' % _CHAT_TARGET_HELPER_SCRIPT

	_AGREE_RESUME_ATTACHMENT_REQUEST_SCRIPT = '''async ({ sid, target }) => {
%s
		try {
			const ulc = document.querySelector(".user-list-content");
			if (!ulc || !ulc.__vue__) return { ok: false, error: "user-list-content not found" };
			const bossList = ulc.__vue__.$parent;
			const list = (bossList && bossList.list) || [];
			const match = findTargetFriend(list, sid, target || {});
			if (!match.ok) return match;
			const friend = match.friend;
			if (bossList && friend) bossList.handleOpenChat(friend);

			let conversation = null;
			for (let i = 0; i < 20; i++) {
				await new Promise(r => setTimeout(r, 500));
				conversation =
					document.querySelector(".chat-conversation") ||
					document.querySelector(".chat-message-list") ||
					document.querySelector(".chat-panel");
				if (conversation) break;
			}
			if (!conversation) return { ok: false, error: "chat conversation not found after open" };

			const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
			const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
			const agreeButtons = [...conversation.querySelectorAll(".btn-agree, button, a, span")]
				.filter(el => visible(el) && clean(el.innerText || el.textContent) === "同意");
			if (!agreeButtons.length) {
				return {
					ok: false,
					error: "resume request agree button not found",
					hasResumeRequest: /附件简历|详细简历|发.*简历|简历/.test(clean(conversation.innerText || conversation.textContent)),
					textSample: clean(conversation.innerText || conversation.textContent).slice(0, 240),
				};
			}

			const button = agreeButtons[agreeButtons.length - 1];
			button.click();
			await new Promise(r => setTimeout(r, 1500));
			const remainingAgreeButtonCount = [...conversation.querySelectorAll(".btn-agree, button, a, span")]
				.filter(el => visible(el) && clean(el.innerText || el.textContent) === "同意").length;
			return {
				ok: true,
				method: "resume-request-agree",
				friendName: friend.name || friend.bossName || friend.friendName || "",
				agreeButtonCount: agreeButtons.length,
				remainingAgreeButtonCount,
				textSample: clean(conversation.innerText || conversation.textContent).slice(0, 240),
			};
		} catch(e) { return { ok: false, error: e.message }; }
	}''' % _CHAT_TARGET_HELPER_SCRIPT

	def _navigate_to_chat(self) -> dict[str, Any]:
		"""确保 CDP 页面在候选人聊天页，等待聊天列表就绪。"""
		browser = self._get_browser()
		browser._ensure_started()
		if self._browser_raw_cdp_url(browser):
			return self._navigate_to_chat_via_raw_cdp(browser)
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
					"""() => {
						const ulc = document.querySelector('.user-list-content');
						const vueReady = !!(
							ulc &&
							ulc.__vue__ &&
							ulc.__vue__.$parent &&
							ulc.__vue__.$parent.list &&
							ulc.__vue__.$parent.list.length > 0
						);
						const domReady = !!(ulc && ulc.querySelector('li'));
						return vueReady || domReady;
					}"""
				)
				if ready:
					return {"ok": True, "url": browser._page.url}
			except Exception:
				pass
			_time.sleep(1)
		page_url = ""
		page_title = ""
		try:
			page_url = str(browser._page.url or "")
		except Exception:
			page_url = ""
		try:
			page_title = str(browser._page.title() or "")
		except Exception:
			page_title = ""
		if "/web/user" in page_url or "登录" in page_title or "注册登录" in page_title:
			return {
				"ok": False,
				"error": "boss_chat_login_required",
				"message": "Boss CDP 登录态已失效，聊天页被重定向到登录页。请先执行 boss login --cdp，或在当前 CDP Chrome 内重新登录 BOSS。",
				"url": page_url,
				"title": page_title,
			}
		return {
			"ok": False,
			"error": "boss_chat_page_not_ready",
			"message": "Boss 聊天页未就绪，当前无法发送消息。请确认聊天列表已加载，或刷新 CDP 登录态后重试。",
			"url": page_url,
			"title": page_title,
		}

	def _navigate_to_chat_via_raw_cdp(self, browser: "BrowserSession") -> dict[str, Any]:
		"""Ensure candidate chat is ready without creating a Playwright page."""
		from boss_agent_cli.api.browser_client import ensure_candidate_chat_page_via_cdp

		cdp_url = self._browser_raw_cdp_url(browser) or self._cdp_url or ""
		chat_page = ensure_candidate_chat_page_via_cdp(cdp_url or None)
		if not chat_page.get("ok"):
			return {
				"ok": False,
				"error": str(chat_page.get("code") or "boss_chat_page_not_ready"),
				"message": str(chat_page.get("message") or "Boss 聊天页未就绪。"),
				"url": str(chat_page.get("url") or ""),
				"title": str(chat_page.get("title") or ""),
			}
		ready_script = """(() => {
			const ulc = document.querySelector('.user-list-content');
			const vueReady = !!(
				ulc &&
				ulc.__vue__ &&
				ulc.__vue__.$parent &&
				ulc.__vue__.$parent.list &&
				ulc.__vue__.$parent.list.length > 0
			);
			const domReady = !!(ulc && ulc.querySelector('li'));
			return {
				ready: vueReady || domReady,
				href: location.href,
				title: document.title,
			};
		})()"""
		for _ in range(15):
			try:
				ready = browser.evaluate_js_in_zhipin_tab(ready_script)
				if isinstance(ready, dict) and ready.get("ready"):
					return {"ok": True, "url": str(ready.get("href") or chat_page.get("url") or "")}
			except Exception:
				pass
			time.sleep(1)
		page_url = ""
		page_title = ""
		try:
			ready = browser.evaluate_js_in_zhipin_tab(ready_script)
			if isinstance(ready, dict):
				page_url = str(ready.get("href") or "")
				page_title = str(ready.get("title") or "")
		except Exception:
			pass
		if "/web/user" in page_url or "登录" in page_title or "注册登录" in page_title:
			return {
				"ok": False,
				"error": "boss_chat_login_required",
				"message": "Boss CDP 登录态已失效，聊天页被重定向到登录页。请先执行 boss login --cdp，或在当前 CDP Chrome 内重新登录 BOSS。",
				"url": page_url,
				"title": page_title,
			}
		return {
			"ok": False,
			"error": "boss_chat_page_not_ready",
			"message": "Boss 聊天页未就绪，当前无法发送消息。请确认聊天列表已加载，或刷新 CDP 登录态后重试。",
			"url": page_url,
			"title": page_title,
		}

	def _evaluate_candidate_chat_script(self, browser: "BrowserSession", script: str, arg: Any | None = None) -> Any:
		if self._browser_raw_cdp_url(browser):
			return browser.evaluate_js_in_zhipin_tab(script, arg)
		if arg is None:
			return browser._page.evaluate(script)
		return browser._page.evaluate(script, arg)

	@staticmethod
	def _browser_raw_cdp_url(browser: "BrowserSession") -> str:
		value = getattr(browser, "_raw_cdp_url", None)
		return value if isinstance(value, str) and value else ""

	@staticmethod
	def _chat_target_payload(
		*,
		security_id: str,
		target_recruiter_name: str = "",
		target_company: str = "",
		target_title: str = "",
		target_gid: str = "",
		target_friend_id: str = "",
		target_uid: str = "",
		target_encrypt_boss_id: str = "",
		target_recruiter_id: str = "",
	) -> dict[str, str]:
		return {
			"security_id": str(security_id or "").strip(),
			"recruiter_name": str(target_recruiter_name or "").strip(),
			"company": str(target_company or "").strip(),
			"title": str(target_title or "").strip(),
			"gid": str(target_gid or "").strip(),
			"friend_id": str(target_friend_id or "").strip(),
			"uid": str(target_uid or "").strip(),
			"encrypt_boss_id": str(target_encrypt_boss_id or "").strip(),
			"recruiter_id": str(target_recruiter_id or "").strip(),
		}

	def send_chat_message(
		self,
		security_id: str,
		content: str,
		*,
		target_recruiter_name: str = "",
		target_company: str = "",
		target_title: str = "",
		target_gid: str = "",
		target_friend_id: str = "",
		target_uid: str = "",
		target_encrypt_boss_id: str = "",
		target_recruiter_id: str = "",
	) -> dict[str, Any]:
		"""通过 CDP 在候选人聊天页发送文字消息。"""
		navigation = self._navigate_to_chat()
		if not navigation.get("ok"):
			return {"code": -1, "message": str(navigation.get("message") or "聊天页未就绪"), "detail": navigation}
		browser = self._get_browser()
		target = self._chat_target_payload(
			security_id=security_id,
			target_recruiter_name=target_recruiter_name,
			target_company=target_company,
			target_title=target_title,
			target_gid=target_gid,
			target_friend_id=target_friend_id,
			target_uid=target_uid,
			target_encrypt_boss_id=target_encrypt_boss_id,
			target_recruiter_id=target_recruiter_id,
		)
		try:
			result = self._evaluate_candidate_chat_script(
				browser,
				self._SEND_MSG_SCRIPT,
				{"sid": security_id, "content": content, "target": target},
			)
			if isinstance(result, dict) and result.get("ok"):
				return {"code": 0, "message": "消息已发送", "method": result.get("method", "cdp")}
			return {"code": -1, "message": str(result.get("error", "发送失败")), "detail": result}
		except Exception as exc:
			return {"code": -1, "message": f"发送失败: {exc}"}

	def send_resume(
		self,
		security_id: str,
		*,
		target_recruiter_name: str = "",
		target_company: str = "",
		target_title: str = "",
		target_gid: str = "",
		target_friend_id: str = "",
		target_uid: str = "",
		target_encrypt_boss_id: str = "",
		target_recruiter_id: str = "",
	) -> dict[str, Any]:
		"""通过 CDP 自动发送在线简历给指定招聘者。"""
		navigation = self._navigate_to_chat()
		if not navigation.get("ok"):
			return {"code": -1, "message": str(navigation.get("message") or "聊天页未就绪"), "detail": navigation}
		browser = self._get_browser()
		target = self._chat_target_payload(
			security_id=security_id,
			target_recruiter_name=target_recruiter_name,
			target_company=target_company,
			target_title=target_title,
			target_gid=target_gid,
			target_friend_id=target_friend_id,
			target_uid=target_uid,
			target_encrypt_boss_id=target_encrypt_boss_id,
			target_recruiter_id=target_recruiter_id,
		)
		try:
			result = self._evaluate_candidate_chat_script(
				browser,
				self._SEND_RESUME_SCRIPT,
				{"sid": security_id, "target": target},
			)
			if isinstance(result, dict) and result.get("ok"):
				return {"code": 0, "message": "简历已发送", "method": result.get("method", "cdp")}
			return {"code": -1, "message": str(result.get("error", "发送失败")), "detail": result}
		except Exception as exc:
			return {"code": -1, "message": f"发送简历失败: {exc}"}

	def send_resume_attachment(
		self,
		security_id: str,
		file_path: str,
		*,
		target_recruiter_name: str = "",
		target_company: str = "",
		target_title: str = "",
		target_gid: str = "",
		target_friend_id: str = "",
		target_uid: str = "",
		target_encrypt_boss_id: str = "",
		target_recruiter_id: str = "",
	) -> dict[str, Any]:
		"""通过 CDP 上传附件简历 PDF，不发送额外文字消息。"""
		attachment = Path(file_path).expanduser().resolve()
		if not attachment.exists():
			return {"code": -1, "message": f"附件简历不存在: {attachment}"}
		navigation = self._navigate_to_chat()
		if not navigation.get("ok"):
			return {"code": -1, "message": str(navigation.get("message") or "聊天页未就绪"), "detail": navigation}
		browser = self._get_browser()
		if self._browser_raw_cdp_url(browser):
			target = self._chat_target_payload(
				security_id=security_id,
				target_recruiter_name=target_recruiter_name,
				target_company=target_company,
				target_title=target_title,
				target_gid=target_gid,
				target_friend_id=target_friend_id,
				target_uid=target_uid,
				target_encrypt_boss_id=target_encrypt_boss_id,
				target_recruiter_id=target_recruiter_id,
			)
			try:
				agree_result = self._evaluate_candidate_chat_script(
					browser,
					self._AGREE_RESUME_ATTACHMENT_REQUEST_SCRIPT,
					{"sid": security_id, "target": target},
				)
			except Exception as exc:
				return {"code": -1, "message": f"点击附件简历确认失败: {exc}", "detail": navigation}
			if isinstance(agree_result, dict) and agree_result.get("ok"):
				return {
					"code": 0,
					"message": "附件简历请求已同意",
					"method": "resume-request-agree",
					"file": str(attachment),
					"detail": {"navigation": navigation, "agree_result": agree_result},
				}
			return {
				"code": -1,
				"message": "未找到待确认的附件简历同意按钮；当前 raw CDP 通道不能选择本地附件文件，已取消发送。",
				"method": "resume-request-agree",
				"file": str(attachment),
				"detail": {"navigation": navigation, "agree_result": agree_result},
			}
		def _is_navigation_context_error(exc: Exception) -> bool:
			message = str(exc)
			return (
				"Execution context was destroyed" in message
				or "most likely because of a navigation" in message
				or "Cannot find context with specified id" in message
			)

		def _safe_evaluate(stage: str, script: str, arg: Any | None = None, *, retries: int = 3) -> Any:
			last_error: Exception | None = None
			for _ in range(retries):
				try:
					if arg is None:
						return browser._page.evaluate(script)
					return browser._page.evaluate(script, arg)
				except Exception as exc:
					if not _is_navigation_context_error(exc):
						raise RuntimeError(f"{stage}: {exc}") from exc
					last_error = exc
					try:
						browser._page.wait_for_load_state("domcontentloaded", timeout=5000)
					except Exception:
						pass
					time.sleep(0.5)
			raise RuntimeError(f"{stage}: {last_error}") from last_error

		try:
			try:
				open_result = browser._page.evaluate(
					'''({ sid, recruiterName, company, title }) => {
					const normalize = (value) =>
						String(value || "")
							.replace(/\\s+/g, "")
							.replace(/\\.\\.\\.$/, "")
							.toLowerCase();
					const summarize = (friend) => ({
						name: normalize(friend.name || friend.bossName || friend.friendName),
						company: normalize(friend.brandName || friend.companyName || friend.company),
						title: normalize(friend.title || friend.sourceTitle || friend.positionName || friend.jobName),
						securityIdPrefix: String(friend.securityId || "").slice(0, 12),
					});
					const publicSummary = (friend) => {
						const summary = summarize(friend);
						return {
							name: friend.name || friend.bossName || friend.friendName || "",
							company: friend.brandName || friend.companyName || friend.company || "",
							title: friend.title || friend.sourceTitle || friend.positionName || friend.jobName || "",
							securityIdPrefix: summary.securityIdPrefix,
						};
					};
					const ulc = document.querySelector(".user-list-content");
					if (!ulc) return { ok: false, error: "user-list-content not found" };
					const bossList = ulc.__vue__ && ulc.__vue__.$parent;
					const list = (bossList && bossList.list) || [];
					const key = String(sid || "").slice(0, 30);
					const target = {
						name: normalize(recruiterName),
						company: normalize(company),
						title: normalize(title),
					};
					let friend = null;
					if (bossList && list.length) {
						if (key) {
							friend = list.find(f =>
								String(f.securityId || "").includes(key) ||
								String(f.encryptBossId || "").includes(key)
							);
						}
						if (!friend && target.name) {
							const identityMatches = list.filter(f => {
								const item = summarize(f);
								const nameMatch = item.name === target.name;
								const companyMatch =
									target.company &&
									item.company &&
									(item.company === target.company ||
									 item.company.includes(target.company) ||
									 target.company.includes(item.company));
								const titleMatch =
									target.title &&
									item.title &&
									(item.title === target.title ||
									 item.title.includes(target.title) ||
									 target.title.includes(item.title));
								return nameMatch && (companyMatch || titleMatch);
							});
							if (identityMatches.length === 1) {
								friend = identityMatches[0];
							} else if (identityMatches.length > 1) {
								return {
									ok: false,
									error: "target friend ambiguous",
									candidates: identityMatches.slice(0, 8).map(publicSummary),
								};
							}
						}
						if (!friend && target.name) {
							const nameMatches = list.filter(f => summarize(f).name === target.name);
							if (nameMatches.length === 1) {
								friend = nameMatches[0];
							} else if (nameMatches.length > 1) {
								return {
									ok: false,
									error: "target friend ambiguous by name",
									candidates: nameMatches.slice(0, 8).map(publicSummary),
								};
							}
						}
						if (friend) {
							bossList.handleOpenChat(friend);
							return { ok: true, method: "vue", friendName: friend.name || "", friend: publicSummary(friend) };
						}
					}

					const domItems = [...document.querySelectorAll(".user-list-content li")];
					const domSummary = (el) => ({
						name: "",
						company: "",
						title: "",
						text: String(el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 160),
					});
					const domMatches = domItems.filter(el => {
						const text = normalize(el.innerText || el.textContent || "");
						const nameMatch = target.name && text.includes(target.name);
						const companyMatch = target.company && text.includes(target.company);
						const titleMatch = target.title && text.includes(target.title);
						return nameMatch && (companyMatch || titleMatch);
					});
					if (domMatches.length === 1) {
						const clickable = domMatches[0].querySelector(".friend-content") || domMatches[0];
						clickable.click();
						return { ok: true, method: "dom", friend: domSummary(domMatches[0]) };
					}
					if (domMatches.length > 1) {
						return {
							ok: false,
							error: "target friend ambiguous in DOM",
							candidates: domMatches.slice(0, 8).map(domSummary),
						};
					}
					if (!friend) {
						return {
							ok: false,
							error: "target friend not found",
							target,
							candidates: list.length
								? list.slice(0, 8).map(publicSummary)
								: domItems.slice(0, 8).map(domSummary),
						};
					}
				}''',
					{
						"sid": security_id,
						"recruiterName": target_recruiter_name,
						"company": target_company,
						"title": target_title,
					},
				)
			except Exception as exc:
				if not _is_navigation_context_error(exc):
					raise
				open_result = {
					"ok": True,
					"method": "open-triggered-before-navigation",
					"warning": str(exc),
				}
			if not isinstance(open_result, dict) or not open_result.get("ok"):
				return {"code": -1, "message": str((open_result or {}).get("error") or "打开目标对话失败"), "detail": open_result}
			try:
				browser._page.wait_for_load_state("domcontentloaded", timeout=5000)
			except Exception:
				pass
			try:
				browser._page.wait_for_selector('.chat-input[contenteditable="true"]', timeout=12000)
			except Exception as exc:
				return {
					"code": -1,
					"message": f"打开目标对话后未找到输入框: {exc}",
					"detail": open_result,
				}
			if target_recruiter_name or target_company or target_title:
				target_verified = _safe_evaluate(
					"verify-target-conversation",
					'''({ recruiterName, company, title }) => {
						const normalize = (value) =>
							String(value || "").replace(/\\s+/g, "").replace(/\\.\\.\\.$/, "").toLowerCase();
						const target = {
							name: normalize(recruiterName),
							company: normalize(company),
							title: normalize(title),
						};
						const conversationText =
							document.querySelector(".chat-conversation")?.innerText ||
							document.querySelector(".chat-message-list")?.innerText ||
							document.querySelector(".chat-panel")?.innerText ||
							document.querySelector(".chat-editor")?.parentElement?.innerText ||
							"";
						const text = normalize(conversationText);
						const nameMatch = target.name && text.includes(target.name);
						const companyMatch = target.company && text.includes(target.company);
						const titleMatch = target.title && text.includes(target.title);
						return {
							ok: Boolean(nameMatch || companyMatch || titleMatch),
							nameMatch: Boolean(nameMatch),
							companyMatch: Boolean(companyMatch),
							titleMatch: Boolean(titleMatch),
							textSample: String(conversationText || "").replace(/\\s+/g, " ").trim().slice(0, 200),
						};
					}''',
					{
						"recruiterName": target_recruiter_name,
						"company": target_company,
						"title": target_title,
					},
				)
				if isinstance(target_verified, dict) and not target_verified.get("ok"):
					return {
						"code": -1,
						"message": "打开目标对话后未能确认当前会话身份，已取消附件上传",
						"detail": {"open_result": open_result, "target_verified": target_verified},
					}
			before_file_count = _safe_evaluate(
				"count-file-before-upload",
				'''({ name }) => {
					const conversationText = document.querySelector(".chat-conversation")?.innerText || "";
					return conversationText.split(name).length - 1;
				}''',
				{"name": attachment.name},
			)
			try:
				agree_result = browser._page.evaluate(
					'''() => {
						const conversation = document.querySelector(".chat-conversation");
						if (!conversation) return { ok: false, reason: "conversation not found" };
						const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
						const agreeButtons = [...conversation.querySelectorAll(".btn-agree, button, a, span")]
							.filter(el => visible(el) && String(el.innerText || el.textContent || "").trim() === "同意");
						if (!agreeButtons.length) {
							return {
								ok: false,
								reason: "resume request agree button not found",
								textSample: String(conversation.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 240),
							};
						}
						const button = agreeButtons[agreeButtons.length - 1];
						button.click();
						return { ok: true, method: "resume-request-agree", agreeButtonCount: agreeButtons.length };
					}'''
				)
			except Exception as exc:
				if not _is_navigation_context_error(exc):
					raise RuntimeError(f"click-resume-request-agree: {exc}") from exc
				agree_result = {
					"ok": True,
					"method": "resume-request-agree",
					"warning": str(exc),
				}
			if isinstance(agree_result, dict) and agree_result.get("ok"):
				verify: dict[str, Any] | None = None
				for _ in range(12):
					time.sleep(1)
					verify = _safe_evaluate(
						"verify-resume-request-agree",
						'''({ name, beforeCount }) => {
							const conversationText = document.querySelector(".chat-conversation")?.innerText || "";
							const fileNameCount = conversationText.split(name).length - 1;
							const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
							const agreeButtonCount = [...document.querySelectorAll(".chat-conversation .btn-agree")]
								.filter(visible).length;
							const hasResumeRequest = /附件简历|详细简历|发.*简历/.test(conversationText);
							return {
								seenFileName: fileNameCount > beforeCount,
								fileNameCount,
								beforeCount,
								agreeButtonCount,
								hasResumeRequest,
								textSample: conversationText.replace(/\\s+/g, " ").trim().slice(0, 240),
							};
						}''',
						{"name": attachment.name, "beforeCount": int(before_file_count or 0)},
					)
					if isinstance(verify, dict) and (
						verify.get("seenFileName") or int(verify.get("agreeButtonCount") or 0) == 0
					):
						return {
							"code": 0,
							"message": "附件简历请求已同意",
							"method": "resume-request-agree",
							"file": str(attachment),
							"detail": {"agree_result": agree_result, "verify": verify},
						}
				return {
					"code": -1,
					"message": "已点击附件简历同意按钮，但未能确认 Boss 聊天页状态变化",
					"method": "resume-request-agree",
					"file": str(attachment),
					"detail": {"agree_result": agree_result, "verify": verify},
				}
			open_toolbar_result = _safe_evaluate(
				"open-resume-toolbar",
				'''() => {
					const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
					const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
					const editor = document.querySelector(".chat-editor");
					if (!editor) return { ok: false, error: "chat editor not found" };
					const candidates = [...editor.querySelectorAll("button, a, span, div")]
						.filter(visible)
						.map(el => ({ el, text: clean(el.innerText || el.textContent) }))
						.filter(item => item.text === "发简历" || /^发简历\\b/.test(item.text));
					if (!candidates.length) {
						return {
							ok: false,
							error: "resume toolbar button not found",
							editorText: clean(editor.innerText || editor.textContent).slice(0, 240),
						};
					}
					const target = candidates[candidates.length - 1].el;
					const clickable = target.closest("button, a, [role='button'], .btn, .btn-v2") || target;
					clickable.click();
					return {
						ok: true,
						method: "resume-toolbar-open",
						buttonText: candidates[candidates.length - 1].text,
						editorText: clean(editor.innerText || editor.textContent).slice(0, 240),
					};
				}''',
			)
			if not isinstance(open_toolbar_result, dict) or not open_toolbar_result.get("ok"):
				return {
					"code": -1,
					"message": "未找到 Boss 聊天工具栏的发简历入口",
					"method": "resume-toolbar-upload",
					"file": str(attachment),
					"detail": open_toolbar_result,
				}
			choose_attachment_result: dict[str, Any] | None = None
			for _ in range(8):
				time.sleep(0.5)
				choose_attachment_result = _safe_evaluate(
					"choose-resume-toolbar-attachment",
					'''() => {
						const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
						const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
						const fileSelector = 'input[type="file"][ka="user-resume-upload-file"], input[type="file"][accept*=".pdf"], input[type="file"][accept*="application/pdf"], input[type="file"][accept*="pdf"]';
						const visibleRoots = [...document.querySelectorAll(".dialog-container, .dialog, .boss-dialog, .modal, .pop, [role='dialog']")]
							.filter(visible);
						const roots = visibleRoots.length ? visibleRoots : [document.body];
						if (visibleRoots.some(root => root.querySelector(fileSelector))) {
							return { ok: true, method: "resume-toolbar-file-input-ready" };
						}
						const labels = ["上传附件简历", "上传简历", "附件简历"];
						for (const root of roots) {
							const actions = [...root.querySelectorAll("button, a, span, div")]
								.filter(visible)
								.map(el => ({ el, text: clean(el.innerText || el.textContent) }))
								.filter(item =>
									item.text &&
									labels.some(label => item.text === label || item.text.includes(label)) &&
									!/发送在线简历|在线填写|没有附件简历|取消/.test(item.text)
								);
							if (actions.length) {
								const action = actions[actions.length - 1];
								const clickable = action.el.closest("button, a, [role='button'], .btn, .btn-v2") || action.el;
								clickable.click();
								return { ok: true, method: "resume-toolbar-attachment-option", buttonText: action.text };
							}
						}
						return {
							ok: false,
							error: "resume attachment option not found",
							dialogText: roots.map(root => clean(root.innerText || root.textContent)).join(" | ").slice(0, 360),
						};
					}''',
				)
				if isinstance(choose_attachment_result, dict) and choose_attachment_result.get("ok"):
					break
			if not isinstance(choose_attachment_result, dict) or not choose_attachment_result.get("ok"):
				return {
					"code": -1,
					"message": "已打开 Boss 发简历入口，但未找到附件简历上传选项",
					"method": "resume-toolbar-upload",
					"file": str(attachment),
					"detail": {
						"open_toolbar_result": open_toolbar_result,
						"choose_attachment_result": choose_attachment_result,
					},
				}
			file_input = browser._page.locator(
				'input[type="file"][ka="user-resume-upload-file"], '
				'input[type="file"][accept*=".pdf"], '
				'input[type="file"][accept*="application/pdf"], '
				'input[type="file"][accept*="pdf"]'
			).first
			file_input.set_input_files(str(attachment))
			time.sleep(1)
			confirm_result = _safe_evaluate(
				"confirm-resume-toolbar-upload",
				'''() => {
					const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
					const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
					const visibleRoots = [...document.querySelectorAll(".dialog-container, .dialog, .boss-dialog, .modal, .pop, [role='dialog']")]
						.filter(visible);
					const roots = visibleRoots.filter(root => /简历|附件|RESUME|EXPORT/i.test(clean(root.innerText || root.textContent)));
					if (!roots.length) {
						return {
							ok: true,
							method: "resume-toolbar-upload",
							warning: "resume upload dialog not found; waiting for automatic send",
						};
					}
					const labels = ["确认发送", "发送简历", "发送", "确定", "确认"];
					for (const root of roots) {
						const actions = [...root.querySelectorAll("button, a, span, div")]
							.filter(visible)
							.map(el => ({ el, text: clean(el.innerText || el.textContent), disabled: el.disabled || /disabled/.test(String(el.className || "")) }))
							.filter(item =>
								!item.disabled &&
								item.text &&
								labels.some(label => item.text === label || item.text.includes(label)) &&
								!/取消|发送在线简历|在线填写|上传附件简历|上传简历|换电话|换微信/.test(item.text)
							);
						if (actions.length) {
							const action = actions[actions.length - 1];
							const clickable = action.el.closest("button, a, [role='button'], .btn, .btn-v2") || action.el;
							clickable.click();
							return { ok: true, method: "resume-toolbar-upload", buttonText: action.text };
						}
					}
					return {
						ok: true,
						method: "resume-toolbar-upload",
						warning: "resume upload confirmation button not found; waiting for automatic send",
						dialogText: roots.map(root => clean(root.innerText || root.textContent)).join(" | ").slice(0, 360),
					};
				}''',
			)
			verify: dict[str, Any] | None = None
			for _ in range(10):
				time.sleep(1)
				verify = _safe_evaluate(
					"verify-resume-toolbar-upload",
					'''({ name, beforeCount }) => {
						const conversationText = document.querySelector(".chat-conversation")?.innerText || "";
						const fileNameCount = conversationText.split(name).length - 1;
						const visible = (el) => !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
						const activeDialogText = [...document.querySelectorAll(".dialog-container, .dialog, .boss-dialog, .modal, .pop, [role='dialog']")]
							.filter(visible)
							.map(el => String(el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim())
							.join(" | ")
							.slice(0, 360);
						return {
							seenFileName: fileNameCount > beforeCount,
							fileNameCount,
							beforeCount,
							hasResumeFileInput: !!document.querySelector('input[type="file"][ka="user-resume-upload-file"], input[type="file"][accept*=".pdf"], input[type="file"][accept*="application/pdf"], input[type="file"][accept*="pdf"]'),
							activeDialogText,
							textSample: conversationText.replace(/\\s+/g, " ").trim().slice(0, 240),
						};
					}''',
					{"name": attachment.name, "beforeCount": int(before_file_count or 0)},
				)
				if isinstance(verify, dict) and verify.get("seenFileName"):
					return {
						"code": 0,
						"message": "附件简历已通过 Boss 发简历工具栏发送",
						"method": "resume-toolbar-upload",
						"file": str(attachment),
						"detail": {
							"open_toolbar_result": open_toolbar_result,
							"choose_attachment_result": choose_attachment_result,
							"confirm_result": confirm_result,
							"verify": verify,
						},
					}
			return {
				"code": -1,
				"message": "已走 Boss 发简历工具栏上传控件，但未确认看到 PDF 文件名",
				"method": "resume-toolbar-upload",
				"file": str(attachment),
				"detail": {
					"open_toolbar_result": open_toolbar_result,
					"choose_attachment_result": choose_attachment_result,
					"confirm_result": confirm_result,
					"verify": verify,
				},
			}
		except Exception as exc:
			return {"code": -1, "message": f"发送附件简历失败: {exc}"}

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
