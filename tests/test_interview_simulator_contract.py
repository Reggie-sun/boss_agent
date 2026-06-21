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


def test_interview_simulator_exposes_profile_bridge_without_removing_existing_flows():
	repo_root = Path(__file__).resolve().parents[1]
	vite = (repo_root / "demo" / "interview-simulator" / "vite.config.mjs").read_text(encoding="utf-8")
	profile_bridge = (
		repo_root / "demo" / "interview-simulator" / "server" / "profileBridge.mjs"
	).read_text(encoding="utf-8")
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")
	reply = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "ReplyWorkspace.jsx").read_text(encoding="utf-8")
	outreach = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "OutreachWorkspace.jsx").read_text(encoding="utf-8")

	for token in ("/api/agent/profiles", "/api/agent/profile-binding", "/api/agent/usage"):
		assert token in profile_bridge
	for existing in (
		"/api/agent/ask",
		"/api/agent/send",
		"/api/boss/auto-greet",
		"Boss 自动开聊",
		"Agent 全自动",
	):
		assert existing in vite or existing in app or existing in reply or existing in outreach


def test_interview_simulator_profile_refactor_wires_local_profile_workflows():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")
	client = (repo_root / "demo" / "interview-simulator" / "src" / "api" / "agentClient.js").read_text(encoding="utf-8")
	profile_hub = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "ProfileHub.jsx").read_text(encoding="utf-8")
	reply = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "ReplyWorkspace.jsx").read_text(encoding="utf-8")
	outreach = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "OutreachWorkspace.jsx").read_text(encoding="utf-8")
	selector = (repo_root / "demo" / "interview-simulator" / "src" / "components" / "profile" / "ProfileSelector.jsx").read_text(encoding="utf-8")
	panel = (repo_root / "demo" / "interview-simulator" / "src" / "components" / "profile" / "ProfileConfigPanel.jsx").read_text(encoding="utf-8")
	combined = "\n".join([app, client, profile_hub, reply, outreach, selector, panel])

	for token in (
		"ProfileHub",
		"ReplyWorkspace",
		"OutreachWorkspace",
		"selectedProfileId",
		"commercial_profile_required: true",
		"profile_id: selectedProfileId",
		"fetchProfileConfig",
		"updateProfileConfig",
		"bindConversationProfile",
	):
		assert token in combined
	for visible in ("发送到 Boss", "发送附件简历 PDF", "watcher", "Boss 自动开聊", "Agent 全自动"):
		assert visible in combined


def test_interview_simulator_profile_hub_hides_manual_kb_and_tracks_uploads():
	repo_root = Path(__file__).resolve().parents[1]
	client = (repo_root / "demo" / "interview-simulator" / "src" / "api" / "agentClient.js").read_text(encoding="utf-8")
	profile_hub = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "ProfileHub.jsx").read_text(encoding="utf-8")
	profile_bridge = (
		repo_root / "demo" / "interview-simulator" / "server" / "profileBridge.mjs"
	).read_text(encoding="utf-8")

	assert 'placeholder="knowledge_base_id"' not in profile_hub
	assert "knowledge_base_id: newProfile.knowledge_base_id" not in profile_hub
	assert 'appendTextOption(args, "--knowledge-base-id"' not in profile_bridge
	assert "fetchProfileUploads" in profile_hub
	assert "uploadProfileDocument" in client
	assert "uploadProfileDocument" in profile_hub
	assert "/uploads" in profile_bridge


def test_interview_simulator_boss_risk_copy_is_page_scoped_and_clearable():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")
	errors = (repo_root / "demo" / "interview-simulator" / "src" / "bossBridgeErrors.js").read_text(encoding="utf-8")
	outreach = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "OutreachWorkspace.jsx").read_text(encoding="utf-8")

	assert "Boss 账号触发风控" not in errors
	assert "Boss 账号当前已被平台限制访问" not in errors
	assert "当前 Boss 页面或自动化通道" in errors
	assert "handleClearBossAutomationRisk" in app
	assert "onClearBossAutomationRisk" in outreach
	assert "已处理，解除本地锁" in outreach


def test_interview_simulator_profile_binding_uses_cli_supported_source():
	repo_root = Path(__file__).resolve().parents[1]
	profile_hub = (repo_root / "demo" / "interview-simulator" / "src" / "views" / "ProfileHub.jsx").read_text(encoding="utf-8")
	profile_bridge = (
		repo_root / "demo" / "interview-simulator" / "server" / "profileBridge.mjs"
	).read_text(encoding="utf-8")

	assert 'binding_source: "frontend_profile_hub"' not in profile_hub
	assert 'binding_source: "manual"' in profile_hub
	assert "normalizeBindingSource" in profile_bridge
	assert '"manual"' in profile_bridge


def test_interview_simulator_agent_ask_uses_bound_boss_conversation_id():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")

	assert "const agentConversationId = useMemo" in app
	assert 'selectedChatTarget?.conversation_id || "").trim() || sessionId' in app
	assert "sessionId: agentConversationId" in app
	assert "encodeURIComponent(agentConversationId)" in app


def test_interview_simulator_target_refresh_preserves_current_selection():
	repo_root = Path(__file__).resolve().parents[1]
	app = (repo_root / "demo" / "interview-simulator" / "src" / "App.jsx").read_text(encoding="utf-8")

	assert "selectedTargetValueRef" in app
	assert "applySecurityIdRef" in app
	assert "!selectedTargetValueRef.current" in app
	assert "!applySecurityIdRef.current.trim()" in app
