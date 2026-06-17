import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CDP_URL = "http://localhost:9229"
DEFAULT_AGENT_BASE_URL = "http://127.0.0.1:5175"
DEFAULT_RAG_HEALTH_PATH = "/api/v1/health"


@dataclass(frozen=True)
class CheckSpec:
	name: str
	purpose: str
	target: str
	failure_classification: str
	critical: bool = True


@dataclass(frozen=True)
class CheckResult:
	name: str
	status: str
	target: str
	purpose: str
	failure_classification: str
	critical: bool
	detail: str
	recovery_action: str | None = None
	meta: dict[str, Any] | None = None

	def as_dict(self) -> dict[str, Any]:
		return asdict(self)


@dataclass(frozen=True)
class ReadinessConfig:
	cdp_url: str
	agent_base_url: str
	rag_base_url: str
	rag_auth_mode: str
	rag_api_key: str
	data_dir: str
	status_live: bool
	timeout_seconds: float
	wait_seconds: float
	interval_seconds: float


def build_default_checks(config: ReadinessConfig) -> list[CheckSpec]:
	return [
		CheckSpec(
			name="cdp",
			purpose="验证 Chrome DevTools Protocol 调试入口可访问",
			target=f"{config.cdp_url}/json/version",
			failure_classification="service_error",
		),
		CheckSpec(
			name="boss_auth",
			purpose="验证 Boss 登录态是否通过只读在线探测，可真实进入发送链路",
			target="boss status --live" if config.status_live else "boss status",
			failure_classification="env_error",
		),
		CheckSpec(
			name="agent",
			purpose="验证 demo Agent bridge 已启动并且本地 workflow 可初始化",
			target=f"{config.agent_base_url}/api/agent/health",
			failure_classification="service_error",
		),
		CheckSpec(
			name="rag",
			purpose="验证 Enterprise RAG health endpoint 可访问",
			target=f"{config.rag_base_url}{DEFAULT_RAG_HEALTH_PATH}",
			failure_classification="service_error",
		),
	]


DEFAULT_DOTENV_KEYS = {
	"BOSS_RAG_RAG_BASE_URL",
	"BOSS_RAG_RAG_AUTH_MODE",
	"BOSS_RAG_RAG_API_KEY",
	"RAG_API_KEY",
	"RAG_AUTH_API_KEY",
	"BOSS_RAG_CDP_URL",
	"BOSS_CDP_URL",
	"BOSS_RAG_DATA_DIR",
}


def parse_env_file(file_path: Path) -> dict[str, str]:
	if not file_path.exists():
		return {}
	values: dict[str, str] = {}
	for raw_line in file_path.read_text(encoding="utf-8").splitlines():
		line = raw_line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		key = key.strip()
		if not key:
			continue
		values[key] = value.strip().strip("'").strip('"')
	return values


def _config_value(env_values: dict[str, str], *keys: str, fallback: str = "") -> str:
	for key in keys:
		value = os.environ.get(key)
		if value not in (None, ""):
			return value
		file_value = env_values.get(key)
		if file_value not in (None, ""):
			return file_value
	return fallback


def load_config_from_repo(repo_root: Path) -> ReadinessConfig:
	env_values = parse_env_file(repo_root / ".env")
	return ReadinessConfig(
		cdp_url=_config_value(env_values, "BOSS_RAG_CDP_URL", "BOSS_CDP_URL", fallback=DEFAULT_CDP_URL).rstrip("/"),
		agent_base_url=_config_value(env_values, "BOSS_STACK_AGENT_BASE_URL", fallback=DEFAULT_AGENT_BASE_URL).rstrip("/"),
		rag_base_url=_config_value(env_values, "BOSS_RAG_RAG_BASE_URL", fallback="").rstrip("/"),
		rag_auth_mode=_config_value(env_values, "BOSS_RAG_RAG_AUTH_MODE", fallback="none").strip().lower(),
		rag_api_key=_config_value(env_values, "BOSS_RAG_RAG_API_KEY", "RAG_API_KEY", "RAG_AUTH_API_KEY", fallback="").strip(),
		data_dir=_config_value(env_values, "BOSS_RAG_DATA_DIR", fallback="~/.boss-agent").strip() or "~/.boss-agent",
		status_live=True,
		timeout_seconds=8.0,
		wait_seconds=0.0,
		interval_seconds=2.0,
	)


