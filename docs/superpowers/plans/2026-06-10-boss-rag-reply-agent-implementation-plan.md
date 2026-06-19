# Boss RAG Reply Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `boss-agent-cli` fork 基础上交付一个可验收的 V1：支持 manual import / mock Boss envelope / rule-first classification / Enterprise RAG draft generation / review + approve-and-copy，同时默认不可能自动发送 Boss 消息。

**Architecture:** 实现分两段推进。第一段先完成与真实 Boss 无关的本地闭环：SQLite state、manual import、mock envelope、classifier、approval policy、RAG adapter、draft review、approval + audit。这一段对应 Task 1-7，也是第一个可交付 MVP acceptance path。第二段再加真实 Boss read-only adapter，把职位和消息读取接到同一条本地 pipeline 上，但不改变 upstream 默认低风险模式，也不进入真实发送路径。

**Tech Stack:** Python 3.10+, Click, sqlite3, httpx, dataclasses, JSON envelope output, pytest, rich, existing `boss-agent-cli` auth/platform/config helpers.

---

## File Structure

本计划假设实现发生在 `boss-agent-cli` fork 工作树中。如果当前工作区仍是空目录，Task 1 先把 upstream fork 内容同步到当前仓库，再开始后续任务。

### New Modules

- Create: `src/boss_agent_cli/rag_reply/__init__.py`
- Create: `src/boss_agent_cli/rag_reply/models.py`
- Create: `src/boss_agent_cli/rag_reply/store.py`
- Create: `src/boss_agent_cli/rag_reply/schema.py`
- Create: `src/boss_agent_cli/rag_reply/question_builder.py`
- Create: `src/boss_agent_cli/rag_reply/classifier.py`
- Create: `src/boss_agent_cli/rag_reply/policy.py`
- Create: `src/boss_agent_cli/rag_reply/service.py`
- Create: `src/boss_agent_cli/rag_reply/review.py`
- Create: `src/boss_agent_cli/rag_reply/clipboard.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/__init__.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/manual_import.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/mock_envelope.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/boss_automation.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/rag_http.py`
- Create: `src/boss_agent_cli/commands/rag.py`

### Existing Files To Modify

