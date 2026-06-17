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