def _build_headers(auth_mode: str, api_key: str) -> dict[str, str]:
	headers = {"Accept": "application/json"}
	if auth_mode == "bearer" and api_key:
		headers["Authorization"] = f"Bearer {api_key}"
	elif auth_mode == "x-api-key" and api_key:
		headers["X-API-Key"] = api_key
	return headers


def _http_get_json(url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 3.0) -> tuple[int, dict[str, Any]]:
	req = request.Request(url, headers=headers or {}, method="GET")
	try:
		with request.urlopen(req, timeout=timeout_seconds) as resp:
			body = resp.read().decode("utf-8")
			return resp.getcode(), json.loads(body) if body else {}
	except error.HTTPError as exc:
		body = exc.read().decode("utf-8", errors="replace")
		payload: dict[str, Any]
		try:
			payload = json.loads(body) if body else {}
		except json.JSONDecodeError:
			payload = {"raw_body": body}
		return exc.code, payload


def _run_boss_status(
	repo_root: Path,
	*,
	data_dir: str,
	live: bool,
	timeout_seconds: float,
) -> tuple[int, dict[str, Any], str]:
	command = [
		sys.executable,
		"-c",
		"from boss_agent_cli.main import cli; import sys; cli.main(args=sys.argv[1:], standalone_mode=False)",
		"--json",
		"--data-dir",
		data_dir,
		"status",
	]
	if live:
		command.append("--live")
	env = dict(os.environ)
	python_path = env.get("PYTHONPATH", "")
	env["PYTHONPATH"] = f"{repo_root / 'src'}:{python_path}" if python_path else str(repo_root / "src")
	completed = subprocess.run(
		command,
		cwd=repo_root,
		capture_output=True,
		text=True,
		timeout=timeout_seconds,
		check=False,
		env=env,
	)
	payload = json.loads(completed.stdout.strip() or "{}")
	return completed.returncode, payload, completed.stderr.strip()


def evaluate_cdp_check(spec: CheckSpec, payload: dict[str, Any]) -> CheckResult:
	ws_url = str(payload.get("webSocketDebuggerUrl") or "").strip()
	browser = str(payload.get("Browser") or "").strip()
	if ws_url:
		return CheckResult(
			name=spec.name,
			status="pass",
			target=spec.target,
			purpose=spec.purpose,
			failure_classification=spec.failure_classification,
			critical=spec.critical,
			detail=f"CDP 可用：{browser or 'unknown browser'}",
			meta={"webSocketDebuggerUrl": ws_url, "browser": browser or None},
		)
	return CheckResult(
		name=spec.name,
		status="fail",
		target=spec.target,
		purpose=spec.purpose,
		failure_classification=spec.failure_classification,
		critical=spec.critical,
		detail="CDP 返回体缺少 webSocketDebuggerUrl。",
		recovery_action="启动 Chrome 并带上 --remote-debugging-port=9229，或改脚本参数指向正确的 CDP 地址。",
		meta={"browser": browser or None},
	)


