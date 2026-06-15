# Boss Agent Current Stage

> Last updated: 2026-06-15
>
> Scope: 本文档用于说明当前 `BOSS_AGENT` 项目已经推进到什么阶段、哪些链路已经可用、哪些仍然需要真实 Boss 会话验证，以及下一步应该怎么接着做。

## Executive Summary

当前项目处在 **本地前端模拟器 + Agent workflow 联调完成，准备进入真实 Boss 会话受控验收** 的阶段。

已经完成的核心能力是：

- 本地前端 `demo/interview-simulator` 可以通过 `/api/agent/ask` 调用后端 `boss agent ask`。
- 后端已经不是直接把前端问题当作普通 RAG 问答，而是进入 `BossRagReplyService`，由 Agent workflow 做意图分类、RAG 调用、本地策略回复、候选人口吻改写和草稿持久化。
- 常见 HR 问法已经有较稳定的候选人回答，包括项目介绍、自我介绍、代表项目、项目难点、系统设计、岗位匹配、协作方式。
- “发一下简历”现在会被识别为 `resume_share_request`，前端会带 `auto_send_resume: true`，后端会尝试进入自动发送在线简历流程。
- “为什么离职？”现在会被识别为 `resignation_status`，并生成保守、非空、适合 Boss 聊天场景的本地回答。

还没有完成的关键验收是：

- 尚未在一个真实 Boss 对话 `security_id` 上完成端到端发送验证。
- 当前前端实测中，“麻烦发一下简历”已经进入自动发送分支，但因为没有可用 `security_id`，返回 `missing_security_id`，所以没有真正发给 Boss 对话。
- 当前实现发送的是 Boss 官方在线简历路径，即 `client.send_resume(security_id)`；它不是本地 PDF 附件上传路径。

## Stage Definition

当前阶段可以定义为：

**Phase 3: Local Agent Workflow Ready, Live Boss Delivery Pending**

这个阶段的含义是：

- `Agent ask` 语义已经基本成型。
- 前端只是测试入口，不再承担 RAG 直连职责。
- RAG 是 Agent workflow 里的一个工具/上游知识来源，而不是前端直接暴露的最终回答者。
- 简历请求已经从“生成一句会发简历的回答”推进到“会尝试调用真实发送在线简历工具”。
- 离职、在职、时间安排等敏感 HR 问题已经有本地安全草稿，不再空响应。
- 真实 Boss 发送还需要 `security_id`、登录态、CDP 会话和 Boss 页面状态共同满足。

## Runtime Status

当前本地运行链路以这些端口和服务为主：

| Surface | Current status | Notes |
| --- | --- | --- |
| Frontend simulator | `http://127.0.0.1:5173` | Vite 本地前端，用于模拟 HR 提问和测试发送入口 |
| Enterprise RAG API | `http://127.0.0.1:8020` | `.env` 中 `BOSS_RAG_RAG_BASE_URL=http://127.0.0.1:8020` |
| RAG auth mode | `bearer` | `.env` 中 `BOSS_RAG_RAG_AUTH_MODE=bearer` |
| Resume send switch | enabled | `.env` 中 `BOSS_RAG_SEND_ENABLED=true` |
| Boss send target | pending | 需要真实 `security_id` |

## Architecture Status

当前前端调用链路是：

```text
demo/interview-simulator
  -> POST /api/agent/ask
  -> vite bridge runBossJsonCommand(...)
  -> boss agent ask
  -> BossRagReplyService
  -> classify_message(...)
  -> Enterprise RAG or local policy
  -> AgentAnswerAdapter / local template fallback
  -> draft + thread memory + optional delivery
```

发送到 Boss 的链路是：

```text
frontend "发送到 Boss" or auto_send_resume
  -> POST /api/agent/send or boss agent ask --auto-send-resume
  -> boss agent send / _maybe_auto_send_resume
  -> execute_chat_reply(...)
  -> client.send_chat_message(security_id, message)
  -> client.send_resume(security_id) when send_resume=true
```

这里有一个很重要的边界：

- `/api/agent/ask` 负责生成回答，并且在 `auto_send_resume=true` 且问题是发简历请求时尝试自动发送。
- `/api/agent/send` 负责把已经生成的 draft 发送到 Boss。
- 真正发送必须有 `security_id`。
- 没有 `security_id` 时，系统现在会返回明确状态：`missing_security_id`。

## Completed Work

### Agent Answer Quality

已完成：

