from pathlib import Path

from boss_agent_cli.rag_reply.adapters.boss_automation import BossAutomationAdapter
from boss_agent_cli.rag_reply.models import AuditLogRecord
from boss_agent_cli.rag_reply.store import RagReplyStore


class _JobPlatform:
	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def search_jobs(self, query, **filters):
		assert query == "golang"
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"jobList": [
					{
						"encryptJobId": "job_001",
						"securityId": "sec_001",
						"jobName": "Go 开发",
						"brandName": "TestCo",
						"salaryDesc": "30-40K",
						"cityName": "北京",
					}
				],
			},
		}

	def recommend_jobs(self, page=1):
		raise AssertionError("recommend_jobs should not be called in this test")

	def job_detail(self, job_id):
		assert job_id == "job_001"
		return {
			"code": 0,
			"zpData": {
				"jobInfo": {
					"encryptJobId": "job_001",
					"securityId": "sec_001",
					"jobName": "Go 开发",
					"salaryDesc": "30-40K",
					"cityName": "北京",
					"experienceName": "3-5年",
					"degreeName": "本科",
					"postDescription": "负责后端服务开发和稳定性建设。",
				},
				"brandComInfo": {"brandName": "TestCo"},
				"jobDetail": "负责后端服务开发和稳定性建设。",
			},
		}

	def close(self):
		return None


class _MessagePlatform:
	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"result": [
					{
						"securityId": "sec_001",
						"uid": 12345,
						"friendId": 12345,
						"encryptBossId": "enc_boss_001",
						"encryptJobId": "job_001",
						"name": "张HR",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "方便加微信吗？",
						"lastTS": 1700000000000,
					}
				],
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		assert gid == "12345"
		assert security_id == "sec_001"
		assert page == 1
		assert count == 50
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"id": "m_001",
						"from": {"uid": 12345, "name": "张HR"},
						"type": 1,
						"text": "方便加微信吗？",
						"time": 1700000000000,
					},
					{
						"id": "m_002",
						"from": {"uid": 99999, "name": "我"},
						"type": 1,
						"text": "先在这里聊吧",
						"time": 1700000001000,
					},
				]
			},
		}

	def close(self):
		return None


class _PipelineCandidatePlatform:
	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"result": [
					{
						"securityId": "sec_read",
						"uid": 12345,
						"friendId": 12345,
						"encryptBossId": "enc_boss_001",
						"encryptJobId": "job_001",
						"relationType": 2,
						"lastMessageInfo": {"status": 2},
						"unreadMsgCount": 0,
						"name": "张HR",
						"brandName": "TestCo",
						"title": "AI 工程师",
						"lastMsg": "我发了项目介绍",
						"lastTS": 1700000000000,
					},
					{
						"securityId": "sec_unread",
						"relationType": 2,
						"lastMessageInfo": {"status": 1},
						"unreadMsgCount": 0,
						"lastTS": 1700000000000,
					},
				],
			},
		}

	def close(self):
		return None


class _RecentOnlyMessagePlatform:
	def __init__(self):
		self.friend_list_pages: list[int] = []
		self.chat_history_calls: list[tuple[str, str]] = []

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		self.friend_list_pages.append(page)
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"result": [
					{
						"securityId": f"sec_{index:03d}",
						"uid": 10000 + index,
						"encryptJobId": f"job_{index:03d}",
						"name": f"HR{index}",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前是否还在招聘？",
						"lastTS": 1700000000000 + index,
					}
					for index in range(25)
				],
				"hasMore": False,
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		self.chat_history_calls.append((gid, security_id))
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"id": f"m_{gid}",
						"from": {"uid": int(gid), "name": "HR"},
						"type": 1,
						"text": "你好",
						"time": 1700000000000,
					}
				]
			},
		}

	def close(self):
		return None


class _UnreadBeyondRecentLimitPlatform:
	def __init__(self):
		self.friend_list_pages: list[int] = []
		self.chat_history_calls: list[tuple[str, str]] = []

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		self.friend_list_pages.append(page)
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"result": [
					{
						"securityId": f"sec_{index:03d}",
						"uid": 10000 + index,
						"encryptJobId": f"job_{index:03d}",
						"name": f"HR{index}",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": (
							"第七个未读"
							if index == 6
							else "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前是否还在招聘？"
						),
						"lastTS": 1700000000000 + index,
						"unreadMsgCount": 1 if index == 6 else 0,
					}
					for index in range(8)
				],
				"hasMore": False,
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		self.chat_history_calls.append((gid, security_id))
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"id": f"m_{gid}",
						"from": {"uid": int(gid), "name": "HR"},
						"type": 1,
						"text": "第七个未读" if security_id == "sec_006" else "你好",
						"time": 1700000000000,
					}
				]
			},
		}

	def close(self):
		return None


