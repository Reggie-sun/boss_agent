# Boss Commercial Profile RAG Design

## Goal

本设计把当前 `BOSS_AGENT` 从单人本地求职助手推进到 commercial-ready self-hosted 形态：支持多个用户、一个用户多个 profile、资料通过 RAG 上传和检索、Boss 会话绑定 profile，并保留现有前端测试对话、自动开聊、自动投简历、被动 watcher、CLI、MCP 和 Docker 运行方式。

核心原则是：现有能力全部保留，profile/RAG 多用户化作为增强层叠加，商业化字段和用量统计真实落库，但第一版不接真实支付回调。

## Selected Approach

采用 `Profile Hub + Thin RAG Connector`。

`BOSS_AGENT` 负责产品和业务状态：`tenant_id`、`user_id`、`profile_id`、profile 配置、资料上传任务、Boss 会话绑定、用量统计、配额、审计和前端控制台。外部 RAG 负责文档解析、索引、检索、citation 和知识库隔离。

不采用把 profile 全部放在 RAG 服务里的方案，因为那会削弱 `BOSS_AGENT` 对上传状态、会话绑定、配额和审计的控制。不采用本地保存完整资料副本并同步 RAG 的方案，因为早期会增加隐私、同步和迁移复杂度。

## Non-Negotiable Capability Preservation

商业化改造不能删除现有能力。允许强化、改路由、补 profile 上下文或增加安全 gate，但不能让既有能力消失。

必须保留：

- 前端测试对话和 demo conversation。
- `Boss 自动开聊`。
- 搜索筛选、预览、选定目标、`Agent 全自动`。
- 自动投简历和附件简历发送能力。
- 被动 watcher 和 HR 对话自动回复。
- 手动导入、draft、review、approve/copy 等 CLI 流程。
- 当前 MCP server 和 Docker 启动方式。
- 当前 CDP fail-closed 和附件简历官方 UI 路径约束。

迁移策略必须先保证旧功能继续能跑，再把 `user_id/profile_id/knowledge_base_id` 接入相关链路。

## Product Routes

前端可以拆成两个路由或两个一级 tab，但两条能力都要保留。

`/agent/reply` 面向已有 Boss 会话：

- 展示前端测试对话。
- 展示已同步 HR 会话。
- 绑定或切换 profile。
- 查看 draft、evidence、RAG 状态和 watcher 状态。
- 处理被动自动回复和人工 review。

`/agent/outreach` 面向主动触达：

- 保留当前 `Boss 自动开聊` 面板。
- 保留搜索条件、预览、目标选择、`Agent 全自动`。
- 保留自动投简历和附件简历能力。
- 使用 profile 的结构化配置和 RAG 资料生成开聊语、筛选解释或后续回复。

两条路由共享 `ProfileStore`、`ProfileConfig`、配额、用量和审计，但业务状态分开。自动回复和自动开聊的开关也必须分开，避免一个开关同时放开两类风险。

## Architecture

整体架构：

```text
CLI + Console
  -> ProfileStore
  -> ProfileUpload
  -> RagProfileConnector
  -> External RAG knowledge_base_id

Boss conversation
  -> ConversationProfileBinding
  -> question_builder(user_id, profile_id, knowledge_base_id)
  -> RagHttpAdapter
  -> AgentAnswerAdapter
  -> policy / send gate
```

`BOSS_AGENT` 新增 profile hub 层，但不实现向量检索。RAG connector 是薄适配层，负责创建知识库、上传文档、查询索引状态和带 profile 上下文发起问答。

`agent_answer.py` 从候选人事实模板收缩成通用回答编排器。它只保留必要系统行为：候选人第一人称、禁止编造、不要提 RAG/知识库、JSON 输出、引用约束、自然口吻、失败时保守降级或 fail closed。它不允许出现具体人名、公司、项目数字或固定个人经历。

## Data Model

第一版新增或扩展以下模型。所有商业化相关表都必须包含 `tenant_id` 或能从 `user_id` 稳定追溯到租户。

`Tenant`：

```text
tenant_id
display_name
plan_code: free | pro | team | enterprise
subscription_status: trial | active | past_due | suspended | canceled
license_key_hash
payment_provider
provider_customer_id
provider_subscription_id
created_at / updated_at
```

`User`：

```text
tenant_id
user_id
display_name
email
role: owner | admin | member
status: active | suspended
created_at / updated_at
```

`UserProfile`：

```text
tenant_id
user_id
profile_id
display_name
target_title
knowledge_base_id
status: active | archived
created_at / updated_at
```

`ProfileConfig`：

```text
tenant_id
profile_id
contact_phone
contact_wechat
interview_windows
salary_reply_policy
resume_attachment_path
reply_auto_send_enabled
outreach_auto_send_enabled
proactive_resume_enabled
```

这些字段可以为空。为空时对应 intent 必须 blocked 或 manual required，不能让模型临时猜。

`ProfileUpload`：

```text
tenant_id
user_id
profile_id
upload_id
source_filename
source_type: resume | project | work_experience | personal_note | other
source_size_bytes
rag_document_id
status: queued | uploaded | indexed | failed
error_message
created_at / updated_at
```