- 常见 HR 项目问题会生成候选人口吻回答。
- 当上游 RAG 返回生硬 Markdown、第三人称描述或答案偏长时，会通过 `AgentAnswerAdapter` 做本地改写或模板兜底。
- 当没有外部 AI 改写服务时，不再错误复用 RAG API key 去调用 DeepSeek。
- 如果 RAG 问法不稳定或局部失败，典型 HR 问题可以通过本地模板兜底，避免前端出现空回答或 `502`。

覆盖的典型问题包括：

- `请你做一个简短的自我介绍，重点说和企业级 RAG 相关的经历。`
- `请介绍一下你做的企业级 RAG 项目，重点说清楚你的职责、核心技术方案和结果。`
- `你最有代表性的项目是什么？`
- `这个项目里你遇到过最难的问题是什么，你是怎么解决的？`
- `如果我们让你来做类似系统，你会怎么设计检索、重排和引用溯源？`
- `你为什么觉得自己适合这个岗位？`
- `你平时和产品、算法、后端是怎么协作的？`

### Resume Share Request

已完成：

- `发一下简历`、`麻烦发一下简历`、`方便发一份简历过来吗` 这类问题会识别为 `resume_share_request`。
- 前端 `handleAsk` 已经传 `auto_send_resume: true`。
- 后端 `boss agent ask --auto-send-resume` 会调用 `_maybe_auto_send_resume(...)`。
- `.env` 中 `BOSS_RAG_SEND_ENABLED=true` 时，发送开关是打开的。
- 如果缺少 `security_id`，前端会看到明确提示：`发送到 Boss 失败：当前没有可用的 security_id`。

当前状态：

- 自动发送逻辑已经接上。
- 尚未完成真实 Boss 对话发送，因为本地前端测试时没有可用 `security_id`。

### Resignation Question

已完成：

- `为什么离职？` 会识别为 `resignation_status`。
- 之前该意图属于敏感类，本地策略返回空字符串，导致前端看起来“没有响应”。
- 现在会返回保守的候选人回答，强调寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。

当前回答风格：

```text
我目前主要是希望寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。当前项目让我积累了企业级 RAG 从架构到落地的完整经验，下一步希望进入更成熟的 AI 团队或更有 AI 产品化空间的环境，把这类系统继续做深。
```

### Frontend Simulator

已完成：

- 前端 `Agent 问题输入` 能显示 Agent 最终回答。
- 离职问题前端实测可正常显示回答。
- 发简历问题前端实测可显示 `missing_security_id`，说明已经进入发送判断而不是静默失败。
- `发送到 Boss` 按钮仍然复用 `/api/agent/send`，用于手动发送当前 draft。

## Verification

### Automated Tests

已跑过的 focused tests：

```bash
pytest tests/test_rag_reply_classifier.py tests/test_rag_reply_question_builder.py tests/test_rag_reply_agent_answer.py tests/test_rag_reply_commands.py tests/test_rag_reply_service.py -q
```

当前结果：

```text
45 passed in 1.69s
```

### API Regression

已通过本地 `/api/agent/ask` 验证：

| Question | Expected intent | Observed result |
| --- | --- | --- |
| `麻烦发一下简历` | `resume_share_request` | 返回非空回答，并进入 auto-send 分支；因无 `security_id` 返回 `missing_security_id` |
| `为什么离职？` | `resignation_status` | 返回非空本地安全回答 |

### Browser Regression

已通过前端页面验证：

- `为什么离职？`：页面显示正常回答，耗时约 `284ms`。
- `麻烦发一下简历`：页面显示回答，并明确提示 `发送到 Boss 失败：当前没有可用的 security_id`。

截图证据：

```text
.gstack/qa-reports/screenshots/resume-and-resign-fix.png
```

## Current File Changes

当前这批阶段性改动主要集中在：

| File | Purpose |
| --- | --- |
| `demo/interview-simulator/src/App.jsx` | 前端 `ask` 请求带上 `auto_send_resume: true` |
| `src/boss_agent_cli/rag_reply/service.py` | 本地策略补齐简历发送、离职、在职、时间安排、面试时间等非空回答 |
| `tests/test_rag_reply_classifier.py` | 补充离职问题分类测试 |
| `tests/test_rag_reply_service.py` | 补充简历请求文案和离职本地草稿测试 |
| `src/boss_agent_cli/rag_reply/adapters/agent_answer.py` | 候选人口吻改写和 HR 模板兜底 |
| `src/boss_agent_cli/rag_reply/classifier.py` | 扩展真实 HR 问法分类 |
| `src/boss_agent_cli/rag_reply/question_builder.py` | 改善进入 Enterprise RAG 的候选人面试问法包装 |
| `src/boss_agent_cli/commands/rag.py` | Agent workflow 构建不再错误复用 RAG key 作为外部 AI key |