class _InboundBeyondRecentLimitPlatform(_UnreadBeyondRecentLimitPlatform):
	def friend_list(self, page=1):
		response = super().friend_list(page=page)
		for item in response["zpData"]["result"]:
			item["unreadMsgCount"] = 0
		return response


class _PagedMessagePlatform:
	def __init__(self):
		self.friend_list_pages: list[int] = []
		self.chat_history_calls: list[tuple[str, str]] = []

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		self.friend_list_pages.append(page)
		pages = {
			1: self._items(0, 5),
			2: self._items(5, 5),
			3: self._items(10, 2),
		}
		return {
			"code": 0,
			"zpData": {
				"result": pages.get(page, []),
				"hasMore": page < 3,
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		self.chat_history_calls.append((gid, security_id))
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"id": f"m_{gid}",
						"from": {"uid": int(gid), "name": "HR"},
						"type": 1,
						"text": f"第 {gid} 个会话",
						"time": 1700000000000,
					}
				]
			},
		}

	def close(self):
		return None

	@staticmethod
	def _items(start: int, count: int):
		return [
			{
				"securityId": f"sec_{index:03d}",
				"uid": 10000 + index,
				"encryptJobId": f"job_{index:03d}",
				"name": f"HR{index}",
				"brandName": "TestCo",
				"title": "HRBP",
				"lastMsg": "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前是否还在招聘？",
				"lastTS": 1700000000000 + index,
			}
			for index in range(start, start + count)
		]


class _DuplicateTimestampMessagePlatform:
	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"result": [
					{
						"securityId": "sec_dup",
						"uid": 44798248,
						"encryptJobId": "job_dup",
						"name": "张HR",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "你好",
						"lastTS": 1780543293000,
					}
				],
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		assert gid == "44798248"
		assert security_id == "sec_dup"
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"type": 3,
						"time": 1780543293000,
						"from": {"uid": 44798248, "name": "张HR"},
						"text": "",
					},
					{
						"type": 3,
						"time": 1780543293000,
						"from": {"uid": 44798248, "name": "张HR"},
						"text": "你好，我们正在诚聘大模型应用开发，有兴趣聊聊吗",
					},
					{
						"type": 4,
						"time": 1780543293000,
						"from": {"uid": 44798248, "name": "张HR"},
						"text": "",
					},
					{
						"type": 4,
						"time": 1780543293000,
						"from": {"uid": 44798248, "name": "张HR"},
						"text": "",
					},
				]
			},
		}

	def close(self):
		return None


class _RotatingSecurityMessagePlatform:
	def __init__(self):
		self.calls = 0

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		self.calls += 1
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"result": [
					{
						"securityId": f"sec_rotating_{self.calls}",
						"uid": 755278482,
						"friendId": 755278482,
						"encryptJobId": "job_resume",
						"name": "李HR",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "对方已查看了您的附件简历",
						"lastTS": 1781746548734,
					}
				],
			},
		}

	def chat_history(self, gid, security_id, page=1, count=50):
		assert gid == "755278482"
		assert security_id.startswith("sec_rotating_")
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"mid": 354743700415492,
						"securityId": security_id,
						"type": 4,
						"time": 1781746548734,
						"from": {"uid": 755278482, "name": "李HR"},
						"body": {"text": "对方已查看了您的附件简历"},
					}
				]
			},
		}

	def close(self):
		return None