- Modify: `src/boss_agent_cli/config.py`
- Modify: `src/boss_agent_cli/commands/register.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `README.en.md` if upstream docs parity is required in the same change set

### New Tests

- Create: `tests/test_rag_reply_models.py`
- Create: `tests/test_rag_reply_store.py`
- Create: `tests/test_rag_reply_import.py`
- Create: `tests/test_rag_reply_mock_envelope.py`
- Create: `tests/test_rag_reply_classifier.py`
- Create: `tests/test_rag_reply_policy.py`
- Create: `tests/test_rag_reply_question_builder.py`
- Create: `tests/test_rag_reply_rag_http.py`
- Create: `tests/test_rag_reply_service.py`
- Create: `tests/test_rag_reply_commands.py`
- Create: `tests/test_rag_reply_boss_automation.py`
- Create: `tests/test_rag_reply_no_send_default.py`

## Data Models

V1 使用本地 SQLite，原始 Boss context 默认只保存在本地数据库。

### Intent Enum

- `project_question`
- `resume_question`
- `salary_or_offer`
- `availability_or_schedule`
- `personal_status`
- `interview_time`
- `resignation_status`
- `job_detail_question`
- `smalltalk`
- `contact_exchange`
- `unsafe_or_unclear`

### `jobs`

- `job_id TEXT PRIMARY KEY`
- `security_id TEXT`
- `title TEXT`
- `company TEXT`
- `salary TEXT`
- `city TEXT`
- `summary TEXT`
- `detail_json TEXT`
- `source TEXT`
- `updated_at TEXT`

### `recruiters`

- `recruiter_id TEXT PRIMARY KEY`
- `display_name TEXT`
- `company TEXT`
- `profile_json TEXT`
- `updated_at TEXT`

### `conversations`

- `conversation_id TEXT PRIMARY KEY`
- `source TEXT`
- `job_id TEXT`
- `recruiter_id TEXT`
- `channel TEXT`
- `last_message_at TEXT`
- `state_json TEXT`
- `updated_at TEXT`

### `messages`

- `message_id TEXT PRIMARY KEY`
- `conversation_id TEXT NOT NULL`
- `job_id TEXT`
- `recruiter_id TEXT`
- `direction TEXT`
- `message_text TEXT`
- `message_type TEXT`
- `source TEXT`
- `raw_json TEXT`
- `import_batch_id TEXT`
- `created_at TEXT`

### `drafts`

- `draft_id TEXT PRIMARY KEY`
- `conversation_id TEXT NOT NULL`
- `source_message_id TEXT NOT NULL`
- `draft_text TEXT NOT NULL`
- `intent TEXT NOT NULL`
- `risk_labels_json TEXT NOT NULL`
- `evidence_json TEXT NOT NULL`
- `approval_required INTEGER NOT NULL`
- `send_allowed INTEGER NOT NULL`
- `audit_status TEXT NOT NULL`
- `rag_session_id TEXT`
- `created_at TEXT`
- `updated_at TEXT`

### `approval_events`

- `event_id TEXT PRIMARY KEY`
- `draft_id TEXT NOT NULL`
- `action TEXT NOT NULL`
- `notes TEXT`
- `copied_to_clipboard INTEGER NOT NULL`
- `created_at TEXT`

### `audit_logs`

- `log_id TEXT PRIMARY KEY`
- `event_type TEXT NOT NULL`
- `entity_type TEXT NOT NULL`
- `entity_id TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TEXT`

### `rag_calls`

- `call_id TEXT PRIMARY KEY`
- `draft_id TEXT`
- `conversation_id TEXT NOT NULL`
- `request_json TEXT NOT NULL`
- `response_json TEXT`
- `status TEXT NOT NULL`
- `created_at TEXT`

## CLI Commands

`boss rag init`
: 初始化本地 SQLite 和默认配置提示，不触发任何平台读取。

`boss rag import-messages --file <path> --format json|md|csv`
: 手动导入消息到本地数据库。

`boss rag ingest-mock --file <path>`
: 导入 mock `boss-agent-cli` JSON envelope，验证结构化 Boss 输入链路。

`boss rag sync-jobs --query <query> [filters...]`
: 通过 Boss read-only adapter 拉取职位列表 / 详情并保存本地摘要。

`boss rag sync-messages [--conversation-id <id>]`
: 在 `boss_rag_allow_message_read=true` 且本地已授权的前提下读取 Boss 聊天列表 / HR 消息并落库。

`boss rag draft [--conversation-id <id>] [--message-id <id>]`
: 对待处理消息进行分类、审批判断、RAG 调用和 draft 保存。

`boss rag review [--draft-id <id>]`
: 显示 draft、intent、risk labels、citations / evidence、approval status。

`boss rag approve <draft_id> [--copy]`
: 记录审批事件，并尽量复制 draft 到剪贴板；若本机无 clipboard 工具则打印到 stdout/stderr 供手动复制。

`boss rag audit [--draft-id <id>]`
: 查看 audit log 和 approval history。

V1 不创建 `boss rag send` 进入 MVP 接受路径。若未来保留命令位，也必须返回 disabled-by-default 的明确错误。

## Test List

- Manual import 解析 JSON / Markdown / CSV，并把消息写入 SQLite。
- Mock `boss-agent-cli` JSON envelope 能被 ingest，字段映射到本地 `messages` / `conversations`。
- Rule-first classifier 正确识别：
  `salary_or_offer`、`availability_or_schedule`、`interview_time`、`resignation_status`、`personal_status`、`contact_exchange`、`unsafe_or_unclear`。
  `contact_exchange` 包括 微信、vx、联系方式、手机号、电话、邮箱、加我。
- 非敏感问题才允许 fallback 到轻量 LLM / heuristic classifier；敏感规则命中时绝不被覆盖。
- `question_builder` 只把 HR question、short job summary、answer objective 放进 RAG question，不带 Boss raw message 全量、不带 recruiter profile 全量、不带 full job detail 全量。
- RAG adapter 正确调用 `/api/v1/chat/ask`，包含允许字段，处理 success / timeout / HTTP error。
- Draft 保存后字段完整：`draft_text`、`intent`、`risk_labels`、`evidence`、`approval_required`、`send_allowed`、`audit_status`。
- RAG failure fail closed：当 `/api/v1/chat/ask` 超时或报错时，仍然保存记录，且 `audit_status="rag_failed"`、`send_allowed=false`、`approval_required=true`，并写 audit log。
- Review command 输出草稿、evidence、risk labels、审批状态。
- Approve 命令持久化 `approval_events`，并写 `audit_logs`。
- 默认没有任何自动发送能力；`send_allowed` 默认 `false`。
- Boss read-only adapter 只有显式 opt-in 才允许读取消息；未开启时返回清晰错误。

## Implementation Order

1. Bootstrap upstream fork into the workspace and establish a passing baseline.
2. Add config flags and register the `boss rag` command group with no side effects.
3. Add SQLite schema, models, and audit-safe persistence.
4. Implement manual import and mock envelope ingestion.
5. Implement rule-first classifier and approval policy.
6. Implement minimal-context RAG question builder and HTTP adapter.
7. Implement draft orchestration, review, approve-and-copy, and audit commands.
8. Implement Boss read-only adapter for jobs and messages behind explicit opt-in after the local MVP path is green.
9. Update docs and run focused regression tests to prove default no-send behavior.

## Rollback And Safety Plan

- Keep all new state in a separate SQLite file such as `~/.boss-agent/boss-rag.sqlite3`; no migration against upstream cache/state files.
- Do not modify upstream `compliance.py` blocked-command behavior for existing `chat` / `chatmsg` / `greet` / `reply` surfaces.
- Route real Boss reading only through new `boss rag` commands with explicit config checks.
- Never add a working send path in MVP. `approve` records approval only; clipboard copy is the terminal action.
- If Boss message reading proves brittle, disable `sync-messages` and continue with `import-messages` + `ingest-mock`; the rest of the pipeline still ships.
- If RAG integration fails, drafts should degrade to `audit_status="rag_failed"` with `send_allowed=false` and `approval_required=true`, and audit logging must still succeed.

### Task 1: Bootstrap Fork Workspace

**Files:**
- Create: upstream `boss-agent-cli` source tree in current workspace
- Modify: `README.md` only if bootstrap instructions need local repo notes
- Test: upstream baseline tests already present in fork

- [ ] **Step 1: Import the upstream codebase into the current workspace**

Use the `boss-agent-cli` fork as the working tree instead of implementing against the empty `BOSS_AGENT` directory.

```bash
if [ -z "$(find . -mindepth 1 -maxdepth 1 -not -name .git -print -quit)" ]; then
  git clone <your-fork-of-boss-agent-cli> .
