# Boss Agent Current Stage

> Last updated: 2026-06-17
>
> Scope: 本文档用于说明当前 `BOSS_AGENT` 项目已经推进到什么阶段、哪些链路已经可用、哪些仍然需要真实 Boss 会话验证，以及下一步应该怎么接着做。

## Executive Summary

当前项目处在 **本地前端模拟器 + Agent workflow 联调完成，真实 Boss 发送预检已接入，但候选人聊天页登录前置态仍未通过** 的阶段。

和上一阶段相比，当前结论已经发生了一个关键变化：

- 之前最大的表面报错是 `missing_security_id`。
- 现在 `security_id` 兜底链路已经接上，前端不再要求手工先点一个目标才能测试。
- 当前真正挡住真实发送的根因已经收敛为：**当前 9222 CDP profile 访问 `https://www.zhipin.com/web/geek/chat` 时会被重定向到 `https://www.zhipin.com/web/user/`**。

已经完成的核心能力是：

- 本地前端 `demo/interview-simulator` 可以通过 `/api/agent/ask` 调用后端 `boss agent ask`。
- 后端已经不是直接把前端问题当作普通 RAG 问答，而是进入 `BossRagReplyService`，由 Agent workflow 做意图分类、RAG 调用、本地策略回复、候选人口吻改写和草稿持久化。
- 常见 HR 问法已经有较稳定的候选人回答，包括项目介绍、自我介绍、代表项目、项目难点、系统设计、岗位匹配、协作方式。
- “发一下简历”会识别为 `resume_share_request`，前端会带 `auto_send_resume: true`，后端会尝试进入真实发送链路。
- 前端现在会在提问和发送两个入口里自动补齐可用 `security_id`，不再因为“没有手工选目标”就直接失败。
- 前端和后端都已经改成：**不是只看 CDP 端口通不通，而是预检 Boss 候选人聊天页是否真的可达**。

还没有完成的关键验收是：

- 尚未在一个真实 Boss 对话 `security_id` 上完成端到端发送验证。
- 当前真实阻塞不再是 `missing_security_id`，而是 `chat_login_redirect` / `AUTH_EXPIRED`。
- 当前实现发送的是 Boss 官方在线简历路径，即 `client.send_resume(security_id)`；它不是本地 PDF 附件上传路径。

## Stage Definition

当前阶段可以定义为：

**Phase 3: Local Agent Workflow Ready, Live Boss Delivery Blocked by Chat-Route Preflight**

这个阶段的含义是：

- `Agent ask` 语义已经基本成型。
- 前端只是测试入口，不再承担 RAG 直连职责。
- RAG 是 Agent workflow 里的一个工具/上游知识来源，而不是前端直接暴露的最终回答者。
- 简历请求已经从“生成一句会发简历的回答”推进到“会尝试调用真实发送在线简历工具”。
- 离职、在职、时间安排等敏感 HR 问题已经有本地安全草稿，不再空响应。
- 真实 Boss 发送现在需要同时满足：
  - `security_id` 可解析
  - `boss status --live` 可通过
  - CDP Chrome 候选人聊天页可达
  - Boss 页面不再把 `/web/geek/chat` 重定向回 `/web/user/`

## Runtime Status

当前本地运行链路以这些端口和服务为主：

| Surface | Current status | Notes |
| --- | --- | --- |
| Frontend simulator | `http://127.0.0.1:5175` | Vite 本地前端，用于模拟 HR 提问和测试发送入口 |
| Enterprise RAG API | `http://127.0.0.1:8020` | `.env` 中 `BOSS_RAG_RAG_BASE_URL=http://127.0.0.1:8020` |
| RAG auth mode | `bearer` | `.env` 中 `BOSS_RAG_RAG_AUTH_MODE=bearer` |
| CDP Chrome | `http://localhost:9222` | 当前可连接，但 chat page 预检未通过 |
| Resume send switch | enabled | `.env` 中 `BOSS_RAG_SEND_ENABLED=true` |
| Boss live auth | failed | `boss status --live -> AUTH_EXPIRED` |
| Boss chat preflight | failed | `/api/agent/health -> preflightStatus=chat_login_redirect` |

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

Boss 主动消息全自动链路是：

```text
Boss inbound message
  -> boss agent watcher-run --loop --ensure-chat-page or frontend watcher interval
  -> ensure_candidate_chat_page_via_cdp(...)
  -> _CliWatcherMessageSyncer.sync_messages(...)
  -> BossPassiveWatcher.run_once(live_sync=True)
  -> BossRagReplyService.create_draft_for_message(...)
  -> run_auto_reply_graph(...)
  -> _CliWatcherDelivery.send(...)
  -> execute_chat_reply(...)
```

这个链路只有在显式配置打开时才会发送真实消息：

