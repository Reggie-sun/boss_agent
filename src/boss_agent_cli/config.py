import json
import os
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
	"default_city": None,
	"default_salary": None,
	"request_delay": [1.5, 3.0],
	"batch_greet_delay": [2.0, 5.0],
	"batch_greet_max": 10,
	"log_level": "error",
	"login_timeout": 120,
	"cdp_url": None,
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
}

ENV_ALIASES: dict[str, tuple[str, ...]] = {
	"boss_rag_rag_base_url": ("BOSS_RAG_RAG_BASE_URL",),
	"boss_rag_rag_timeout_seconds": ("BOSS_RAG_RAG_TIMEOUT_SECONDS",),
	"boss_rag_rag_api_key": ("BOSS_RAG_RAG_API_KEY", "RAG_API_KEY", "RAG_AUTH_API_KEY"),
	"boss_rag_rag_auth_mode": ("BOSS_RAG_RAG_AUTH_MODE",),
	"boss_rag_allow_message_read": ("BOSS_RAG_ALLOW_MESSAGE_READ",),
	"boss_rag_send_enabled": ("BOSS_RAG_SEND_ENABLED",),
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
