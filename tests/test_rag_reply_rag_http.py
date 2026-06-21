import httpx

from boss_agent_cli.rag_reply.adapters.rag_http import RagHttpAdapter


class _Response:
	def __init__(self, payload):
		self._payload = payload

	def raise_for_status(self):
		return None

	def json(self):
		return self._payload


def test_rag_http_calls_chat_ask_endpoint(monkeypatch):
	captured = {}

	def fake_post(url, *, json, timeout, headers=None):
		captured["url"] = url
		captured["json"] = json
		captured["timeout"] = timeout
		captured["headers"] = headers
		return _Response({"answer": "draft", "citations": [{"id": "c1"}]})

	monkeypatch.setattr(httpx, "post", fake_post)
	adapter = RagHttpAdapter(base_url="http://127.0.0.1:8020", timeout_seconds=12)

	result = adapter.answer(rag_question="HR question: hi", session_id="sess_001")

	assert result.ok is True
	assert captured["url"].endswith("/api/v1/chat/ask")
	assert "question" in captured["json"]
	assert "session_id" in captured["json"]
	assert "metadata" not in captured["json"]
	assert captured["headers"] is None


def test_rag_http_sends_optional_supported_scope_without_profile_metadata(monkeypatch):
	captured = {}

	def fake_post(url, *, json, timeout, headers=None):
		captured["json"] = json
		return _Response({"answer": "draft", "citations": []})

	monkeypatch.setattr(httpx, "post", fake_post)
	adapter = RagHttpAdapter(base_url="http://127.0.0.1:8020", timeout_seconds=12)

	result = adapter.answer(
		rag_question="HR question: hi",
		session_id="sess_001",
		document_id="doc_001",
		category_id="cat_001",
	)

	assert result.ok is True
	assert captured["json"]["document_id"] == "doc_001"
	assert captured["json"]["category_id"] == "cat_001"
	assert "metadata" not in captured["json"]
	assert "tenant_id" not in captured["json"]
	assert "user_id" not in captured["json"]
	assert "profile_id" not in captured["json"]
	assert "knowledge_base_id" not in captured["json"]


def test_rag_http_uses_x_api_key_header_when_configured(monkeypatch):
	captured = {}

	def fake_post(url, *, json, timeout, headers=None):
		captured["headers"] = headers
		return _Response({"answer": "draft", "citations": []})

	monkeypatch.setattr(httpx, "post", fake_post)
	adapter = RagHttpAdapter(
		base_url="http://127.0.0.1:8020",
		timeout_seconds=12,
		api_key="configured-rag-integration-key-123456",
		auth_mode="x_api_key",
	)

	result = adapter.answer(rag_question="HR question: hi", session_id="sess_001")

	assert result.ok is True
	assert captured["headers"] == {"X-API-Key": "configured-rag-integration-key-123456"}


def test_rag_http_uses_bearer_header_when_configured(monkeypatch):
	captured = {}

	def fake_post(url, *, json, timeout, headers=None):
		captured["headers"] = headers
		return _Response({"answer": "draft", "citations": []})

	monkeypatch.setattr(httpx, "post", fake_post)
	adapter = RagHttpAdapter(
		base_url="http://127.0.0.1:8020",
		timeout_seconds=12,
		api_key="configured-rag-integration-key-123456",
		auth_mode="bearer",
	)

	result = adapter.answer(rag_question="HR question: hi", session_id="sess_001")

	assert result.ok is True
	assert captured["headers"] == {"Authorization": "Bearer configured-rag-integration-key-123456"}


def test_rag_http_failure_returns_closed_result(monkeypatch):
	def fake_post(url, *, json, timeout, headers=None):
		raise httpx.ReadTimeout("timed out")

	monkeypatch.setattr(httpx, "post", fake_post)
	adapter = RagHttpAdapter(base_url="http://127.0.0.1:8020", timeout_seconds=12)

	result = adapter.answer(rag_question="HR question: hi", session_id="sess_001")

	assert result.ok is False
	assert result.audit_status == "rag_failed"
	assert result.send_allowed is False
	assert result.approval_required is True


def test_rag_http_rejects_unknown_auth_mode():
	adapter = RagHttpAdapter(
		base_url="http://127.0.0.1:8020",
		timeout_seconds=12,
		api_key="configured-rag-integration-key-123456",
		auth_mode="unknown_mode",
	)

	result = adapter.answer(rag_question="HR question: hi", session_id="sess_001")

	assert result.ok is False
	assert result.audit_status == "rag_failed"
	assert "Unknown boss_rag_rag_auth_mode" in str(result.error_message)