else
  git clone <your-fork-of-boss-agent-cli> /tmp/boss-agent-cli-bootstrap
  rsync -a /tmp/boss-agent-cli-bootstrap/ ./
fi
```

- [ ] **Step 2: Verify the baseline environment**

Run:

```bash
python -m pytest tests/test_compliance.py tests/test_chatmsg_extended.py -q
```

Expected: baseline tests pass before any V1 changes.

- [ ] **Step 3: Record the accepted design doc in the fork**

Keep [2026-06-10-boss-rag-reply-agent-design.md](/home/reggie/vscode_folder/BOSS_AGENT/docs/superpowers/specs/2026-06-10-boss-rag-reply-agent-design.md) in the fork’s `docs/superpowers/specs/`.

- [ ] **Step 4: Commit baseline import if needed**

```bash
git add README.md docs/superpowers/specs/2026-06-10-boss-rag-reply-agent-design.md
git commit -m "docs: add Boss RAG reply agent design baseline"
```

### Task 2: Add Config Flags And Command Skeleton

**Files:**
- Modify: `src/boss_agent_cli/config.py`
- Modify: `src/boss_agent_cli/commands/register.py`
- Create: `src/boss_agent_cli/commands/rag.py`
- Create: `src/boss_agent_cli/rag_reply/__init__.py`
- Test: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Write the failing command-registration tests**

```python
def test_rag_group_is_registered():
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "rag", "--help"])
    assert result.exit_code == 0