class _DialogResumeRequestPlatform:
	def __init__(self):
		self.friend_list_pages: list[int] = []
		self.chat_history_calls: list[tuple[str, str]] = []

	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		self.friend_list_pages.append(page)
		assert page == 1
		items = [
			{
				"securityId": f"sec_{index:03d}",
				"uid": 10000 + index,
				"encryptJobId": f"job_{index:03d}",
				"name": f"HR{index}",
				"brandName": "TestCo",
				"title": "HRBP",
				"lastMsg": "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前是否还在招聘？",
				"lastTS": 1700000000000 + index,
				"lastMessageInfo": {
					"msgId": f"m_{index}",
					"fromId": 99999,
					"toId": 10000 + index,
					"showText": "我是候选人的求职助理 Agent，您好，想跟进一下这个岗位目前是否还在招聘？",
				},
			}
			for index in range(100)
		]
		items[1] = {
			"securityId": "sec_dialog",
			"uid": 564424706,
			"encryptJobId": "job_dialog",
			"name": "齐女士",
			"brandName": "卓越际联科技有限公司",
			"title": "招聘专员",
			"lastMsg": "",
			"lastTS": 1782023873843,
			"lastMessageInfo": {
				"msgId": 355879624061954,
				"fromId": 564424706,
				"toId": 622581782,
				"showText": "",
			},
		}
		return {"code": 0, "zpData": {"result": items, "hasMore": False}}

	def chat_history(self, gid, security_id, page=1, count=50):
		self.chat_history_calls.append((gid, security_id))
		return {
			"code": 0,
			"zpData": {
				"messages": [
					{
						"mid": 355879624061954,
						"type": 1,
						"bizType": 13,
						"time": 1782023873843,
						"from": {"uid": 564424706, "name": "齐女士"},
						"body": {
							"type": 7,
							"templateId": 1,
							"dialog": {
								"text": "我想要一份您的附件简历，您是否同意",
								"buttons": [
									{"text": "同意", "url": "bosszp://bosszhipin.app/openwith?type=sendaction&uid=564424706&aid=38&extends={}"},
									{"text": "拒绝", "url": "bosszp://bosszhipin.app/openwith?type=sendaction&uid=564424706&aid=39&extends={}"},
								],
								"operated": False,
							},
						},
					}
				]
			},
		}

	def close(self):
		return None


class _DuplicateRecentTargetPlatform:
	def is_success(self, response):
		return response.get("code") == 0

	def unwrap_data(self, response):
		return response.get("zpData")

	def parse_error(self, response):
		return ("UNKNOWN", response.get("message", ""))

	def friend_list(self, page=1):
		assert page == 1
		return {
			"code": 0,
			"zpData": {
				"hasMore": False,
				"result": [
					{
						"securityId": "sec_recent_001",
						"uid": 755278482,
						"friendId": 755278482,
						"encryptJobId": "job_resume",
						"name": "李HR",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "对方已查看了您的附件简历",
						"lastTS": 1781746548734,
					},
					{
						"securityId": "sec_recent_002",
						"uid": 755278482,
						"friendId": 755278482,
						"encryptJobId": "job_resume",
						"name": "李HR",
						"brandName": "TestCo",
						"title": "HRBP",
						"lastMsg": "对方已查看了您的附件简历",
						"lastTS": 1781746548734,
					},
				],
			},
		}

	def close(self):
		return None


def test_sync_jobs_maps_platform_job_detail_to_local_summary(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_JobPlatform(), store=store)

	result = adapter.sync_jobs(query="golang")

	assert result.count == 1
	assert result.synced_job_ids == ["job_001"]
	stored = store.get_job("job_001")
	assert stored is not None
	assert stored.title == "Go 开发"
	assert stored.company == "TestCo"
	assert stored.summary
	assert "后端服务开发" in stored.summary
	assert stored.source == "boss_sync"


def test_sync_messages_saves_conversation_and_inbound_messages(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_MessagePlatform(), store=store)

	result = adapter.sync_messages()

	assert result.count == 1
	assert result.conversation_ids == ["boss_conv_12345"]
	assert result.message_ids == ["boss_msg_12345_m_001"]
	conversation = store.get_conversation("boss_conv_12345")
	assert conversation is not None
	assert conversation.recruiter_id == "boss_recruiter_12345"
	assert conversation.job_id == "job_001"
	assert conversation.state["security_id"] == "sec_001"
	assert conversation.state["gid"] == "12345"
	assert conversation.state["uid"] == "12345"
	assert conversation.state["friend_id"] == "12345"
	assert conversation.state["encrypt_boss_id"] == "enc_boss_001"
	assert conversation.state["recruiter_name"] == "张HR"
	assert conversation.state["company"] == "TestCo"
	assert conversation.state["title"] == "HRBP"

	messages = store.list_messages("boss_conv_12345")
	assert len(messages) == 1
	assert messages[0].direction == "inbound"
	assert messages[0].message_text == "方便加微信吗？"
	assert messages[0].source == "boss_sync"

	recruiter = store.get_recruiter("boss_recruiter_12345")
	assert recruiter is not None
	assert recruiter.display_name == "张HR"
	assert recruiter.company == "TestCo"


