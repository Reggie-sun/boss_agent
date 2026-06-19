# Boss RAG Reply Agent V1 Design

## Goal

V1 构建一个 `Boss read-only automation + RAG draft reply + human approval send gate` 的本地 CLI / local service。系统复用 `boss-agent-cli` 作为 Boss 直聘只读自动化和结构化 CLI 基座，复用现有 Enterprise RAG 作为外部 HTTP 服务生成回答草稿，但不改动 RAG 核心检索、生成、citation pipeline。

V1 不是 full auto-apply，不是 batch auto-greeting，也不是 fully autonomous HR chat bot。

## Selected Base

主基座选择 fork / inherit `can4hou6joeng4/boss-agent-cli`。原因是它已经具备 Python CLI、JSON envelope、MCP / Agent 友好输出、本地配置、登录/session 管理、SQLite/cache 思路和默认低风险 guardrails。它的默认模式已经阻断 `chat`、`chatmsg`、`greet`、`apply`、`reply` 等敏感命令，这和 V1 的只读优先、安全默认边界一致。

`geekgeekrun/geekgeekrun` 只作为求职者端 workflow 参考，例如职位搜索、打招呼流程、follow-up 逻辑和 LLM 生成消息模式。`jackwener/boss-cli` 只作为 capability/interface 或 fallback execution-layer 参考。除非后续证明 `boss-agent-cli` 不适合，否则 V1 不以它们为主基座。

## V1 Scope

V1 支持：

- 显式本地配置和 Boss 登录/session 授权后读取职位列表、职位详情、聊天列表和 HR 消息。
- 通过手动粘贴 / 导入消息进入 fallback 低风险模式。
- 对 HR 消息做 intent 分类。
- 对项目、简历、技术问题调用 Enterprise RAG 生成候选回复草稿。
- 保存 draft、risk labels、evidence、approval event 和 audit log。
- 在 review 命令里展示草稿、citations/evidence、risk labels 和审批状态。
- 以 approve-and-copy-to-clipboard 作为 MVP 输出路径。

V1 不支持：

- 全自动海投。
- 批量自动打招呼。
- 自动连续 follow-up 或骚扰 HR。
- 默认自动发送 Boss 消息。
- 绕过平台风控或规避平台限制。
- 把 Boss 原始消息、招聘者完整资料或完整职位详情默认塞进 RAG question。

## Architecture

```text
boss-agent-cli fork
  -> BossAutomationAdapter
  -> JobReader / MessageReader / OptionalSendWrapper(disabled by default)
  -> ManualImportAdapter
  -> BossRagReplyAgent
  -> MessageClassifier
  -> ApprovalPolicy
  -> RagAdapter -> Enterprise RAG HTTP API
  -> DraftStore + AuditLog
  -> CLI review / approve-copy commands
```

## Module Boundaries

`BossAutomationAdapter` 只负责 Boss 数据读取和可选发送包装。它不做消息分类、不拼 RAG prompt、不判断审批策略。消息读取必须受 `boss_rag.allow_message_read=true`、登录状态和本地授权记录共同控制；默认不通过全局关闭 `boss-agent-cli` 的 `low_risk_mode` 来获得能力。

`ManualImportAdapter` 负责从 clipboard、JSON、Markdown 或 CSV 接收手动消息输入，并标准化成与 Boss 读取一致的 local message model。

`BossRagReplyAgent` 负责编排：读取本地未处理消息、分类、按最小上下文构造 RAG 请求、保存草稿、记录 audit log，并把发送状态保持为默认禁止。

`MessageClassifier` 必须 rule-first。薪资、offer、面试时间、可用时间、离职状态、在职状态、个人承诺、微信/联系方式交换，以及任何不清晰但可能有风险的消息，都必须先命中 sensitive intent / risk labels，然后强制 `approval_required=true`。LLM classifier 只能作为非敏感分类的补充，不得覆盖 rule-first sensitive result。

`ApprovalPolicy` 决定 `approval_required`、`send_allowed` 和 `audit_status`。所有 draft 都不是最终回复；即使 `send_allowed=true`，MVP 也只走 approve-and-copy-to-clipboard。

`RagAdapter` 调用现有 Enterprise RAG。默认调用 `POST /api/v1/chat/ask`，只发送 HR question、必要的 short job summary 和 answer objective。Boss raw messages、recruiter info、full job details 默认留在本地 SQLite。

V1 的标准 intent 集合包括：

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

## Data Contract

Draft reply 必须使用显式字段，不能被当成最终回复：

```json
{
  "draft_text": "...",
  "intent": "project_question",
  "risk_labels": [],
  "evidence": {
    "rag_snapshot_id": "...",
    "citations": [],
    "source": "enterprise_rag"
  },
  "approval_required": true,
  "send_allowed": false,
  "audit_status": "draft_created"
}
```

## RAG Integration

现有 Enterprise RAG 的稳定入口是：

```text
POST /api/v1/chat/ask
```

当前 `ChatRequest` 字段包括 `question`、`top_k`、`mode`、`enable_external_search`、`session_id`、`document_id`、`category_id`。V1 不假设存在通用 `metadata` 字段。Boss metadata 由本地 SQLite 维护，并通过本地 `conversation_id` / `message_id` / `rag_session_id` 关联 RAG 请求。

如果后续需要审计或权限隔离能力，才提出一个极薄的内部 adapter endpoint；该变更需要按 Enterprise RAG 的 API-schema / stable contract 规则单独设计。

如果 `/api/v1/chat/ask` 超时、返回错误或解析失败，workflow 必须 fail closed：仍然落一条 draft 记录和 audit log，但该记录必须满足 `audit_status="rag_failed"`、`send_allowed=false`、`approval_required=true`，并且不会打开任何发送路径。

## Send Policy

V1 不需要真实 Boss send-message implementation。MVP 接受路径优先是 `approve-and-copy-to-clipboard`。

如果设计 send-message wrapper，它必须默认禁用，并且同时满足：

- explicit config flag；
- human confirmation；
- audit log；
- rate limit；
- sensitive-message policy gate。

它不得进入 initial MVP acceptance path。

## State Storage

本地 SQLite 保存 Boss context、message state、draft state、approval event、audit log 和 RAG call metadata。默认不上传 Boss 原始消息、招聘者详情或完整职位详情到 RAG。所有 secrets、cookie、token 仍沿用 `boss-agent-cli` 的脱敏和 auth/session 机制，不写入 audit log 明文。

## Risk Controls

主要风险包括平台政策风险、账号安全风险、反自动化检测、selector/API 脆弱性、登录态过期、消息误分类、承诺性回复误发、联系方式交换和隐私泄露。控制方式是：只读默认、显式 opt-in、发送禁用、sensitive rule-first、人工审批、audit log、rate limit、低频读取、错误 fail closed、manual import fallback。

## MVP Acceptance Criteria

- Manual import works。
- Mock `boss-agent-cli` JSON envelope works。
- Classifier produces the correct intent。
- Sensitive messages are blocked by approval policy。
- RAG adapter calls `/api/v1/chat/ask` correctly。
- Draft reply is saved。
- Review command shows draft, citations/evidence, and risk labels。
- Approval event is persisted。
- Audit log is written。
- No automatic sending is possible by default。

## Open Implementation Decision

实现阶段需要先确认是把 `BOSS_AGENT` 初始化为 `boss-agent-cli` fork 的工作目录，还是在 fork 上新增 `boss_rag` package。默认建议：以 fork 后的 `boss-agent-cli` 代码为基础，在 `src/boss_agent_cli/rag_reply/` 下新增 V1 模块，避免额外跨仓库 glue code。