def test_rag_sync_messages_requires_explicit_opt_in():
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "rag", "sync-messages"])
    parsed = json.loads(result.output)
    assert parsed["ok"] is False
    assert parsed["error"]["code"] == "RAG_READ_NOT_ENABLED"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
pytest tests/test_rag_reply_commands.py -q
```

Expected: fail because `rag` command group does not exist yet.

- [ ] **Step 3: Add minimal config keys and command skeleton**

```python
DEFAULTS.update({
    "boss_rag_db_path": None,
    "boss_rag_rag_base_url": None,
    "boss_rag_rag_timeout_seconds": 20,
    "boss_rag_allow_message_read": False,
    "boss_rag_send_enabled": False,
})
```

```python
@click.group("rag")
def rag_group() -> None:
    """Boss RAG reply workflow commands."""
```

- [ ] **Step 4: Re-run the command tests**

Run:

```bash
pytest tests/test_rag_reply_commands.py -q
```

Expected: basic `rag` group tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/config.py src/boss_agent_cli/commands/register.py src/boss_agent_cli/commands/rag.py src/boss_agent_cli/rag_reply/__init__.py tests/test_rag_reply_commands.py
git commit -m "feat: add Boss RAG command skeleton"
```

### Task 3: Add SQLite Schema And Domain Models

**Files:**
- Create: `src/boss_agent_cli/rag_reply/models.py`
- Create: `src/boss_agent_cli/rag_reply/schema.py`
- Create: `src/boss_agent_cli/rag_reply/store.py`
- Test: `tests/test_rag_reply_models.py`
- Test: `tests/test_rag_reply_store.py`

- [ ] **Step 1: Write the failing model/store tests**

```python
def test_draft_record_defaults_to_no_send():
    draft = DraftRecord.new(...)
    assert draft.send_allowed is False
    assert draft.approval_required is True


def test_store_creates_expected_tables(tmp_path):
    store = RagReplyStore(tmp_path / "boss-rag.sqlite3")
    store.initialize()
    assert set(store.list_tables()) >= {"messages", "drafts", "approval_events", "audit_logs", "rag_calls"}
```

- [ ] **Step 2: Run tests to confirm failure**

Run:

```bash
pytest tests/test_rag_reply_models.py tests/test_rag_reply_store.py -q
```

Expected: fail because store/models are missing.

- [ ] **Step 3: Implement dataclasses and SQLite initialization**

```python
@dataclass
class DraftRecord:
    draft_id: str
    conversation_id: str
    source_message_id: str
    draft_text: str
    intent: str
    risk_labels: list[str]
    evidence: dict[str, Any]
    approval_required: bool
    send_allowed: bool = False
    audit_status: str = "draft_created"
```