def test_list_pipeline_candidates_returns_read_no_reply_targets(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_PipelineCandidatePlatform(), store=store)

	candidates = adapter.list_pipeline_candidates(
		now_ts_ms=1700000000000 + 5 * 24 * 3600 * 1000,
		stale_days=3,
	)

	assert len(candidates) == 1
	candidate = candidates[0]
	assert candidate["stage"] == "read_no_reply"
	assert candidate["security_id"] == "sec_read"
	assert candidate["job_id"] == "job_001"
	assert candidate["company"] == "TestCo"
	assert candidate["title"] == "AI 工程师"
	assert candidate["msg_status"] == "已读"
	assert candidate["reason"] == "对方已读未回，建议主动跟进"
	assert candidate["gid"] == "12345"
	assert candidate["friend_id"] == "12345"
	assert candidate["uid"] == "12345"
	assert candidate["encrypt_boss_id"] == "enc_boss_001"
	assert candidate["recruiter_name"] == "张HR"
	assert candidate["recruiter_id"] == "boss_recruiter_12345"


def test_sync_messages_advances_current_page_in_five_item_batches(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _RecentOnlyMessagePlatform()
	first_adapter = BossAutomationAdapter(platform=platform, store=store)
	second_adapter = BossAutomationAdapter(platform=platform, store=store)

	first = first_adapter.sync_messages()
	second = second_adapter.sync_messages()

	assert platform.friend_list_pages == [1, 1]
	assert platform.chat_history_calls[:5] == [
		("10000", "sec_000"),
		("10001", "sec_001"),
		("10002", "sec_002"),
		("10003", "sec_003"),
		("10004", "sec_004"),
	]
	assert platform.chat_history_calls[5:10] == [
		("10005", "sec_005"),
		("10006", "sec_006"),
		("10007", "sec_007"),
		("10008", "sec_008"),
		("10009", "sec_009"),
	]
	assert first.count == 5
	assert len(first.conversation_ids) == 5
	assert second.count == 5
	assert len(second.conversation_ids) == 5


def test_sync_messages_prioritizes_unread_conversations_on_current_page(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _UnreadBeyondRecentLimitPlatform()
	first_adapter = BossAutomationAdapter(platform=platform, store=store)
	second_adapter = BossAutomationAdapter(platform=platform, store=store)

	first = first_adapter.sync_messages()
	second = second_adapter.sync_messages()

	assert platform.friend_list_pages == [1, 1]
	assert platform.chat_history_calls[:1] == [("10006", "sec_006")]
	assert platform.chat_history_calls[1:6] == [
		("10000", "sec_000"),
		("10001", "sec_001"),
		("10002", "sec_002"),
		("10003", "sec_003"),
		("10004", "sec_004"),
	]
	assert "boss_conv_10006" in first.conversation_ids
	assert "boss_conv_10006" not in second.conversation_ids
	messages = store.list_messages("boss_conv_10006")
	assert len(messages) == 1
	assert messages[0].message_text == "第七个未读"


def test_sync_messages_resets_legacy_cursor_to_unread_priority(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="boss_messages_synced",
			entity_type="sync_batch",
			entity_id="legacy_cursor",
			payload={"next_cursor": {"page": 1, "offset": 5}},
		)
	)
	platform = _UnreadBeyondRecentLimitPlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	result = adapter.sync_messages()

	assert platform.chat_history_calls[:1] == [("10006", "sec_006")]
	assert result.conversation_ids == ["boss_conv_10006"]


def test_sync_messages_resets_unversioned_priority_cursor(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="boss_messages_synced",
			entity_type="sync_batch",
			entity_id="legacy_priority_cursor",
			payload={"next_cursor": {"page": 1, "offset": 5, "priority": "normal"}},
		)
	)
	platform = _InboundBeyondRecentLimitPlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	result = adapter.sync_messages()

	assert platform.chat_history_calls[:1] == [("10006", "sec_006")]
	assert result.conversation_ids == ["boss_conv_10006"]


