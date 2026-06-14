import json

from click.testing import CliRunner

from boss_agent_cli.main import cli


def test_shortlist_add_list_remove(tmp_path):
	runner = CliRunner()
	result = runner.invoke(
		cli,
		[
			"--data-dir", str(tmp_path),
			"--json",
			"shortlist", "add", "sec_001", "job_001",
			"--title", "Go 开发",
			"--company", "TestCo",
			"--city", "广州",
			"--salary", "20-30K",
			"--source", "search",
		],
	)
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert parsed["ok"] is True
	assert parsed["data"]["security_id"] == "sec_001"

	list_result = runner.invoke(cli, ["--data-dir", str(tmp_path), "--json", "shortlist", "list"])
	assert list_result.exit_code == 0
	list_parsed = json.loads(list_result.output)
	assert len(list_parsed["data"]) == 1
	assert list_parsed["data"][0]["company"] == "TestCo"

	remove_result = runner.invoke(cli, ["--data-dir", str(tmp_path), "--json", "shortlist", "remove", "sec_001", "job_001"])
	assert remove_result.exit_code == 0
	remove_parsed = json.loads(remove_result.output)
	assert remove_parsed["data"]["removed"] is True


def test_shortlist_zhilian_hints_use_platform_specific_commands(tmp_path):
	runner = CliRunner()
	add_result = runner.invoke(
		cli,
		[
			"--data-dir", str(tmp_path),
			"--json",
			"--platform", "zhilian",
			"shortlist", "add", "sec_001", "job_001",
		],
	)
	assert add_result.exit_code == 0
	add_parsed = json.loads(add_result.output)
	assert add_parsed["hints"]["next_actions"][0] == "boss --platform zhilian shortlist list"
	assert add_parsed["hints"]["next_actions"][1] == "boss --platform zhilian shortlist remove sec_001 job_001"

	list_result = runner.invoke(cli, ["--data-dir", str(tmp_path), "--json", "--platform", "zhilian", "shortlist", "list"])
	assert list_result.exit_code == 0
	list_parsed = json.loads(list_result.output)
	assert list_parsed["hints"]["next_actions"][0] == "boss --platform zhilian detail <security_id> --job-id <job_id>"

	remove_result = runner.invoke(
		cli,
		["--data-dir", str(tmp_path), "--json", "--platform", "zhilian", "shortlist", "remove", "sec_001", "job_001"],
	)
	assert remove_result.exit_code == 0
	remove_parsed = json.loads(remove_result.output)
	assert remove_parsed["hints"]["next_actions"][0] == "boss --platform zhilian shortlist list"


def test_shortlist_prepare_with_resume_and_mark_applied(tmp_path):
	runner = CliRunner()
	resume_init = runner.invoke(
		cli,
		["--data-dir", str(tmp_path), "--json", "resume", "init", "--name", "backend", "--template", "default"],
	)
	assert resume_init.exit_code == 0
	add_result = runner.invoke(
		cli,
		[
			"--data-dir", str(tmp_path),
			"--json",
			"shortlist", "add", "sec_001", "job_001",
			"--title", "Go 开发",
			"--company", "TestCo",
			"--city", "广州",
			"--salary", "20-30K",
		],
	)
	assert add_result.exit_code == 0

	prepare_result = runner.invoke(
		cli,
		[
			"--data-dir", str(tmp_path),
			"--json",
			"shortlist", "prepare", "sec_001", "job_001",
			"--resume", "backend",
			"--tone", "积极主动",
			"--note", "可一周内到岗",
		],
	)
	assert prepare_result.exit_code == 0
	prepare_parsed = json.loads(prepare_result.output)
	assert prepare_parsed["ok"] is True
	assert prepare_parsed["data"]["status"] == "prepared"
	assert prepare_parsed["data"]["resume"]["name"] == "backend"
	assert "official_entry_url" in prepare_parsed["data"]["manual_entry"]
	assert "可一周内到岗" in prepare_parsed["data"]["draft_message"]
	assert prepare_parsed["hints"]["next_actions"][1] == "boss shortlist mark-applied sec_001 job_001 --resume backend"

	mark_result = runner.invoke(
		cli,
		[
			"--data-dir", str(tmp_path),
			"--json",
			"shortlist", "mark-applied", "sec_001", "job_001",
			"--resume", "backend",
			"--notes", "官网已手动提交",
		],
	)
	assert mark_result.exit_code == 0
	mark_parsed = json.loads(mark_result.output)
	assert mark_parsed["ok"] is True
	assert mark_parsed["data"]["status"] == "manually_applied"
	assert mark_parsed["data"]["updated_resumes"] == ["backend"]

	applications_result = runner.invoke(
		cli,
		["--data-dir", str(tmp_path), "--json", "resume", "applications", "backend"],
	)
	assert applications_result.exit_code == 0
	applications_parsed = json.loads(applications_result.output)
	assert applications_parsed["data"][0]["status"] == "manually_applied"
	assert applications_parsed["data"][0]["notes"] == "官网已手动提交"


def test_shortlist_prepare_missing_item_returns_schema_error(tmp_path):
	runner = CliRunner()
	result = runner.invoke(
		cli,
		["--data-dir", str(tmp_path), "--json", "shortlist", "prepare", "missing", "job_001"],
	)
	assert result.exit_code == 1
	parsed = json.loads(result.output)
	assert parsed["error"]["code"] == "SHORTLIST_NOT_FOUND"


def test_shortlist_schema_is_exposed():
	runner = CliRunner()
	result = runner.invoke(cli, ["schema"])
	assert result.exit_code == 0
	parsed = json.loads(result.output)
	assert "shortlist" in parsed["data"]["commands"]
	assert parsed["data"]["commands"]["shortlist"]["subcommands"]["prepare"]
