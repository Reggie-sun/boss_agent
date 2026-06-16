# BOSS_AGENT Auto Greet Session Memory

## Scope

适用于 `/home/reggie/vscode_folder/BOSS_AGENT` 的 Boss 自动开聊、HR simulator 前端、`batch-greet` CLI、Vite bridge 和 RAG 被动 watcher 邻近工作。

## Session Facts

- 本 session 已把 HR simulator 的 `Boss 自动开聊` 接到真实 CLI 能力：关键词、城市、薪资、经验、学历、行业、公司规模、融资阶段、职位类型、福利关键词、数量。
- 关键提交：
  - `513edde feat: expose boss search filters in simulator`
  - `5113914 feat: raise boss greet limit to 150`
  - `1d083fc fix: fail boss auto greet with no candidates`
- `batch-greet` 现在最大上限是 `150`，默认每条成功开聊后的随机间隔是 `batch_greet_delay=[1.0, 10.0]`。
- `BOSS_RAG_COMMAND_TIMEOUT_SECONDS=0` 表示前端 bridge 不再设置 `spawnSync` timeout。
- 当前前端 dev server 最近运行在 `http://127.0.0.1:5178/`，因为 `5177` 被占用。

## Durable Lessons

- 不要把 `batch-greet` 的 `0/0` 当成功。真实自动开聊没有候选人时必须返回 `NO_CANDIDATES` recoverable error，让前端显示错误而不是绿色成功。
- 调试 Boss 自动开聊时，先区分三层：`boss search` 是否搜到结果、`batch-greet` 是否筛掉已开聊/不匹配候选、前端是否只是渲染 CLI envelope。
- 福利关键词筛选走 `--welfare`，会逐个查职位详情；它可能导致候选数为 0，应先用“预览”确认搜索结果。
- MCP 的 `boss_batch_greet` 参数映射要保持和 CLI 一致，`limit` 输入最终应转成 CLI 的 `--count`。

## Verification Trail

- `python -m pytest tests/test_greet_detail_extended.py tests/test_greet_extended.py tests/test_schema_contract.py` 通过，最后一次为 `34 passed`。
- `npm run build` 在 `demo/interview-simulator` 通过。
- 空候选复现脚本现在返回 `exit_code=1`、`ok=false`、`error.code=NO_CANDIDATES`。

## Next-Agent Guidance

如果用户说“这是假的”或截图出现“已开聊 0 个，失败 0 个”，优先查 `src/boss_agent_cli/commands/greet.py` 的 `NO_CANDIDATES` 分支是否仍生效，再查前端 `/api/boss/auto-greet` 是否把 CLI `ok=false` 转成错误提示。