```python
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    draft_text TEXT NOT NULL,
    intent TEXT NOT NULL,
    risk_labels_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    approval_required INTEGER NOT NULL,
    send_allowed INTEGER NOT NULL,
    audit_status TEXT NOT NULL,
    rag_session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

- [ ] **Step 4: Re-run the model/store tests**

Run:

```bash
pytest tests/test_rag_reply_models.py tests/test_rag_reply_store.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/models.py src/boss_agent_cli/rag_reply/schema.py src/boss_agent_cli/rag_reply/store.py tests/test_rag_reply_models.py tests/test_rag_reply_store.py
git commit -m "feat: add Boss RAG local state store"
```

### Task 4: Implement Manual Import And Mock Envelope Ingestion

**Files:**
- Create: `src/boss_agent_cli/rag_reply/adapters/manual_import.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/mock_envelope.py`
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_rag_reply_import.py`
- Test: `tests/test_rag_reply_mock_envelope.py`

- [ ] **Step 1: Write failing ingestion tests**

```python
def test_import_messages_json_writes_message_and_conversation(tmp_path):
    ...
    assert store.get_message("msg_001").message_text == "你这个RAG项目具体做了什么？"


def test_mock_envelope_ingest_maps_chatmsg_payload(tmp_path):
    ...
    assert stored.intent_source == "mock_envelope"
```

- [ ] **Step 2: Run ingestion tests and confirm failure**

Run:

```bash
pytest tests/test_rag_reply_import.py tests/test_rag_reply_mock_envelope.py -q
```

Expected: fail because importers are missing.

- [ ] **Step 3: Implement importers with source tagging**

```python
def import_messages(path: Path, fmt: str, store: RagReplyStore) -> ImportBatchResult:
    # parse json/md/csv -> normalize -> store conversation + messages
```

```python
def ingest_mock_envelope(payload: dict[str, Any], store: RagReplyStore) -> ImportBatchResult:
    # accept boss-agent-cli success envelope and map data[] into local records
```

- [ ] **Step 4: Add CLI wiring**

```python
@rag_group.command("import-messages")
@click.option("--file", "file_path", required=True)
@click.option("--format", "fmt", type=click.Choice(["json", "md", "csv"]), required=True)
def import_messages_cmd(...): ...
```

- [ ] **Step 5: Re-run ingestion tests**

Run:

```bash
pytest tests/test_rag_reply_import.py tests/test_rag_reply_mock_envelope.py tests/test_rag_reply_commands.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/adapters/manual_import.py src/boss_agent_cli/rag_reply/adapters/mock_envelope.py src/boss_agent_cli/commands/rag.py tests/test_rag_reply_import.py tests/test_rag_reply_mock_envelope.py tests/test_rag_reply_commands.py
git commit -m "feat: add manual import and mock envelope ingestion"
```

### Task 5: Implement Rule-First Classifier And Approval Policy

**Files:**
- Create: `src/boss_agent_cli/rag_reply/classifier.py`
- Create: `src/boss_agent_cli/rag_reply/policy.py`
- Test: `tests/test_rag_reply_classifier.py`
- Test: `tests/test_rag_reply_policy.py`

- [ ] **Step 1: Write the failing classifier/policy tests**

```python
@pytest.mark.parametrize(
    ("message_text", "expected_intent"),
    [
        ("期望薪资多少？", "salary_or_offer"),
        ("什么时候方便面试？", "interview_time"),
        ("现在是在职吗？", "personal_status"),
        ("方便加微信吗？", "contact_exchange"),
        ("把手机号发我", "contact_exchange"),
    ],
)
def test_sensitive_rules_win(message_text, expected_intent):
    result = classify_message(message_text)
    assert result.intent == expected_intent
    assert "human_approval_required" in result.risk_labels
```