def test_sync_messages_prioritizes_inbound_last_message_without_unread_count(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _InboundBeyondRecentLimitPlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	result = adapter.sync_messages()

	assert platform.chat_history_calls[:1] == [("10006", "sec_006")]
	assert result.conversation_ids == ["boss_conv_10006"]


def test_sync_messages_prioritizes_blank_dialog_resume_request_during_normal_cursor(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	store.append_audit_log(
		AuditLogRecord.new(
			event_type="boss_messages_synced",
			entity_type="sync_batch",
			entity_id="normal_cursor",
			payload={
				"next_cursor": {
					"page": 1,
					"offset": 75,
					"priority": "normal",
					"priority_version": 2,
				}
			},
		)
	)
	platform = _DialogResumeRequestPlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	result = adapter.sync_messages()

	assert platform.chat_history_calls[:1] == [("564424706", "sec_dialog")]
	assert result.conversation_ids == ["boss_conv_564424706"]
	assert result.message_ids == ["boss_msg_564424706_355879624061954"]
	messages = store.list_messages("boss_conv_564424706")
	assert len(messages) == 1
	assert messages[0].message_text == "我想要一份您的附件简历，您是否同意"
	assert messages[0].message_type == "1"


def test_sync_messages_advances_friend_list_pages_in_five_item_batches(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _PagedMessagePlatform()
	first_adapter = BossAutomationAdapter(platform=platform, store=store)
	second_adapter = BossAutomationAdapter(platform=platform, store=store)
	third_adapter = BossAutomationAdapter(platform=platform, store=store)
	fourth_adapter = BossAutomationAdapter(platform=platform, store=store)

	first = first_adapter.sync_messages()
	second = second_adapter.sync_messages()
	third = third_adapter.sync_messages()
	fourth = fourth_adapter.sync_messages()

	assert platform.friend_list_pages == [1, 2, 3, 1]
	assert len(platform.chat_history_calls) == 17
	assert platform.chat_history_calls[0:5] == [
		("10000", "sec_000"),
		("10001", "sec_001"),
		("10002", "sec_002"),
		("10003", "sec_003"),
		("10004", "sec_004"),
	]
	assert platform.chat_history_calls[5:10] == [
		("10005", "sec_005"),
		("10006", "sec_006"),
		("10007", "sec_007"),
		("10008", "sec_008"),
		("10009", "sec_009"),
	]
	assert platform.chat_history_calls[10:12] == [
		("10010", "sec_010"),
		("10011", "sec_011"),
	]
	assert platform.chat_history_calls[12:17] == platform.chat_history_calls[0:5]
	assert first.count == 5
	assert second.count == 5
	assert third.count == 2
	assert fourth.count == 5
	assert store.get_conversation("boss_conv_10011") is not None


def test_sync_messages_uses_content_fingerprint_when_timestamp_collides(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_DuplicateTimestampMessagePlatform(), store=store)

	result = adapter.sync_messages()

	assert result.count == 1
	assert len(result.message_ids) == 1
	assert len(set(result.message_ids)) == 1
	messages = store.list_messages("boss_conv_44798248")
	assert len(messages) == 1
	assert len({message.message_id for message in messages}) == 1
	assert messages[0].message_text == "你好，我们正在诚聘大模型应用开发，有兴趣聊聊吗"


def test_sync_messages_keeps_identity_stable_when_security_id_rotates(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _RotatingSecurityMessagePlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	first = adapter.sync_messages()
	second = adapter.sync_messages()

	assert first.conversation_ids == ["boss_conv_755278482"]
	assert second.conversation_ids == ["boss_conv_755278482"]
	assert first.message_ids == ["boss_msg_755278482_354743700415492"]
	assert second.message_ids == ["boss_msg_755278482_354743700415492"]
	messages = store.list_messages("boss_conv_755278482")
	assert len(messages) == 1
	assert messages[0].raw["securityId"] == "sec_rotating_2"


def test_list_recent_targets_dedupes_rotating_security_ids(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_DuplicateRecentTargetPlatform(), store=store)

	targets = adapter.list_recent_targets(limit=5)

	assert len(targets) == 1
	assert targets[0].conversation_id == "boss_conv_755278482"
