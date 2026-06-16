# Boss Agent Passive Watcher Design

## Executive Summary

第一版目标是做一个 **后台常驻 watcher + 前端控制台** 的被动自动代理。它只处理已经进入 Boss 聊天的 HR 消息，不做主动找岗位、主动开聊或批量触达。

自动策略采用保守白名单：项目/简历能力问答、发附件 PDF 简历、面试时间、可约时间、寒暄、离职/在职状态、联系方式和薪资托管回复。需要 RAG 的问题调用 Enterprise RAG，再整理成候选人口吻；不需要 RAG 的意图走本地固定策略或配置。薪资问题不回答具体数字，只发送 Agent 托管话术并转人工。

产品形态采用可观察控制台：后台可以自动跑，但用户必须能看到队列、分类、RAG 调用、发送结果、失败原因，并能全局暂停或禁用单个会话。

## Scope

本 spec 覆盖第一版被动闭环：

- 后台 watcher 周期性检查 Boss 聊天和运行前置条件。
- 自动读取最近会话的新 inbound HR 消息。
- 根据 intent 决定是否调用 RAG、使用本地策略、发送附件简历、回复联系方式、协商面试时间或转人工。
- 将每次决策和动作写入 audit log。
- 前端控制台展示 watcher 状态、队列、会话结果和 blocked 原因。

本 spec 不覆盖：

- 主动搜索岗位。
- 主动打招呼或主动开聊。
- 批量触达。
- 绕过 Boss 风控或登录限制。
- 自动承诺薪资、offer、入职日期或任何需要本人确认的最终条件。

## Architecture

系统新增一个 `agent watcher` 编排层。它复用现有 `BossRagReplyService`、`RagHttpAdapter`、`AgentAnswerAdapter`、`execute_chat_reply(...)` 和 `send_resume_attachment(...)` 能力，不把前端做成决策中心。

后台 watcher 的职责：

- 做 runtime preflight。
- 读取最近 Boss 会话的新消息。
- 生成去重后的处理任务。
- 调用 classifier 和 draft service。
- 根据 policy 选择 action。
- 调用 Boss 发送或附件上传链路。
- 写入任务状态和 audit log。

前端控制台的职责：

- 展示 watcher 是否运行、暂停或故障。
- 展示最近队列、当前任务、会话状态和 action 结果。
- 展示每条消息的 intent、risk labels、RAG 状态、draft、发送路径和错误原因。
- 提供全局暂停、恢复、单会话禁用和单会话恢复入口。

核心设计原则是：后台负责自动化，前端负责可观察和控制。即使后台是自动模式，也不能变成黑盒。

## Intent Policy

第一版自动处理以下 intent：

- `project_question`：调用 Enterprise RAG，使用 `AgentAnswerAdapter` 整理成候选人口吻，自动发送文本。
- `resume_question`：调用 Enterprise RAG，使用 `AgentAnswerAdapter` 整理成候选人口吻，自动发送文本。
- `resume_share_request`：发送固定候选人回复，并通过附件 PDF 简历链路发送本地简历。
- `interview_time`：读取固定可约时间段配置，自动回复可约窗口，请 HR 选择具体时间。
- `availability_or_schedule`：读取固定可约时间段配置，自动回复可协调窗口。
- `contact_exchange`：从配置读取唯一手机号和唯一微信号，自动一起回复。
- `smalltalk`：使用本地固定礼貌回复。
- `resignation_status`：使用本地保守离职动机回复。
- `personal_status`：使用本地保守在职和到岗时间说明。
- `salary_or_offer`：发送固定 Agent 托管回复，然后将会话标记为 `blocked_manual_required`。

第一版 blocked 场景：

- intent 无法判断。
- `security_id` 缺失。
- 目标招聘者、公司或岗位不唯一。
- Boss 登录态过期。
- Boss 聊天页不可达。
- 附件上传 UI 不确定。
- RAG 失败且本地模板没有可信兜底。
- 手机号或微信号配置缺失、不唯一或为空。
- 同一会话连续失败达到阈值。

## Salary Handling

薪资问题不静默失败，也不回答具体薪资。

当 classifier 识别为 `salary_or_offer` 时，watcher 自动发送固定托管回复：

```text
我是候选人的求职助理 Agent，薪资相关问题需要候选人本人确认后回复。我已经记录下来，会提醒本人尽快处理。
```

发送后，该会话进入 `blocked_manual_required`。watcher 后续不再围绕同一个薪资话题继续自动回复，避免重复刷屏。前端控制台显示“薪资问题已转真人”，audit log 记录 `salary_or_offer -> blocked_manual_required`。

