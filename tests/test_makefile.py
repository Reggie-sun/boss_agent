from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _make(*args: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		["make", *args],
		cwd=ROOT,
		text=True,
		capture_output=True,
		check=False,
	)


def test_agent_auto_reply_make_target_runs_live_watcher_with_explicit_gates():
	result = _make("--dry-run", "agent-auto-reply")

	output = (result.stdout + result.stderr).replace("\\\n", " ")
	assert result.returncode == 0, output
	assert "BOSS_RAG_ALLOW_MESSAGE_READ=true" in output
	assert "BOSS_RAG_SEND_ENABLED=true" in output
	assert "BOSS_RAG_WATCHER_ENABLED=true" in output
	assert "BOSS_RAG_WATCHER_DRY_RUN=false" in output
	assert "BOSS_RAG_WATCHER_LIVE_SYNC=true" in output
	assert "BOSS_RAG_PROACTIVE_RESUME_ENABLED=true" in output
	assert "--json" not in output
	assert "agent watcher-run --loop --live-sync --ensure-chat-page" in output


def test_help_mentions_agent_auto_reply_make_target():
	result = _make("help")

	output = result.stdout + result.stderr
	assert result.returncode == 0, output
	assert "make agent-auto-reply" in output