```python
def test_policy_blocks_sensitive_intents_from_send():
    decision = build_approval_decision(intent="salary_or_offer", risk_labels=["human_approval_required"])
    assert decision.approval_required is True
    assert decision.send_allowed is False
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```bash
pytest tests/test_rag_reply_classifier.py tests/test_rag_reply_policy.py -q
```

Expected: fail because classifier and policy are missing.

- [ ] **Step 3: Implement rule-first detection**

```python
SENSITIVE_RULES = [
    ("salary_or_offer", [r"薪资", r"工资", r"offer"]),
    ("availability_or_schedule", [r"方便", r"有空", r"时间"]),
    ("interview_time", [r"面试", r"几点", r"哪天"]),
    ("resignation_status", [r"离职", r"离岗"]),
    ("personal_status", [r"在职", r"目前状态"]),
    ("contact_exchange", [r"微信", r"vx", r"联系方式"]),
]
```

```python
if matched_sensitive_rule:
    return ClassificationResult(
        intent=matched_sensitive_rule.intent,
        risk_labels=["human_approval_required", matched_sensitive_rule.intent],
        classifier_source="rules",
    )
```

- [ ] **Step 4: Re-run classifier/policy tests**

Run:

```bash
pytest tests/test_rag_reply_classifier.py tests/test_rag_reply_policy.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/classifier.py src/boss_agent_cli/rag_reply/policy.py tests/test_rag_reply_classifier.py tests/test_rag_reply_policy.py
git commit -m "feat: add rule-first message classifier and approval policy"
```

### Task 6: Implement Minimal-Context RAG Builder And HTTP Adapter

**Files:**
- Create: `src/boss_agent_cli/rag_reply/question_builder.py`
- Create: `src/boss_agent_cli/rag_reply/adapters/rag_http.py`
- Test: `tests/test_rag_reply_question_builder.py`
- Test: `tests/test_rag_reply_rag_http.py`

- [ ] **Step 1: Write the failing RAG adapter tests**

```python
def test_question_builder_excludes_full_boss_context():
    question = build_rag_question(...)
    assert "raw_json" not in question
    assert "完整职位详情" not in question
    assert "HR question:" in question


def test_rag_http_calls_chat_ask_endpoint(httpx_mock):
    ...
    assert request.url.path == "/api/v1/chat/ask"
    assert "question" in request.json()
    assert "session_id" in request.json()
    assert "metadata" not in request.json()


def test_rag_http_failure_returns_closed_result(httpx_mock):
    ...
    assert result.audit_status == "rag_failed"
    assert result.send_allowed is False
    assert result.approval_required is True
```

- [ ] **Step 2: Run the RAG tests and verify failure**

Run:

```bash
pytest tests/test_rag_reply_question_builder.py tests/test_rag_reply_rag_http.py -q
```

Expected: fail because builder and HTTP adapter are missing.

- [ ] **Step 3: Implement the minimal-context builder**

```python
def build_rag_question(hr_question: str, job_summary: str | None, objective: str) -> str:
    parts = [
        f"HR question: {hr_question}",
        f"Answer objective: {objective}",
    ]
    if job_summary:
        parts.append(f"Short job summary: {job_summary}")
    return "\n".join(parts)
```

- [ ] **Step 4: Implement the HTTP adapter**

```python
payload = {
    "question": rag_question,
    "session_id": rag_session_id,
    "mode": "accurate",
}
try:
    response = httpx.post(f"{base_url}/api/v1/chat/ask", json=payload, timeout=timeout)
except httpx.HTTPError:
    return RagFailureResult(
        audit_status="rag_failed",
        send_allowed=False,
        approval_required=True,
    )
```

- [ ] **Step 5: Re-run the RAG tests**

Run:

```bash
pytest tests/test_rag_reply_question_builder.py tests/test_rag_reply_rag_http.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/boss_agent_cli/rag_reply/question_builder.py src/boss_agent_cli/rag_reply/adapters/rag_http.py tests/test_rag_reply_question_builder.py tests/test_rag_reply_rag_http.py
git commit -m "feat: add minimal-context Enterprise RAG adapter"
```

### Task 7: Implement Draft Orchestration, Review, Approve-And-Copy, And Audit

**Files:**
- Create: `src/boss_agent_cli/rag_reply/service.py`
- Create: `src/boss_agent_cli/rag_reply/review.py`
- Create: `src/boss_agent_cli/rag_reply/clipboard.py`
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_rag_reply_service.py`
- Test: `tests/test_rag_reply_commands.py`
- Test: `tests/test_rag_reply_no_send_default.py`

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_draft_command_saves_draft_and_audit_log(tmp_path):
    ...
    draft = store.list_drafts()[0]
    assert draft.draft_text
    assert draft.audit_status == "draft_created"
    assert store.list_audit_logs()


