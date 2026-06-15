import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "stack_readiness.py"


def load_module():
	spec = importlib.util.spec_from_file_location("stack_readiness", SCRIPT_PATH)
	assert spec is not None and spec.loader is not None
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def test_stack_readiness_script_exists():
	assert SCRIPT_PATH.exists()


def test_stack_readiness_defines_required_checks():
	module = load_module()
	check_names = [check.name for check in module.DEFAULT_CHECKS]
	assert check_names == ["cdp", "boss_auth", "agent", "rag"]


def test_load_config_reads_repo_defaults():
	module = load_module()
	config = module.load_config_from_repo(ROOT)
	assert config.cdp_url == "http://localhost:9222"
	assert config.agent_base_url == "http://127.0.0.1:5175"
	assert config.rag_base_url == "http://127.0.0.1:8020"
	assert config.rag_auth_mode == "bearer"
	assert config.rag_api_key


def test_evaluate_boss_auth_complete_is_ready():
	module = load_module()
	spec = module.CheckSpec(
		name="boss_auth",
		purpose="auth",
		target="boss status",
		failure_classification="env_error",
	)
	payload = {
		"ok": True,
		"data": {
			"auth_state": "complete",
			"auth_summary": "healthy",
			"checks": [
				{"name": "wt2_presence", "status": "ok"},
				{"name": "stoken_presence", "status": "ok"},
			],
		},
	}
	result = module.evaluate_boss_auth_check(spec, payload)
	assert result.status == "pass"
	assert result.meta["wt2_status"] == "ok"
	assert result.meta["stoken_status"] == "ok"


def test_evaluate_boss_auth_partial_warns():
	module = load_module()
	spec = module.CheckSpec(
		name="boss_auth",
		purpose="auth",
		target="boss status",
		failure_classification="env_error",
	)
	payload = {
		"ok": True,
		"data": {
			"auth_state": "partial",
			"auth_summary": "degraded",
			"auth_health": {"recovery_action": "refresh login"},
			"checks": [],
		},
	}
	result = module.evaluate_boss_auth_check(spec, payload)
	assert result.status == "warn"
	assert result.recovery_action == "refresh login"


def test_runner_marks_all_ready_only_when_everything_passes():
	module = load_module()
	config = module.ReadinessConfig(
		cdp_url="http://localhost:9222",
		agent_base_url="http://127.0.0.1:5175",
		rag_base_url="http://127.0.0.1:8020",
		rag_auth_mode="bearer",
		rag_api_key="demo",
		data_dir="~/.boss-agent",
		status_live=False,
		timeout_seconds=1.0,
		wait_seconds=0.0,
		interval_seconds=0.1,
	)

	def fake_http_get(url, headers=None, timeout_seconds=3.0):
		if url.endswith("/json/version"):
			return 200, {"Browser": "Chrome/147", "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/demo"}
		if url.endswith("/api/agent/health"):
			return 200, {
				"configured": True,
				"ready": True,
				"endpoint": "/api/agent/ask + /api/agent/send",
				"browserChannel": {"available": True, "mode": "cdp"},
			}
		if url.endswith("/api/v1/health"):
			return 200, {"status": "ok", "app_name": "Enterprise-grade RAG API"}
		raise AssertionError(url)

	def fake_boss_status(repo_root, *, data_dir, live, timeout_seconds):
		return 0, {
			"ok": True,
			"data": {
				"auth_state": "complete",
				"auth_summary": "healthy",
				"checks": [
					{"name": "wt2_presence", "status": "ok"},
					{"name": "stoken_presence", "status": "ok"},
				],
			},
		}, ""

	runner = module.ReadinessRunner(
		config,
		http_get_json=fake_http_get,
		run_boss_status=fake_boss_status,
	)
	report = runner.run_once()
	assert report["all_ready"] is True
	assert [item["status"] for item in report["checks"]] == ["pass", "pass", "pass", "pass"]
