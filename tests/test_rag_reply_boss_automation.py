from pathlib import Path

from boss_agent_cli.rag_reply.adapters.boss_automation import BossAutomationAdapter
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
		if page != 1:
			raise AssertionError("sync_messages should not deep-page friend_list in V1")
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
						"lastMsg": "你好",
						"lastTS": 1700000000000 + index,
					}
					for index in range(25)
				],
				"hasMore": None,
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
	assert result.conversation_ids == ["boss_conv_sec_001"]
	assert result.message_ids == ["boss_msg_sec_001_m_001"]
	conversation = store.get_conversation("boss_conv_sec_001")
	assert conversation is not None
	assert conversation.recruiter_id == "boss_recruiter_12345"
	assert conversation.job_id == "job_001"
	assert conversation.state["security_id"] == "sec_001"
	assert conversation.state["gid"] == "12345"

	messages = store.list_messages("boss_conv_sec_001")
	assert len(messages) == 1
	assert messages[0].direction == "inbound"
	assert messages[0].message_text == "方便加微信吗？"
	assert messages[0].source == "boss_sync"

	recruiter = store.get_recruiter("boss_recruiter_12345")
	assert recruiter is not None
	assert recruiter.display_name == "张HR"
	assert recruiter.company == "TestCo"


def test_sync_messages_limits_recent_conversations_without_deep_pagination(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	platform = _RecentOnlyMessagePlatform()
	adapter = BossAutomationAdapter(platform=platform, store=store)

	result = adapter.sync_messages()

	assert platform.friend_list_pages == [1]
	assert len(platform.chat_history_calls) == 5
	assert result.count == 5
	assert len(result.conversation_ids) == 5
	assert len(result.message_ids) == 5


def test_sync_messages_uses_content_fingerprint_when_timestamp_collides(tmp_path: Path):
	store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
	store.initialize()
	adapter = BossAutomationAdapter(platform=_DuplicateTimestampMessagePlatform(), store=store)

	result = adapter.sync_messages()

	assert result.count == 1
	assert len(result.message_ids) == 1
	assert len(set(result.message_ids)) == 1
	messages = store.list_messages("boss_conv_sec_dup")
	assert len(messages) == 1
	assert len({message.message_id for message in messages}) == 1
	assert messages[0].message_text == "你好，我们正在诚聘大模型应用开发，有兴趣聊聊吗"