## Open Boundaries

### Real Boss Delivery

尚未完成：

- 使用真实 Boss 会话 `security_id` 发出一条消息。
- 使用真实 Boss 会话 `security_id` 调用 `client.send_resume(security_id)` 并确认 Boss 页面实际显示在线简历已发出。

下一步验收条件：

```text
输入：真实 security_id + HR 问“麻烦发一下简历”
预期：delivery.status = sent
预期：message_sent = true
预期：resume_sent = true
预期：Boss 页面能看到消息和在线简历发送状态
```

如果返回：

```text
missing_security_id
```

说明前端还没有选中或填入真实 Boss 会话目标。

如果返回：

```text
resume_failed
```

说明消息可能已发出，但 Boss 在线简历发送接口失败，需要继续看 `client.send_resume(...)` 的响应。

如果返回：

```text
message_failed
```

说明第一步聊天消息发送失败，需要检查登录态、CDP 连接、Boss 页面状态或 `security_id` 是否过期。

### Online Resume vs Local PDF

当前实现路径是：

```text
client.send_resume(security_id)
```

含义是发送 Boss 平台的在线简历。

当前没有实现：

```text
上传 /home/reggie/vscode_folder/BOSS_AGENT/孙瑞杰的简历.pdf 作为本地 PDF 附件
```

原因是 Boss 的“在线简历主动发”和“本地 PDF 附件发”不是同一个交互。当前项目优先接入的是 Boss 官方在线简历发送路径。

### Sensitive Intent Policy

目前策略是：

- `resume_share_request`：生成回答，并可在 `auto_send_resume=true` 时尝试真实发送。
- `resignation_status`：生成保守求职动机回答。
- `personal_status`：生成在职看机会和到岗时间说明。
- `availability_or_schedule`：生成可协调时间的回答。
- `interview_time`：生成可配合面试安排的回答。
- `salary_or_offer`、`contact_exchange`、`unsafe_or_unclear`：仍然默认空草稿，需要人工处理。

这个边界是有意保留的：薪资、联系方式交换、模糊不安全内容仍然不应该自动回复或自动发送。

## Next Steps

### Step 1: Provide or Select a Real `security_id`

在前端中通过以下任一方式提供真实目标：

- 在 `BOSS 直聘 · 全自动投递` 区域搜索并选择职位，使 `Security ID` 自动填入。
- 手动填入一个真实 Boss 会话对应的 `security_id`。

没有 `security_id` 时，发简历请求只能生成草稿，无法真正发出。

### Step 2: Run Resume Send Smoke

在前端输入：

```text
麻烦发一下简历
```

期望结果：

```json
{
  "delivery": {
    "status": "sent",
    "message_sent": true,
    "resume_sent": true
  }
}
```

同时在 Boss 页面确认在线简历确实发出。

### Step 3: Run Sensitive HR Smoke

继续测试这些 HR 问法：

```text
为什么离职？
现在是在职吗？
什么时候方便面试？
方便发一份简历过来吗？
```

期望：

- 都有非空回答。
- 只有发简历请求会尝试调用发送在线简历工具。
- 其它敏感问题只生成草稿，不自动发送。

### Step 4: Decide Whether to Support Local PDF Attachment

如果目标必须是发送本地 PDF：

```text
/home/reggie/vscode_folder/BOSS_AGENT/孙瑞杰的简历.pdf
```

那需要新接一条 Boss 页面附件上传交互，不能复用当前 `client.send_resume(security_id)`。

建议先完成在线简历发送验收，再决定是否追加本地 PDF 附件路径。

## Stage Exit Criteria

当前阶段退出条件是：

- 前端选中真实 `security_id` 后，`麻烦发一下简历` 能真实发送 Boss 消息。
- `delivery.status=sent`。
- `message_sent=true`。
- `resume_sent=true`。
- Boss 页面实际可见在线简历发送成功。
- `为什么离职？`、`现在是在职吗？`、`什么时候方便面试？` 在前端均能返回非空安全回答。
- 相关 focused tests 保持通过。

满足以上条件后，项目可以进入：

**Phase 4: Live Boss Delivery Verified**

也就是从“本地模拟器联调完成”进入“真实 Boss 场景可用”的阶段。

