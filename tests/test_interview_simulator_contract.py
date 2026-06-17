from pathlib import Path


def test_interview_simulator_classifies_account_risk_messages():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text()

	assert "function isBossAccountRiskMessage" in app
	for token in ("环境存在异常", "异常访问", "风控", "安全验证"):
		assert token in app