## Contact Handling

联系方式是可自动回复的固定信息，不再默认 blocked。

第一版要求同时配置唯一手机号和唯一微信号。HR 要联系方式时，watcher 回复这两个值。系统不得从历史聊天、RAG 答案或模型输出里临时猜联系方式。

如果手机号或微信号缺失、为空或出现多个候选值，任务进入 `blocked_manual_required`，不发送任何联系方式。

## Data Flow

1. watcher 周期性运行 runtime preflight：CDP 可连接、Boss 聊天页可达、Boss 登录态有效、附件 PDF 路径存在、RAG health 可用或存在可接受降级路径。
2. watcher 读取最近 Boss 会话的新 inbound 消息。
3. watcher 通过 `conversation_id + message_id/text hash` 去重，避免重复处理同一条 HR 消息。
4. 每条新消息进入 classifier。
5. `project_question` 和 `resume_question` 进入 RAG path：构造 RAG question，调用 Enterprise RAG，使用 agent answer adapter 改写，自动发送文本。
6. `resume_share_request` 进入 attachment resume path：发送固定回复，然后调用附件 PDF 上传链路。
7. `interview_time` 和 `availability_or_schedule` 进入 schedule path：读取固定可约窗口并回复。
8. `contact_exchange` 进入 contact path：读取唯一手机号和微信号并回复。
9. `salary_or_offer` 进入 salary handoff path：发送固定 Agent 托管回复，然后标记人工接管。
10. 发送前做 target gate：确认 `security_id`、招聘者名、公司和职位没有冲突。
11. 每次动作写入 audit log：分类结果、RAG request、draft、发送路径、状态、错误原因和页面可见验证信号。
12. 前端控制台轮询本地状态 API，展示队列、结果和 blocked 原因。

## Attachment Resume Flow

第一版默认发送附件 PDF 简历，而不是 Boss 在线简历。

附件上传必须遵循当前已知 Boss UI 边界：

- 有“附件简历请求卡片”时，优先点聊天记录里的 `同意`。
- 没有请求卡片时，才走聊天工具栏里的 `发简历` 主动发送链路。
- 主动链路必须打开简历弹层，选择 `上传附件简历`、`上传简历` 或 `附件简历`。
- 只能使用 `ka="user-resume-upload-file"` 或 accept 包含 `pdf` 的 file input。
- 只能在可见“简历 / 附件 / RESUME / EXPORT”语义的弹层内点击确认或发送。
- 禁止 fallback 到普通 `.btn-send:not(.disabled)` 文本发送按钮。
- 发送后用聊天记录里出现的 PDF 文件名作为成功确认信号。

如果页面导航导致 `Execution context was destroyed`，发送层可以等待页面恢复并重试进入工具栏 fallback。若目标会话不唯一或弹层语义不确定，必须 blocked。

## Safety Gates

自动发送前必须通过以下 gate：

- **Runtime gate**：`watcher_enabled=true`、CDP 可连接、Boss 聊天页可达、Boss 登录态有效。
- **Target gate**：消息绑定到唯一 `security_id`，招聘者名、公司和职位没有冲突。
- **Intent gate**：intent 必须在自动白名单内，或属于薪资托管回复。
- **RAG gate**：需要 RAG 的问题必须有可信 RAG 答案，或命中本地候选人模板降级。
- **Attachment gate**：附件 PDF 存在，上传 UI 明确，不能误点普通文本发送按钮。
- **Contact gate**：手机号和微信号都配置且唯一。
- **Rate gate**：同一会话短时间只处理一次新消息，同一 draft 不重复发送，连续失败后暂停该会话。
- **Manual stop gate**：前端全局暂停或单会话禁用必须在下一轮立即生效。

## Status Model

watcher 任务使用统一状态，前端直接展示这些状态：

- `queued`：任务已进入队列。
- `processing`：任务正在处理。
- `sent`：文本或附件发送成功。
- `blocked_manual_required`：需要真人接管。
- `skipped_duplicate`：重复消息，已跳过。
- `runtime_unavailable`：运行环境不可用。
- `target_ambiguous`：目标会话不唯一。
- `rag_failed`：RAG 失败且没有可接受降级。
- `attachment_failed`：附件上传失败。
- `send_failed`：消息发送失败。
- `paused`：全局或会话暂停。

失败不能包装成成功。前端和 CLI 输出必须诚实显示真实状态。

## Configuration

第一版需要新增或复用以下配置项：

