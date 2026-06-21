from pathlib import Path


def test_interview_simulator_uses_shared_boss_bridge_error_helpers():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text()
	helper = (repo_root / "demo" / "interview-simulator" / "src" / "bossBridgeErrors.js").read_text()

	assert 'from "./bossBridgeErrors.js"' in app
	assert "环境存在异常" not in app
	for token in (
		"bossBridgeErrorFromPayload",
		"bossBridgeErrorMessage",
		"inferBossBridgeErrorCodeFromMessage",
		"TOKEN_REFRESH_FAILED",
		"AUTH_EXPIRED",
	):
		assert token in helper


def test_interview_simulator_auto_greet_requires_profile_gate():
	repo_root = Path(__file__).resolve().parents[1]
	vite = (repo_root / "demo" / "interview-simulator" / "vite.config.mjs").read_text(encoding="utf-8")

	assert "ensureAutoGreetProfileGate" in vite
	assert "commercial_profile_required" in vite
	assert "profile_id 不能为空" in vite
	assert "outreach_auto_send_enabled" in vite
	assert "PROFILE_CONFIG_DISABLED" in vite
	assert "PROFILE_CONFIG_NOT_FOUND" in vite
	assert '"profile",\n      "config",\n      "get"' in vite