def evaluate_boss_auth_check(spec: CheckSpec, payload: dict[str, Any]) -> CheckResult:
	if not payload.get("ok"):
		error_payload = payload.get("error") or {}
		return CheckResult(
			name=spec.name,
			status="fail",
			target=spec.target,
			purpose=spec.purpose,
			failure_classification=spec.failure_classification,
			critical=spec.critical,
			detail=str(error_payload.get("message") or "boss status 失败。"),
			recovery_action=str(error_payload.get("recovery_action") or "先运行 boss doctor / boss login 修复登录态。"),
			meta={"error_code": error_payload.get("code")},
		)

	data = payload.get("data") or {}
	auth_state = str(data.get("auth_state") or "unknown")
	auth_summary = str(data.get("auth_summary") or "unknown")
	checks = data.get("checks") if isinstance(data.get("checks"), list) else []
	check_status = {
		item.get("name"): item.get("status")
		for item in checks
		if isinstance(item, dict) and item.get("name")
	}

	if auth_state == "complete":
		return CheckResult(
			name=spec.name,
			status="pass",
			target=spec.target,
			purpose=spec.purpose,
			failure_classification=spec.failure_classification,
			critical=spec.critical,
			detail=f"Boss 登录态完整：auth_state={auth_state}, summary={auth_summary}",
			meta={
				"auth_state": auth_state,
				"auth_summary": auth_summary,
				"wt2_status": check_status.get("wt2_presence"),
				"stoken_status": check_status.get("stoken_presence"),
			},
		)

	status = "warn" if auth_state in {"partial", "degraded"} else "fail"
	return CheckResult(
		name=spec.name,
		status=status,
		target=spec.target,
		purpose=spec.purpose,
		failure_classification=spec.failure_classification,
		critical=spec.critical,
		detail=f"Boss 登录态未完全就绪：auth_state={auth_state}, summary={auth_summary}",
		recovery_action=str(
			(data.get("auth_health") or {}).get("recovery_action")
			or "运行 boss doctor 查看缺的 cookie / stoken，再按需要执行 boss login 或 CDP 登录。"
		),
		meta={
			"auth_state": auth_state,
			"auth_summary": auth_summary,
			"wt2_status": check_status.get("wt2_presence"),
			"stoken_status": check_status.get("stoken_presence"),
		},
	)


def evaluate_agent_check(spec: CheckSpec, payload: dict[str, Any]) -> CheckResult:
	configured = bool(payload.get("configured"))
	ready = bool(payload.get("ready"))
	browser_channel = payload.get("browserChannel") if isinstance(payload.get("browserChannel"), dict) else {}
	if configured and ready:
		return CheckResult(
			name=spec.name,
			status="pass",
			target=spec.target,
			purpose=spec.purpose,
			failure_classification=spec.failure_classification,
			critical=spec.critical,
			detail=f"Agent bridge 已就绪：endpoint={payload.get('endpoint')}",
			meta={
				"workflow": payload.get("workflow"),
				"authMode": payload.get("authMode"),
				"browserChannelMode": browser_channel.get("mode"),
				"browserChannelAvailable": browser_channel.get("available"),
			},
		)

	return CheckResult(
		name=spec.name,
		status="fail",
		target=spec.target,
		purpose=spec.purpose,
		failure_classification=spec.failure_classification,
		critical=spec.critical,
		detail=str(payload.get("errorMessage") or "Agent health 未就绪。"),
		recovery_action="确认 demo/interview-simulator 的 Vite server 已启动；若 .env 刚改过，重启 Vite 后再试。",
		meta={
			"configured": configured,
			"ready": ready,
			"browserChannelMode": browser_channel.get("mode"),
			"browserChannelAvailable": browser_channel.get("available"),
		},
	)