- `boss_rag_watcher_enabled`：是否启用 watcher。
- `boss_rag_watcher_poll_seconds`：轮询间隔。
- `boss_rag_watcher_max_failures_per_conversation`：单会话连续失败暂停阈值。
- `boss_rag_resume_attachment_path`：附件 PDF 简历路径。
- `boss_rag_contact_phone`：唯一手机号。
- `boss_rag_contact_wechat`：唯一微信号。
- `boss_rag_interview_windows`：固定可约时间段，例如“工作日 20:00 后，周末全天”。
- `boss_rag_watcher_dry_run`：只生成动作和 audit，不真实发送。

默认配置应偏安全：watcher 默认关闭，dry-run 可用于本地验证，真实发送必须显式开启。

## Frontend Console

前端控制台可以基于现有 `demo/interview-simulator` 扩展，也可以新增同目录下的 watcher tab。

第一版控制台必须包含：

- watcher 运行状态。
- runtime health：CDP、Boss chat page、RAG、附件 PDF。
- 队列列表：会话、HR 最新消息、intent、状态。
- 当前任务详情：RAG 调用、draft、action、错误。
- 发送结果：文本发送、附件上传、PDF 文件名确认。
- 控制按钮：全局暂停、恢复、禁用当前会话、恢复当前会话。

控制台不负责生成最终决策，只读 watcher 状态并发送控制命令。

## Testing Strategy

测试分四层，不能把 mock 成功误报为真实 Boss 成功。

### Unit Tests

覆盖 classifier 和 policy：

- `contact_exchange` 自动生成手机号 + 微信号回复。
- 手机号或微信号缺失时进入 `blocked_manual_required`。
- `salary_or_offer` 生成固定 Agent 托管回复，并转人工。
- `resume_share_request` 选择附件简历动作。
- `project_question` 和 `resume_question` 触发 RAG 或本地模板降级。
- 重复消息不二次发送。

### Integration Tests

用 fake Boss adapter 跑 watcher 单轮：

- 读取新 inbound 消息。
- 生成 draft。
- 调用正确 action。
- 写入 audit log。
- 前端状态 API 能看到队列、结果和 blocked 原因。

附件简历链路保留现有关键回归：

- 有请求卡片优先 `同意`。
- 无请求卡片走工具栏上传。
- 不点击普通文本发送按钮。
- `Execution context was destroyed` 后能恢复并进入工具栏 fallback。

### Local Runtime Smoke

启动 watcher 和前端控制台，验证：

- 暂停和恢复。
- 单会话禁用和恢复。
- health preflight。
- RAG health。
- 附件 PDF 路径检查。
- dry-run 队列状态。

这一层只能证明本地状态机正常，不能声称 Boss 真实发出。

### Live Boss E2E Acceptance

只有真实 CDP profile 满足以下条件时才跑：

- `/api/agent/health` 返回 `preflightStatus=ready`。
- `boss status --live` 通过。
- 目标 Boss 会话唯一。

验收项：

- HR 问项目问题，agent 自动 RAG 回答，Boss 页面可见文本。
- HR 要简历，agent 自动上传附件 PDF，Boss 页面可见 PDF 文件名。
- HR 约面试，agent 自动回复固定可约时间段。
- HR 要联系方式，agent 自动回复手机号 + 微信号。
- HR 问薪资，Boss 页面可见 Agent 托管回复，watcher audit log 标记 `salary_or_offer -> blocked_manual_required`。

## Acceptance Criteria

第一版完成的判定标准：

- watcher 可后台运行，默认关闭，显式启用后开始轮询。
- 控制台能显示 watcher 状态、队列、结果、错误和暂停控制。
- 自动回复白名单 intent 能按设计发送。
- 附件 PDF 简历路径按 UI 边界执行，不误点普通发送按钮。
- 联系方式回复只使用配置中的唯一手机号和微信号。
- 薪资问题发送固定 Agent 托管回复后转人工。
- 所有动作可在 audit log 中追踪。
- focused tests、integration tests 和 local runtime smoke 通过。
- live Boss E2E 只在真实 preflight ready 后报告成功。

## Open Risks

- Boss 页面 DOM 和 Vue 内部结构可能漂移，附件上传和目标选择需要持续回归。
- 当前真实环境曾出现 `/web/geek/chat` 跳转到 `/web/user/` 的登录前置态；watcher 不能绕过这个问题，只能准确 blocked。
- RAG 服务延迟或失败时，需要明确哪些问题可模板降级，哪些必须 blocked。
- 后台常驻 watcher 需要限频和去重，否则容易重复回复。
- 自动联系方式和薪资托管回复都是真实发送，配置错误会直接影响 Boss 对话，因此配置校验必须严格。
