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
	assert "BOSS_RAG_READ_NO_REPLY_STALE_DAYS=0" in output
	assert "--json" not in output
	assert "agent watcher-run --loop --live-sync --ensure-chat-page" in output


def test_agent_auto_reply_stops_existing_watcher_before_starting():
	result = _make("--dry-run", "agent-auto-reply")

	output = (result.stdout + result.stderr).replace("\\\n", " ")
	assert result.returncode == 0, output
	stop_index = output.find("pgrep -f")
	start_index = output.find("Starting live Boss Agent auto replies")
	assert stop_index >= 0, output
	assert start_index >= 0, output
	assert stop_index < start_index, output
	assert "agent watcher-run --loo[p]" in output


def test_help_mentions_agent_auto_reply_make_target():
	result = _make("help")

	output = result.stdout + result.stderr
	assert result.returncode == 0, output
	assert "make agent-auto-reply" in output
	assert "AGENT_READ_NO_REPLY_STALE_DAYS=0" in output
