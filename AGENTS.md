# BOSS_AGENT Agent Rules

## Scope

- 本文件作用于整个 `BOSS_AGENT` 仓库；更深层目录的 `AGENTS.md` 可以为该子树追加或覆盖规则。
- 本文件只放 durable rules、边界和协作策略；具体安装、运行、排障步骤应放在 `README.md`、`docs/` 或专门 runbook。
- 默认保持最小必要改动。不要把一次性经验、临时命令或任务过程写进本文件。

## Project Boundaries

- `BOSS_AGENT` 的默认产品边界是本地辅助、只读优先、RAG 草稿、人工批准。真实投递、真实发送消息、交换联系方式、绕过风控或批量触达都不能作为默认自动化路径。
- 涉及 Boss 平台 live 行为时，优先使用低频、只读、用户可理解的探测。遇到 captcha、`ACCOUNT_RISK`、登录异常、非法请求或平台结构漂移时，停止自动化并报告。
- `.env`、本地登录态、cookies、简历、聊天记录和候选人数据都按敏感数据处理。不要在日志、提交信息、文档或最终回复中泄露。
- `approve`、`review`、`copy`、`mark-applied` 这类人工确认工作流可以优化；把 `approve` 等同于真实平台发送是不允许的，除非用户明确要求且代码中已有显式安全 gate。

## Subagent Strategy

- 主 agent 始终拥有最终判断权：确定 scope、分派任务、综合结果、决定是否采用建议、执行最终验证、提交改动并向用户交付。
- 只有当任务确实能降低上下文负担、缩短时间、降低风险或提高验证可信度时才使用 subagent。不要为了形式感创建 subagent。
- 优先用 `read-only` subagent 做代码地图、依赖追踪、日志梳理、风险识别和方案比较；在信息足够后再交给 writer。
- `writer` subagent 只负责一个边界清晰的实现切片，并必须有明确 `allowed_paths`、禁止触碰的文件、验证命令和停止条件。
- `review` subagent 默认只读，负责像代码审查一样找 bug、回归、缺失测试、安全/合规风险和范围漂移，不负责重写实现。
- 对 live 平台、认证、数据隐私、发送/投递、安全 gate、跨模块重构或共享配置的改动，默认至少需要一个独立 review；纯文档小改可由主 agent 自审。

## Read-only Agent Contract

- 只能读取文件、搜索代码、查看 diff、运行非破坏性检查或只读测试；不能编辑、格式化、stage、commit、reset、删除文件或改运行时状态。
- 不能执行真实平台写操作，不能触发投递、消息发送、联系方式交换、批量触达或风控绕过尝试。
- 输出必须包含：结论、证据路径、相关文件/函数、风险点、未确认假设和建议下一步。
- 如果发现需要写入才能继续，停止并向主 agent 报告，不要自行升级为 writer。

## Writer Agent Contract

- 开始前必须确认当前 git 状态、目标文件 ownership、已有 live agents 和 `allowed_paths`。如果可能和其他 writer 重叠，先协调。
- 只能修改分配范围内的文件；不得顺手重构、清理、格式化或修复相邻问题。
- 必须保护用户或其他 agent 的未提交改动；不得使用 `git reset --hard`、`git checkout --`、批量覆盖或不加区分的清理命令。
- 代码改动优先遵循现有架构、命名、测试风格和 public API；保持高内聚、低耦合，避免一次性大抽象。
- 完成后报告实际改动、验证命令、未验证风险和需要主 agent 决策的点。writer 默认不提交，除非主 agent 明确授权。

## Review Agent Contract

- 默认以 read-only 方式审查当前 diff 或指定文件，不修改代码。
- Findings 优先，按严重程度排序；每条 finding 要说明影响、证据位置和可执行修复方向。
- 重点审查行为回归、缺失测试、敏感数据泄露、平台合规边界、auth/session 逻辑、RAG contract、错误处理和并发/状态一致性。
- 不因个人风格、命名偏好或无风险格式问题阻塞交付；这类建议只能放在次要备注。
- 如果没有发现问题，要明确说明剩余测试缺口或无法覆盖的风险。

## Handoff Protocol

- 分派 subagent 时必须写清楚：角色、目标、允许文件、禁止文件、是否可写、是否允许 live probe、验证命令、输出格式和停止条件。
- 对 read-heavy 任务，先给 read-only agent 一个具体问题，不要让多个 explorer 同时搜同一证据。
- 对 write 任务，一次只允许一个 writer 拥有同一文件或紧耦合文件组。共享 worktree 中任何 writer 都要避免并发编辑同一 ownership 区域。
- subagent 的结论只是输入，不是最终答案。主 agent 要复核关键证据，必要时自己运行最小验证。
- 如果 subagent 报告 blocker，主 agent 先确认 blocker 是否真实、是否可绕过、是否需要用户决策，再对外汇报。

## Validation And Delivery

- 行为改动必须运行最近、最能证明该改动的测试；无法验证时必须说明原因和剩余风险。
- 文档-only 改动至少运行 `git diff --check -- <changed-files>`，确保没有尾随空格或补丁格式问题。
- 任务改动完成后，主 agent 只 stage 与当前任务直接相关的文件，并在最终回复前提交；不得用 `git add .`。
- 最终回复应说明改了什么、验证了什么、是否提交、还有什么风险或 blocker。
