import json
from pathlib import Path


def test_bridge_extension_manifest_references_existing_files():
	repo_root = Path(__file__).resolve().parents[1]
	extension_dir = repo_root / "extension"
	manifest = json.loads((extension_dir / "manifest.json").read_text())

	referenced_files = [
		manifest["background"]["service_worker"],
		manifest["action"]["default_popup"],
	]

	for relative_path in referenced_files:
		assert (extension_dir / relative_path).is_file()


def test_bridge_extension_requires_chrome_with_websocket_service_worker_keepalive():
	repo_root = Path(__file__).resolve().parents[1]
	manifest = json.loads((repo_root / "extension" / "manifest.json").read_text())

	assert int(manifest["minimum_chrome_version"]) >= 116


def test_bridge_extension_boss_workspace_fallback_is_debuggable_https_page():
	repo_root = Path(__file__).resolve().parents[1]
	background = (repo_root / "extension" / "background.js").read_text()

	assert "https://www.zhipin.com/" in background
	assert "data:text/html" not in background
	assert "startsWith('data:')" not in background


def test_bridge_extension_keeps_websocket_session_alive():
	repo_root = Path(__file__).resolve().parents[1]
	background = (repo_root / "extension" / "background.js").read_text()

	assert "KEEPALIVE_INTERVAL_MS" in background
	assert "startHeartbeat()" in background
	assert "stopHeartbeat()" in background
	assert '"ping"' in background or "'ping'" in background
	assert "\ninitialize();\n" in background
