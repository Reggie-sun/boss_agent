"""Configuration helpers for the passive Boss Agent watcher."""

from __future__ import annotations

from dataclasses import dataclass


class WatcherConfigError(ValueError):
    """Raised when watcher configuration is missing or unsafe."""


@dataclass(slots=True)
class WatcherConfig:
    enabled: bool
    dry_run: bool
    contact_phone: str
    contact_wechat: str
    interview_windows: str
    resume_attachment_path: str
    poll_seconds: int = 20
    max_failures_per_conversation: int = 3
    live_sync: bool = False
    require_send_enabled: bool = True
    send_enabled: bool = False

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> "WatcherConfig":
        return cls(
            enabled=bool(values.get("boss_rag_watcher_enabled", False)),
            dry_run=bool(values.get("boss_rag_watcher_dry_run", True)),
            contact_phone=str(values.get("boss_rag_contact_phone") or "").strip(),
            contact_wechat=str(values.get("boss_rag_contact_wechat") or "").strip(),
            interview_windows=str(values.get("boss_rag_interview_windows") or "").strip(),
            resume_attachment_path=str(
                values.get("boss_rag_resume_attachment_path") or ""
            ).strip(),
            poll_seconds=max(5, int(values.get("boss_rag_watcher_poll_seconds") or 20)),
            max_failures_per_conversation=max(
                1,
                int(values.get("boss_rag_watcher_max_failures_per_conversation") or 3),
            ),
            live_sync=bool(values.get("boss_rag_watcher_live_sync", False)),
            require_send_enabled=bool(
                values.get("boss_rag_watcher_require_send_enabled", True)
            ),
            send_enabled=bool(values.get("boss_rag_send_enabled", False)),
        )


def _require_unique(value: str, key: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise WatcherConfigError(f"{key} is required for automatic watcher replies.")
    separators = [",", "，", ";", "；", "/", "|"]
    if any(separator in normalized for separator in separators):
        raise WatcherConfigError(f"{key} must be unique for automatic watcher replies.")
    return normalized


def _require_present(value: str, key: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise WatcherConfigError(f"{key} is required for automatic watcher replies.")
    return normalized


def build_contact_reply(config: WatcherConfig) -> str:
    phone = _require_unique(config.contact_phone, "boss_rag_contact_phone")
    wechat = _require_unique(config.contact_wechat, "boss_rag_contact_wechat")
    return f"我的手机号是 {phone}，微信号是 {wechat}。"


def salary_handoff_reply() -> str:
    return (
        "我是候选人的求职助理 Agent，薪资相关问题需要候选人本人确认后回复。"
        "我已经记录下来，会提醒本人尽快处理。"
    )


def salary_preset_reply(value: str) -> str:
    normalized = value.strip()
    return normalized or salary_handoff_reply()


def build_interview_window_reply(config: WatcherConfig) -> str:
    windows = _require_present(config.interview_windows, "boss_rag_interview_windows")
    return (
        f"可以的，我这边通常{windows}方便面试。"
        "您可以发几个可选时间，我确认后会尽快回复。"
    )