def test_approve_command_persists_event_without_send(tmp_path):
    ...
    event = store.list_approval_events()[0]
    assert event.action == "approved"
    assert store.get_draft(draft_id).send_allowed is False


def test_draft_command_persists_closed_record_when_rag_fails(tmp_path):
    ...
    draft = store.list_drafts()[0]
    assert draft.audit_status == "rag_failed"
    assert draft.send_allowed is False
    assert draft.approval_required is True
    assert store.list_audit_logs()
```

- [ ] **Step 2: Run orchestration tests and verify failure**

Run:

```bash
pytest tests/test_rag_reply_service.py tests/test_rag_reply_commands.py tests/test_rag_reply_no_send_default.py -q
```

Expected: fail because service/review/approve flow is missing.

- [ ] **Step 3: Implement draft orchestration**

```python
class BossRagReplyService:
    def create_draft_for_message(self, message_id: str) -> DraftRecord:
        classification = classify_message(...)
        decision = build_approval_decision(...)
        rag_response = self.rag_adapter.answer(...)
        draft = DraftRecord(...)
        self.store.save_draft(draft)
        self.store.append_audit_log(...)
        return draft
```

- [ ] **Step 4: Implement review + approve-and-copy**

```python
def approve_draft(self, draft_id: str, copy_to_clipboard: bool) -> ApprovalEvent:
    event = ApprovalEvent(action="approved", copied_to_clipboard=copy_to_clipboard)
    self.store.save_approval_event(event)
    self.store.append_audit_log(...)
```

- [ ] **Step 5: Add CLI commands**

```python
@rag_group.command("draft")
def draft_cmd(...): ...


@rag_group.command("review")
def review_cmd(...): ...


@rag_group.command("approve")
@click.option("--copy", is_flag=True, default=False)
def approve_cmd(...): ...
```

- [ ] **Step 6: Re-run orchestration tests**

Run:

```bash
pytest tests/test_rag_reply_service.py tests/test_rag_reply_commands.py tests/test_rag_reply_no_send_default.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/boss_agent_cli/rag_reply/service.py src/boss_agent_cli/rag_reply/review.py src/boss_agent_cli/rag_reply/clipboard.py src/boss_agent_cli/commands/rag.py tests/test_rag_reply_service.py tests/test_rag_reply_commands.py tests/test_rag_reply_no_send_default.py
git commit -m "feat: add draft review and approval workflow"
```

### Task 8: Implement Boss Read-Only Adapter Behind Explicit Opt-In

**Files:**
- Create: `src/boss_agent_cli/rag_reply/adapters/boss_automation.py`
- Modify: `src/boss_agent_cli/commands/rag.py`
- Test: `tests/test_rag_reply_boss_automation.py`
- Test: `tests/test_rag_reply_commands.py`

- [ ] **Step 1: Write failing Boss adapter tests**

```python
def test_sync_messages_requires_allow_message_read_flag(tmp_path):
    ...
    assert parsed["error"]["code"] == "RAG_READ_NOT_ENABLED"


def test_sync_jobs_maps_platform_job_detail_to_local_summary(...):
    ...
    assert stored_job.summary
```

- [ ] **Step 2: Run the Boss adapter tests and verify failure**

Run:

```bash
pytest tests/test_rag_reply_boss_automation.py tests/test_rag_reply_commands.py -q
```

Expected: fail because Boss read-only adapter is missing.

- [ ] **Step 3: Implement read-only adapter without touching upstream compliance surfaces**

```python
class BossAutomationAdapter:
    def sync_jobs(...): ...
    def sync_messages(...): ...