def evaluate_rag_check(spec: CheckSpec, payload: dict[str, Any]) -> CheckResult:
	status = str(payload.get("status") or "").lower()
	if status == "ok":
		return CheckResult(
			name=spec.name,
			status="pass",
			target=spec.target,
			purpose=spec.purpose,
			failure_classification=spec.failure_classification,
			critical=spec.critical,
			detail=f"RAG health 正常：{payload.get('app_name') or 'unknown app'}",
			meta={
				"environment": payload.get("environment"),
				"vector_store": (payload.get("vector_store") or {}).get("provider")
				if isinstance(payload.get("vector_store"), dict)
				else None,
				"llm_provider": (payload.get("llm") or {}).get("provider")
				if isinstance(payload.get("llm"), dict)
				else None,
			},
		)

	return CheckResult(
		name=spec.name,
		status="fail",
		target=spec.target,
		purpose=spec.purpose,
		failure_classification=spec.failure_classification,
		critical=spec.critical,
		detail=f"RAG health 返回异常状态：{status or 'missing status'}",
		recovery_action="确认 Enterprise-grade_RAG API 已启动，并检查 /api/v1/health 与鉴权配置。",
		meta={"raw_status": payload.get("status")},
	)


class ReadinessRunner:
	def __init__(
		self,
		config: ReadinessConfig,
		*,
		http_get_json=None,
		run_boss_status=None,
	):
		self.config = config
		self.checks = build_default_checks(config)
		self._http_get_json = http_get_json or _http_get_json
		self._run_boss_status = run_boss_status or _run_boss_status

	def run_once(self) -> dict[str, Any]:
		results: list[CheckResult] = []
		for spec in self.checks:
			if spec.name == "cdp":
				results.append(self._run_cdp(spec))
			elif spec.name == "boss_auth":
				results.append(self._run_boss_auth(spec))
			elif spec.name == "agent":
				results.append(self._run_agent(spec))
			elif spec.name == "rag":
				results.append(self._run_rag(spec))
			else:
				results.append(
					CheckResult(
						name=spec.name,
						status="fail",
						target=spec.target,
						purpose=spec.purpose,
						failure_classification=spec.failure_classification,
						critical=spec.critical,
						detail="未知检查项。",
					),
				)
		all_ready = all(item.status == "pass" for item in results if item.critical)
		return {
			"checked_at": datetime.now(timezone.utc).isoformat(),
			"all_ready": all_ready,
			"checks": [item.as_dict() for item in results],
		}

	def _run_cdp(self, spec: CheckSpec) -> CheckResult:
		try:
			_, payload = self._http_get_json(
				spec.target,
				headers={"Accept": "application/json"},
				timeout_seconds=self.config.timeout_seconds,
			)
			return evaluate_cdp_check(spec, payload)
		except Exception as exc:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail=f"无法访问 CDP：{exc}",
				recovery_action="启动 Chrome 并带上 --remote-debugging-port=9229，或改脚本参数指向正确的 CDP 地址。",
			)

	def _run_boss_auth(self, spec: CheckSpec) -> CheckResult:
		try:
			_, payload, _ = self._run_boss_status(
				ROOT,
				data_dir=self.config.data_dir,
				live=self.config.status_live,
				timeout_seconds=self.config.timeout_seconds * 5,
			)
			return evaluate_boss_auth_check(spec, payload)
		except subprocess.TimeoutExpired:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail="boss status 超时。",
				recovery_action="先运行 boss doctor 看本地登录态与依赖，再重试。",
			)
		except Exception as exc:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail=f"无法执行 boss status：{exc}",
				recovery_action="确认当前 Python 环境可导入 boss_agent_cli，或改用 uv run python 执行脚本。",
			)

	def _run_agent(self, spec: CheckSpec) -> CheckResult:
		try:
			_, payload = self._http_get_json(
				spec.target,
				headers={"Accept": "application/json"},
				timeout_seconds=self.config.timeout_seconds,
			)
			return evaluate_agent_check(spec, payload)
		except Exception as exc:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail=f"无法访问 Agent health：{exc}",
				recovery_action="先启动 demo/interview-simulator，再重试该脚本。",
			)

	def _run_rag(self, spec: CheckSpec) -> CheckResult:
		if not self.config.rag_base_url:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail="未配置 BOSS_RAG_RAG_BASE_URL。",
				recovery_action="在仓库 .env 里配置 BOSS_RAG_RAG_BASE_URL 后再跑。",
			)
		try:
			_, payload = self._http_get_json(
				spec.target,
				headers=_build_headers(self.config.rag_auth_mode, self.config.rag_api_key),
				timeout_seconds=self.config.timeout_seconds,
			)
			return evaluate_rag_check(spec, payload)
		except Exception as exc:
			return CheckResult(
				name=spec.name,
				status="fail",
				target=spec.target,
				purpose=spec.purpose,
				failure_classification=spec.failure_classification,
				critical=spec.critical,
				detail=f"无法访问 RAG health：{exc}",
				recovery_action="确认 Enterprise-grade_RAG 服务已启动，并检查 base URL、端口与鉴权配置。",
			)


