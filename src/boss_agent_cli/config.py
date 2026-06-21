import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
	"default_city": None,
	"default_salary": None,
	"request_delay": [1.5, 3.0],
	"batch_greet_delay": [1.0, 10.0],
	"batch_greet_max": 150,
	"log_level": "error",
	"login_timeout": 120,
	"cdp_url": "http://localhost:9229",
	"export_dir": None,
	"resume_default_template": "default",
	"resume_export_format": "pdf",
	"platform": "zhipin",
	"role": "candidate",
	"low_risk_mode": True,
	"boss_rag_db_path": None,
	"boss_rag_rag_base_url": None,
	"boss_rag_rag_timeout_seconds": 20,
	"boss_rag_rag_api_key": None,
	"boss_rag_rag_auth_mode": "none",
	"boss_rag_allow_message_read": False,
	"boss_rag_send_enabled": False,
	"boss_rag_watcher_enabled": False,
	"boss_rag_watcher_dry_run": True,
	"boss_rag_watcher_live_sync": False,
	"boss_rag_watcher_poll_seconds": 20,
	"boss_rag_watcher_max_failures_per_conversation": 3,
	"boss_rag_read_no_reply_followup_limit_per_cycle": 1,
	"boss_rag_read_no_reply_followup_min_interval_seconds": 300,
	"boss_rag_watcher_require_send_enabled": True,
	"boss_rag_proactive_resume_enabled": False,
	"boss_rag_contact_phone": "",
	"boss_rag_contact_wechat": "",
	"boss_rag_interview_windows": "",
	"boss_rag_resume_attachment_path": "",
	"boss_rag_salary_reply": None,
	"boss_apply_auto_enabled": True,
	"boss_batch_greet_auto_enabled": False,
}

ENV_ALIASES: dict[str, tuple[str, ...]] = {
	"boss_rag_rag_base_url": ("BOSS_RAG_RAG_BASE_URL",),
	"boss_rag_rag_timeout_seconds": ("BOSS_RAG_RAG_TIMEOUT_SECONDS",),
	"boss_rag_rag_api_key": ("BOSS_RAG_RAG_API_KEY", "RAG_API_KEY", "RAG_AUTH_API_KEY"),
	"boss_rag_rag_auth_mode": ("BOSS_RAG_RAG_AUTH_MODE",),
	"boss_rag_allow_message_read": ("BOSS_RAG_ALLOW_MESSAGE_READ",),
	"boss_rag_send_enabled": ("BOSS_RAG_SEND_ENABLED",),
	"boss_rag_watcher_enabled": ("BOSS_RAG_WATCHER_ENABLED",),
	"boss_rag_watcher_dry_run": ("BOSS_RAG_WATCHER_DRY_RUN",),
	"boss_rag_watcher_live_sync": ("BOSS_RAG_WATCHER_LIVE_SYNC",),
	"boss_rag_watcher_poll_seconds": ("BOSS_RAG_WATCHER_POLL_SECONDS",),
	"boss_rag_watcher_max_failures_per_conversation": ("BOSS_RAG_WATCHER_MAX_FAILURES_PER_CONVERSATION",),
	"boss_rag_read_no_reply_followup_limit_per_cycle": ("BOSS_RAG_READ_NO_REPLY_FOLLOWUP_LIMIT_PER_CYCLE",),
	"boss_rag_read_no_reply_followup_min_interval_seconds": ("BOSS_RAG_READ_NO_REPLY_FOLLOWUP_MIN_INTERVAL_SECONDS",),
	"boss_rag_watcher_require_send_enabled": ("BOSS_RAG_WATCHER_REQUIRE_SEND_ENABLED",),
	"boss_rag_proactive_resume_enabled": ("BOSS_RAG_PROACTIVE_RESUME_ENABLED",),
	"boss_rag_contact_phone": ("BOSS_RAG_CONTACT_PHONE",),
	"boss_rag_contact_wechat": ("BOSS_RAG_CONTACT_WECHAT",),
	"boss_rag_interview_windows": ("BOSS_RAG_INTERVIEW_WINDOWS",),
	"boss_rag_resume_attachment_path": ("BOSS_RAG_RESUME_ATTACHMENT_PATH",),
	"boss_rag_salary_reply": ("BOSS_RAG_SALARY_REPLY",),
	"boss_apply_auto_enabled": ("BOSS_APPLY_AUTO_ENABLED",),
	"boss_batch_greet_auto_enabled": ("BOSS_BATCH_GREET_AUTO_ENABLED",),
}


def load_config(config_path: Path | None) -> dict[str, Any]:
	cfg = dict(DEFAULTS)
	if config_path and config_path.exists():
		with open(config_path) as f:
			user_cfg = json.load(f)
		cfg.update(user_cfg)
	for key, env_names in ENV_ALIASES.items():
		override = _read_env_override(env_names)
		if override is not None:
			cfg[key] = _parse_env_value(override, DEFAULTS[key])
	return cfg


def load_project_dotenv(dotenv_path: Path | None = None) -> None:
	"""Load simple KEY=VALUE pairs from a local .env without overriding exported env."""
	resolved_path = dotenv_path or Path.cwd() / ".env"
	if not resolved_path.exists():
		return
	for raw_line in resolved_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		if not key or key in os.environ:
			continue
		os.environ[key] = _strip_env_quotes(value.strip())


def config_env_sources() -> dict[str, str]:
	"""Return config keys currently overridden by environment variables."""
	sources: dict[str, str] = {}
	for key, env_names in ENV_ALIASES.items():
		for env_name in env_names:
			if os.getenv(env_name) not in (None, ""):
				sources[key] = env_name
				break
	return sources


def _read_env_override(env_names: tuple[str, ...]) -> str | None:
	for env_name in env_names:
		value = os.getenv(env_name)
		if value not in (None, ""):
			return value
	return None


def _parse_env_value(raw: str, default: Any) -> Any:
	if default is None:
		return raw
	if isinstance(default, bool):
		return raw.strip().lower() in ("true", "1", "yes", "on")
	if isinstance(default, int):
		return int(raw)
	if isinstance(default, float):
		return float(raw)
	if isinstance(default, list):
		return [part.strip() for part in raw.split(",")]
	return raw


def _strip_env_quotes(value: str) -> str:
	if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
		return value[1:-1]
	return value