- `boss_rag_allow_message_read=true`
- `boss_rag_send_enabled=true`
- `boss_rag_watcher_enabled=true`
- `boss_rag_watcher_dry_run=false`
- `boss_rag_watcher_live_sync=true`
- `--ensure-chat-page` 或前端 watcher console 的 `ensureChatPage=true`

本阶段最重要的新边界是：

- `/api/agent/ask` 负责生成回答，并且在 `auto_send_resume=true` 且问题是发简历请求时尝试自动发送。
- `/api/agent/send` 负责把已经生成的 draft 发送到 Boss。
- 真正发送必须有 `security_id`。
- 现在“浏览器发送通道可用”不再等价于“Boss 真实发送可用”。
- 新的 source of truth 是：
  - `browserChannel.transportAvailable`
  - `browserChannel.chatPageReachable`
  - `browserChannel.preflightStatus`
- `run_auto_reply_graph(...)` 只做状态编排和动作决策，不直接访问 Boss 页面。
- 真实 Boss 读写仍然只通过 Bridge/CDP channel 和 CLI adapter 进入。
- Frontend watcher console 的 running 状态会周期性触发 `POST /api/agent/watcher/run { liveSync: true }`。
- Bridge/CDP 不可用、`ACCOUNT_RISK`、`AUTH_EXPIRED`、缺少 `security_id` 或空草稿时，全自动链路只写 audit，不发送。

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
- `security_id` 现在会在前端通过以下顺序自动解析：
  - 手工输入值
  - 当前选中的对话目标
  - 最近 Boss 目标里的第一个可用 `security_id`

当前状态：

- 自动发送逻辑已经接上。
- `missing_security_id` 已经不是当前主阻塞。
- 当前真正的阻塞是 chat page 预检失败，导致真实发送在前置检查阶段就被拦下。

### Browser / Delivery Fail-Fast

已完成：

- CDP / Bridge 不可用时，前端不会再假装“发送中...”。
- `/api/agent/send` 现在会在真正发之前检查浏览器发送通道。
- `scripts/stack_readiness.py` 已经默认走 `boss status --live`，不再把“本地 session 文件里还有 cookie”误判成 ready。
- `demo/interview-simulator` 的 health/send 预检已经升级为：
  - 不是只看 `http://localhost:9222/json/version`
  - 而是用临时 CDP tab 实际探测 `https://www.zhipin.com/web/geek/chat`

当前 `/api/agent/health` 的关键信号是：

```json
{
  "browserChannel": {
    "available": false,
    "transportAvailable": true,
    "chatPageReachable": false,
    "preflightStatus": "chat_login_redirect",
    "redirectUrl": "https://www.zhipin.com/web/user/"
  }
}
```

### CDP Session Safety

已完成：

- 复用用户现有 CDP Chrome context 时，不再把本地 `session.enc` 里的旧 Boss cookies 回灌进去。
- 这修掉了一个真实 bug：之前确实可能用旧 cookie 污染 live Chrome context。
- `login_via_cdp()` 已补上和 `login_via_browser()` 一样的 `_POST_LOGIN_WAIT`，避免刚检测到 `wt2` 就过早结束登录流程。

这意味着：

- 当前如果又出现 `/web/geek/chat -> /web/user/`，不应该再默认怀疑“是 agent 又把 cookie 清了”。
- 更应该先看这份 9222 profile 的 Boss 候选人聊天前置态是否真的完成。

### Resignation Question

已完成：

- `为什么离职？` 会识别为 `resignation_status`。
- 之前该意图属于敏感类，本地策略返回空字符串，导致前端看起来“没有响应”。
- 现在会返回保守的候选人回答，强调寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。

### Frontend Simulator

已完成：

- 前端 `Agent 问题输入` 能显示 Agent 最终回答。
- 发简历问题前端不再因为没先手工选中目标就卡在 `missing_security_id`。
- 前端会额外显示一行 `Boss 发送预检`，用于提示当前是否真的能进入候选人聊天页发送链路。
- `发送到 Boss` 按钮仍然复用 `/api/agent/send`，用于手动发送当前 draft。

## Verification

### Automated Tests

本阶段额外验证过的 focused tests：

```bash
pytest tests/test_auth_browser.py tests/test_browser_client.py tests/test_api_client_methods.py tests/test_stack_readiness.py
```

当前结果：

```text
71 passed in 30.33s
```

### Build Regression

已跑过：

```bash
cd demo/interview-simulator
npm run build
```

当前结果：

```text
vite build passed
```

### Health / Readiness Regression

已通过本地 health/readiness 验证：

```bash
curl http://127.0.0.1:5175/api/agent/health
python scripts/stack_readiness.py --pretty
```

当前结果：

- `api/agent/health`：`browserChannel.preflightStatus=chat_login_redirect`
- `stack_readiness.py`：`all_ready=false`
- 失败点明确为：
  - `boss_auth -> AUTH_EXPIRED`
  - `browserChannel.available -> false`

### Browser Regression