`ConversationProfileBinding`：

```text
tenant_id
conversation_id
user_id
profile_id
knowledge_base_id
binding_source: manual | default | imported
created_at / updated_at
```

`UsageCounter`：

```text
tenant_id
user_id
profile_id
metric_name
period_start
period_end
used_count
limit_count
updated_at
```

第一版需要统计 profile 数量、上传数量、上传大小、RAG 调用量、自动回复次数、自动开聊次数、附件简历发送次数。

## RAG Contract

RAG connector 需要的最小 contract：

```text
create_knowledge_base(tenant_id, user_id, profile_id) -> knowledge_base_id
upload_profile_document(tenant_id, user_id, profile_id, knowledge_base_id, file/text, source_type) -> rag_document_id
get_document_status(tenant_id, user_id, profile_id, rag_document_id) -> status
ask_profile(tenant_id, user_id, profile_id, knowledge_base_id, question, mode) -> answer + citations + reasoning_summary
```

如果外部 Enterprise RAG 暂时没有这些 endpoint，可以由 `RagProfileConnector` 先适配当前 `/api/v1/chat/ask`，但本地请求记录和未来接口命名必须按上述 contract 设计，避免后续商业化迁移时重写业务层。

所有问答请求必须同时带 `tenant_id/user_id/profile_id/knowledge_base_id`。`knowledge_base_id` 缺失或与绑定 profile 不一致时，直接 blocked。

## Data Flow

### Profile Onboarding

用户通过 CLI 或控制台创建 profile，填写目标方向和高风险结构化配置，然后上传简历、项目经历、工作经历和个人补充说明。

`BOSS_AGENT` 创建 `UserProfile` 和 `ProfileUpload` 记录，调用 `RagProfileConnector` 转交 RAG。RAG 返回 `knowledge_base_id`、`rag_document_id` 和索引状态。`BOSS_AGENT` 保存引用和状态，不自己做向量检索。

### Conversation Binding

同步到新的 Boss 会话时，先查 `ConversationProfileBinding`。没有绑定时，控制台或 CLI 让用户选择 profile；也可以使用默认 profile，但必须写 `binding_source=default` 和 audit log。

绑定后，同一会话后续问题固定使用该 profile。用户可以手动 rebind，但 rebind 必须写 audit，并且旧 draft 不应被改写成新 profile 的结果。

### Reply Generation

HR 消息进入现有 `classifier`。项目、简历、工作经历、技术栈、候选人能力相关事实问题走 RAG path。`question_builder` 使用 HR 问题、短岗位摘要、answer objective，以及绑定的 `tenant_id/user_id/profile_id/knowledge_base_id` 构造请求。

RAG 返回 grounded answer 和 citations 后，`AgentAnswerAdapter` 只做第一人称和沟通口吻整理。没有 citations、低置信或 profile 绑定缺失时，不自动发送。

薪资、联系方式、面试时间、附件简历路径、自动发送权限走 `ProfileConfig`，不问 RAG。配置缺失、多值不唯一或 license/quota gate 不通过时 blocked。

### Outreach Generation

主动开聊保留现有搜索、筛选、预览和目标选择流程。profile 层只提供候选人身份和可用资料，不替代 Boss 搜索链路。

自动开聊文案可以使用 profile RAG 和岗位摘要生成，但发送前必须通过 outreach gate：全局发送开关、`ProfileConfig.outreach_auto_send_enabled`、配额、目标唯一性、CDP ready、平台页面确认。

自动投简历和附件简历发送继续走现有 CDP 官方 UI 路径，不允许转换成普通聊天文本 fallback。

## Commercial Gates

第一版不接真实支付回调，但订阅和支付字段要预留，配额和用量要真实生效。

功能 gate 按能力维度执行：

- license 无效或 tenant suspended：禁止新建 profile、上传资料、自动回复、自动开聊和附件发送；允许查看历史和导出。
- profile 数达到 plan 限制：禁止新建 profile。
- 上传数量或大小超额：禁止新增上传。
- RAG 调用超额：允许人工查看历史，禁止自动生成新 RAG draft。
- 自动回复次数超额：禁止自动发送，允许生成人工 review draft。
- 自动开聊次数超额：禁止 outreach 自动发送。
- 附件简历发送次数超额：禁止自动附件发送。

payment provider 字段只做保存和展示，不处理 Stripe、微信或支付宝回调。后续接支付时，不应改变核心 profile、usage 和 gate 模型。

## CLI/API/Console Surface

CLI 新增：

```text
boss agent profile create --user-id <id> --name <name> --target-title <title>
boss agent profile list --user-id <id>
boss agent profile config set --profile-id <id> ...
boss agent profile upload --profile-id <id> --type resume --file <path>
boss agent profile upload-status --profile-id <id>
boss agent conversation bind-profile --conversation-id <id> --profile-id <id>
boss agent conversation profile --conversation-id <id>
boss agent usage summary --tenant-id <id>
```

本地 API 给控制台复用：

