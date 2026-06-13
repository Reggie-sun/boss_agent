# LangChain MCP Integration Example

适用于想把 `boss-mcp` 直接挂到 LangChain agent 或 LangGraph graph 上的场景。这里走的是 MCP 协议路径，不是 `boss schema --format openai-tools` 的直调路径。

## Good fit when

- 你已经在用 LangChain 或 LangGraph，希望直接复用 `MultiServerMCPClient`
- 你希望 Agent 自动发现 `boss_rag_*`、`boss_search`、`boss_detail` 这类工具，而不是手写工具 schema
- 你希望把低风险 CLI 能力和 Boss RAG workflow 一起暴露给同一个 agent

## Minimal integration

官方推荐的最小形态是：

1. 用 `MultiServerMCPClient` 连接 `boss-mcp`
2. `tools = await client.get_tools()`
3. 把这组工具传给 `create_agent(...)`

仓库里已经放了两份可直接复制的示例：

- LangChain agent: [examples/langchain_mcp_agent.py](../../examples/langchain_mcp_agent.py)
- LangGraph graph: [examples/langgraph_mcp_agent.py](../../examples/langgraph_mcp_agent.py)

先安装依赖：

```bash
pip install -e ".[langchain]"
export BOSS_LANGCHAIN_API_KEY=...
export BOSS_LANGCHAIN_MODEL=gpt-5
export BOSS_MCP_HTTP_URL=http://127.0.0.1:8766/mcp
```

如果你接的是 OpenAI-compatible 服务，也可以额外设置：

```bash
export BOSS_LANGCHAIN_BASE_URL=https://your-provider.example/v1
```

最小运行：

```bash
python examples/langchain_mcp_agent.py "先执行 boss status，再同步最近消息并生成回复草稿"
```

LangGraph 版本：

```bash
python examples/langgraph_mcp_agent.py "先执行 boss status，再同步最近消息并生成回复草稿"
```

如果你已经单独启动了 HTTP MCP server，示例会优先直连 `BOSS_MCP_HTTP_URL`。

当前这台机器上已经验证通过的地址是：

```text
http://127.0.0.1:8766/mcp
```

如果 `BOSS_MCP_HTTP_URL` 没有设置，示例脚本才会退回到 repo-local MCP server：

```text
python -m boss_agent_cli.mcp_server
```

因此它会直接发现当前源码里的工具面，包括：

- `boss schema`
- `boss status`
- `boss search`
- `boss detail`
- `boss shortlist_*`
- `boss_rag_init`
- `boss_rag_sync_messages`
- `boss_rag_draft`
- `boss_rag_review`
- `boss_rag_approve`

建议给模型的工作规则：

```text
1. 首轮先用 boss schema 或直接读取 MCP tools list 做能力发现
2. 进入求职链路前先跑 boss status
3. 搜索链路使用 boss search -> boss detail -> boss shortlist add
4. 回复草稿链路优先使用 boss_rag_sync_messages -> boss_rag_draft -> boss_rag_review
5. 遇到 ok=false 时，根据 error.code 和 error.recovery_action 恢复
```

## LangGraph stateful graph

如果你要在 LangGraph 节点里用，同样保留这套 MCP client 初始化，只是把 `agent.ainvoke(...)` 放进图节点即可。

仓库里的 `examples/langgraph_mcp_agent.py` 做了两件事：

1. 用 `MultiServerMCPClient` 加载 `boss-mcp` 工具
2. 用 `StateGraph + InMemorySaver` 编译一个可带 `thread_id` 的最小图

它适合拿来做两类起点：

- 想先保留 LangChain agent 的工具调用体验，但把它放进 LangGraph 节点
- 后续准备接长期记忆、人工审批节点、或多节点规划 / 执行图

可选线程 ID：

```bash
export BOSS_LANGGRAPH_THREAD_ID=boss-rag-demo
python examples/langgraph_mcp_agent.py "先执行 boss status，再同步最近消息并生成回复草稿"
```

## Recovery flow

推荐恢复顺序：

```bash
boss doctor
boss status
boss login
boss search "Golang" --city 广州
```

LangChain / MCP 侧常见恢复分支：

- `AUTH_REQUIRED` / `AUTH_EXPIRED`：先恢复 `boss login`，再重试工具
- `INVALID_PARAM`：返回 `boss schema` 或重新查看 tool schema，不要猜参数
- `COMPLIANCE_BLOCKED`：不要自动降级为敏感操作，改为提示用户回到平台官网手动完成
- `RATE_LIMITED`：做退避，不要继续推进敏感链路

## Notes

- `boss_rag_sync_messages` 仍受 `boss_rag_allow_message_read=true` 约束；Agent 发现工具不等于默认能读消息
- `MultiServerMCPClient` 默认是 stateless tool invocation；如果后续需要显式 session 生命周期，再切到 LangChain 文档里的 stateful session 用法
- `examples/langgraph_mcp_agent.py` 当前使用 `InMemorySaver`，适合 demo / 本地开发；如果要长期持久化 thread state，再替换为你自己的 checkpointer
- 如果你不想经过 MCP，而是直接把 tool schema 喂给 OpenAI / Claude SDK，请改看 [python-sdk.md](python-sdk.md)