已通过 CDP 探针确认：

- 访问站点首页时，当前 9222 profile 仍然能打开 Boss 普通页面。
- 访问 `https://www.zhipin.com/web/geek/chat` 时，前端脚本会主动把页面跳转到 `https://www.zhipin.com/web/user/`。
- 这说明当前问题不是单纯的“CDP 端口未启动”，也不是“没有 `security_id`”，而是 **候选人聊天路由本身的前置态不满足**。

## Current File Changes

当前这批阶段性改动主要集中在：

| File | Purpose |
| --- | --- |
| `demo/interview-simulator/src/App.jsx` | 前端显示 Boss 发送预检状态，并继续保留 `security_id` 自动兜底 |
| `demo/interview-simulator/vite.config.mjs` | health/send 改成真实 chat page preflight，不再只看 CDP 端口 |
| `src/boss_agent_cli/api/browser_client.py` | 复用 CDP context 时不再回灌旧 cookie |
| `src/boss_agent_cli/api/client.py` | 候选人聊天页跳登录时返回明确 `boss_chat_login_required` 语义 |
| `src/boss_agent_cli/auth/browser.py` | `login_via_cdp()` 增加登录完成后的稳定等待 |
| `scripts/stack_readiness.py` | 默认走 `boss status --live`，把 live auth 作为 readiness gate |
| `tests/test_auth_browser.py` | 覆盖 CDP 登录等待与 `_sync_playwright()` 测试桩 |
| `tests/test_browser_client.py` | 覆盖“复用用户 context 时不回灌旧 cookie”回归 |
| `tests/test_api_client_methods.py` | 覆盖聊天页被重定向到登录页时的明确错误 |
| `tests/test_stack_readiness.py` | 覆盖 live readiness 默认行为 |

## Open Boundaries

### Real Boss Delivery

尚未完成：

- 使用真实 Boss 会话 `security_id` 发出一条消息。
- 使用真实 Boss 会话 `security_id` 调用 `client.send_resume(security_id)` 并确认 Boss 页面实际显示在线简历已发出。

当前真实阻塞条件：

```text
boss status --live -> AUTH_EXPIRED
/api/agent/health -> browserChannel.preflightStatus = chat_login_redirect
```

因此，当前还不能把失败归因于：

- `security_id` 缺失
- CDP 端口未启动
- 前端一直假装发送中

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

### Step 1: Re-verify the Actual 9222 Profile

现在必须确认你登录的是不是当前 agent 真正在用的这份 CDP profile：

```text
--user-data-dir=/home/reggie/.cache/boss-agent-cdp-profile
```

因为当前 demo / CLI / preflight 都是基于这份 profile 读到的状态。

验收标准不是“首页能打开”或“cookie 里还有 wt2/stoken”，而是：

```text
curl http://127.0.0.1:5175/api/agent/health
```

返回：

```json
{
  "browserChannel": {
    "available": true,
    "preflightStatus": "ready",
    "chatPageReachable": true
  }
}
```

### Step 2: Re-run Resume Send Smoke

一旦 preflight 变成 `ready`，就在前端输入：

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

### Step 3: If Preflight Still Redirects, Continue Chat-Route Root Cause Analysis

如果重新走当前 9222 profile 的登录后，`preflightStatus` 仍然是：

```text
chat_login_redirect
```

那下一步就不是前端问题，而要继续查：

- Boss 候选人聊天路由是不是新增了额外前置校验
- `login_via_cdp()` 当前拿到的 cookie / stoken 是否仍不够
- 这份 profile 是否还缺少候选人聊天页依赖的本地状态 / 路由状态

### Step 4: Decide Whether to Support Local PDF Attachment

如果目标必须是发送本地 PDF：

```text
/home/reggie/vscode_folder/BOSS_AGENT/孙瑞杰的简历.pdf
```

那需要新接一条 Boss 页面附件上传交互，不能复用当前 `client.send_resume(security_id)`。

建议先完成在线简历发送验收，再决定是否追加本地 PDF 附件路径。

## Stage Exit Criteria

当前阶段退出条件是：

- `api/agent/health` 返回：
  - `browserChannel.available=true`
  - `browserChannel.preflightStatus=ready`
  - `browserChannel.chatPageReachable=true`
- `boss status --live` 不再返回 `AUTH_EXPIRED`
- 前端选中真实 `security_id` 后，`麻烦发一下简历` 能真实发送 Boss 消息
- `delivery.status=sent`
- `message_sent=true`
- `resume_sent=true`
- Boss 页面实际可见在线简历发送成功
- `为什么离职？`、`现在是在职吗？`、`什么时候方便面试？` 在前端均能返回非空安全回答
- 相关 focused tests 保持通过

满足以上条件后，项目可以进入：

**Phase 4: Live Boss Delivery Verified**

也就是从“本地模拟器联调完成”进入“真实 Boss 场景可用”的阶段。
