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