def _parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="检查 CDP、Boss 登录态、demo Agent bridge、Enterprise RAG 是否接通。",
	)
	parser.add_argument("--cdp-url", default=None, help="默认读取 .env / BOSS_RAG_CDP_URL / BOSS_CDP_URL")
	parser.add_argument("--agent-base-url", default=None, help="默认 http://127.0.0.1:5175")
	parser.add_argument("--rag-base-url", default=None, help="默认读取 .env 的 BOSS_RAG_RAG_BASE_URL")
	parser.add_argument("--data-dir", default=None, help="默认读取 .env 的 BOSS_RAG_DATA_DIR 或 ~/.boss-agent")
	parser.add_argument("--status-live", dest="status_live", action="store_true", default=None, help="执行 boss status --live 做只读在线验证（默认开启）")
	parser.add_argument("--status-local-only", dest="status_live", action="store_false", help="只检查本地 session 文件，不做在线只读验证")
	parser.add_argument("--timeout-seconds", type=float, default=8.0)
	parser.add_argument("--wait-seconds", type=float, default=0.0, help="大于 0 时轮询直到全绿或超时")
	parser.add_argument("--interval-seconds", type=float, default=2.0)
	parser.add_argument("--pretty", action="store_true", help="输出格式化 JSON")
	return parser.parse_args()


def _resolve_config(args: argparse.Namespace) -> ReadinessConfig:
	config = load_config_from_repo(ROOT)
	return ReadinessConfig(
		cdp_url=(args.cdp_url or config.cdp_url).rstrip("/"),
		agent_base_url=(args.agent_base_url or config.agent_base_url).rstrip("/"),
		rag_base_url=(args.rag_base_url or config.rag_base_url).rstrip("/"),
		rag_auth_mode=config.rag_auth_mode,
		rag_api_key=config.rag_api_key,
		data_dir=args.data_dir or config.data_dir,
		status_live=config.status_live if args.status_live is None else args.status_live,
		timeout_seconds=args.timeout_seconds,
		wait_seconds=args.wait_seconds,
		interval_seconds=args.interval_seconds,
	)


def run_until_complete(config: ReadinessConfig) -> dict[str, Any]:
	runner = ReadinessRunner(config)
	started = time.time()
	attempts = 0
	last_report: dict[str, Any] | None = None

	while True:
		attempts += 1
		last_report = runner.run_once()
		last_report["attempts"] = attempts
		last_report["config"] = {
			"cdp_url": config.cdp_url,
			"agent_base_url": config.agent_base_url,
			"rag_base_url": config.rag_base_url,
			"status_live": config.status_live,
		}
		if last_report["all_ready"]:
			return last_report
		if config.wait_seconds <= 0:
			return last_report
		if time.time() - started >= config.wait_seconds:
			last_report["timed_out"] = True
			return last_report
		time.sleep(config.interval_seconds)


DEFAULT_CHECKS = build_default_checks(load_config_from_repo(ROOT))


def main() -> None:
	args = _parse_args()
	report = run_until_complete(_resolve_config(args))
	print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
	raise SystemExit(0 if report.get("all_ready") else 1)


if __name__ == "__main__":
	main()