```text
GET /api/profiles?user_id=...
POST /api/profiles
PATCH /api/profiles/:profile_id/config
POST /api/profiles/:profile_id/uploads
GET /api/profiles/:profile_id/uploads
POST /api/conversations/:conversation_id/profile-binding
GET /api/conversations/:conversation_id/profile-binding
GET /api/usage?tenant_id=...
GET /api/admin/tenants
```

控制台第一版：

- profile 列表和创建。
- profile 高风险配置编辑。
- 上传资料并显示索引状态。
- 在会话详情里绑定或切换 profile。
- 在 draft/evidence 里显示当前 profile 和 `knowledge_base_id`。
- 在 outreach 页面保留现有自动开聊面板。
- admin 页面展示 tenant、user、profile、用量、失败和 audit 摘要。

控制台不直接做检索，不直接拼 prompt，不绕过后端 policy。

## Error Handling And Safety

RAG 上传失败时，`ProfileUpload.status=failed` 并保存错误。索引未完成时，profile 可以存在，但不能用于自动回答事实问题。

RAG answer 无 citation、低置信、空 answer 或 knowledge base 不匹配时，不自动发送，状态为 `rag_low_confidence` 或 `blocked_manual_required`。

联系方式为空或多值不唯一时，不发送。面试时间为空时，根据 profile policy 转人工或发送明确的托管回复。薪资策略为空时固定转人工，不让模型猜薪资。附件简历路径不存在时，不点击 Boss UI，也不转成普通文本发送。

真实 Boss 发送沿用当前仓库安全边界：CDP 不可用时 fail closed；不能静默 fallback 到 headless 或 Bridge delivery；附件简历只能通过官方 UI 和已验证的 PDF 上传路径。

## Testing Strategy

### Unit Tests

- `ProfileStore` 创建、读取、归档 profile。
- `ProfileConfig` 高风险字段校验。
- `ConversationProfileBinding` 固定同一会话 profile。
- `UsageCounter` 超额 gate。
- `AgentAnswerAdapter` 不含个人硬编码模板。
- `question_builder` 和 `RagHttpAdapter` 带上 `tenant_id/user_id/profile_id/knowledge_base_id`。

### Integration Tests

- fake RAG 下创建 profile、上传资料、索引完成。
- 绑定 Boss 会话到 profile 后生成 RAG draft。
- 会话 A 不能使用会话 B 的 profile 或 knowledge base。
- 配额超额时禁止自动回复或自动开聊。
- 结构化联系方式、面试时间、薪资策略不从 RAG 猜。

### Frontend Smoke

- 现有前端测试对话仍显示。
- 测试对话能打开详情。
- 测试对话可以可选绑定 demo profile，但可重置。
- reply 路由能看到 profile、draft、evidence 和 watcher 状态。
- outreach 路由仍显示当前 `Boss 自动开聊`、筛选、预览、目标选择和 `Agent 全自动`。
- 自动投简历入口仍存在。

### Live Boss Verification

任何影响 Boss 搜索、自动开聊、自动投简历、CDP、Bridge delivery 或 outreach 聚合的代码变更，都必须按仓库规则跑一次 bounded real Boss verification，并报告 `total_greeted`、`total_failed`、`stopped_reason` 和平台错误。

profile/RAG docs-only 或纯本地 store 变更不声称 live Boss 成功，除非真实 CDP 验证已跑。

## Migration Plan

第一阶段只新增表、API 和 UI，不删除旧字段，不清空现有 conversation/message/draft 数据。

第二阶段给现有 reply path 接入 profile binding。没有绑定时继续允许 manual review，但事实型自动回复必须提示绑定 profile。

第三阶段给 outreach path 接入 profile config 和 usage gate。保留现有筛选、预览、目标选择和自动投简历 UI。

第四阶段移除 `agent_answer.py` 中个人事实模板，改成 profile RAG 或 blocked/manual required。删除模板前必须有测试证明前端测试对话和常见 demo flow 仍然可用。

## Acceptance Criteria

- 当前已有能力没有消失。
- 一个 tenant 下可以有多个 user，一个 user 下可以有多个 profile。
- profile 资料通过 RAG connector 上传并记录索引状态。
- Boss 会话可以绑定 profile，后续同一会话固定使用该 profile。
- RAG 请求带 `tenant_id/user_id/profile_id/knowledge_base_id`。
- `agent_answer.py` 不再包含具体候选人事实硬编码。
- 联系方式、面试时间、薪资策略、附件简历路径和自动发送权限来自 `ProfileConfig`。
- 商业化字段、subscription 状态、plan、license、usage 和 quota 可落库并参与 gate。
- 支付 provider 字段预留，但第一版不接真实支付回调。
- 前端测试对话保留。
- `Boss 自动开聊` 和自动投简历能力保留。
- Docker/MCP 启动方式保留。

## Out Of Scope

- Stripe、微信、支付宝等真实支付回调。
- 多 RAG 后端自动迁移。
- 机构级候选人池批量托管。
- 绕过 Boss 平台风控、登录限制或官方 UI 约束。
- 把 RAG 检索实现塞进 `BOSS_AGENT`。