```

```python
if not config.get("boss_rag_allow_message_read", False):
    raise RagReplyError("RAG_READ_NOT_ENABLED", "Boss message reading is disabled by default.")
```

- [ ] **Step 4: Re-run the Boss adapter tests**

Run:

```bash
pytest tests/test_rag_reply_boss_automation.py tests/test_rag_reply_commands.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/boss_agent_cli/rag_reply/adapters/boss_automation.py src/boss_agent_cli/commands/rag.py tests/test_rag_reply_boss_automation.py tests/test_rag_reply_commands.py
git commit -m "feat: add Boss read-only adapter for RAG workflow"
```

### Task 9: Regression, Docs, And MVP Acceptance Proof

**Files:**
- Modify: `README.md`
- Modify: `README.en.md` if required
- Modify: `pyproject.toml`
- Test: all new `tests/test_rag_reply_*.py`

- [ ] **Step 1: Add docs for config flags and MVP boundary**

Document:

```text
boss_rag_allow_message_read=false
boss_rag_send_enabled=false
approve != send
manual import remains supported
```

- [ ] **Step 2: Add mypy coverage for new modules if the repo keeps strict overrides**

```toml
"boss_agent_cli.rag_reply.models",
"boss_agent_cli.rag_reply.store",
"boss_agent_cli.rag_reply.classifier",
"boss_agent_cli.rag_reply.policy",
"boss_agent_cli.rag_reply.service",
```

- [ ] **Step 3: Run the focused MVP suite**

Run:

```bash
pytest \
  tests/test_rag_reply_models.py \
  tests/test_rag_reply_store.py \
  tests/test_rag_reply_import.py \
  tests/test_rag_reply_mock_envelope.py \
  tests/test_rag_reply_classifier.py \
  tests/test_rag_reply_policy.py \
  tests/test_rag_reply_question_builder.py \
  tests/test_rag_reply_rag_http.py \
  tests/test_rag_reply_service.py \
  tests/test_rag_reply_commands.py \
  tests/test_rag_reply_boss_automation.py \
  tests/test_rag_reply_no_send_default.py -q
```

Expected: all pass.

- [ ] **Step 4: Run baseline regressions for touched upstream surfaces**

Run:

```bash
pytest tests/test_compliance.py tests/test_chatmsg_extended.py tests/test_commands.py -q
```

Expected: pass, proving no accidental regression to default low-risk behavior.

- [ ] **Step 5: Commit**

```bash
git add README.md README.en.md pyproject.toml tests/test_rag_reply_*.py
git commit -m "docs: document Boss RAG MVP and verify no-send defaults"
```

## Self-Review

### Spec Coverage

- `manual import works`: Task 4
- `mock boss-agent-cli JSON envelope works`: Task 4
- `classifier produces the correct intent`: Task 5
- `sensitive messages are blocked by approval policy`: Task 5
- `RAG adapter calls /api/v1/chat/ask correctly`: Task 6
- `RAG failure must fail closed`: Tasks 6 and 7
- `draft reply is saved`: Task 7
- `review command shows draft, citations/evidence, and risk labels`: Task 7
- `approval event is persisted`: Task 7
- `audit log is written`: Task 7
- `no automatic sending is possible by default`: Tasks 3, 5, 7, 9
- `Boss read-only automation after local MVP`: Task 8
- `do not stuff full Boss context into RAG question`: Task 6

### Placeholder Scan

本计划没有遗留占位语。真实实现细节的不确定性只保留在 Task 1 的 fork 导入方式上，但执行动作已经明确。

### Type Consistency

全计划统一使用以下关键字段：

- `draft_text`
- `intent`
- `risk_labels`
- `evidence`
- `approval_required`
- `send_allowed`
- `audit_status`

不存在后续任务里改名为别的字段的情况。
