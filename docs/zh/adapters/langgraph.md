# LangGraph 适配器（`langgraph`）

本文记录 LangGraph 适配器（`langgraph`）的配置、版本、默认提示词和超时，对应 S13.2、S13.4 和 E43。

## 1. 框架版本

- **包**：
  - `langgraph`：`1.2.18`（锁在 `uv.lock`）
  - `langchain-mcp-adapters`：`0.3.1`（锁在 `uv.lock`）
  - `langchain-openai`：`1.7.3`（锁在 `uv.lock`）
- **导入**：
  - `from langgraph.prebuilt import create_react_agent`
  - `from langchain_mcp_adapters.client import MultiServerMCPClient`
  - `from langchain_openai import ChatOpenAI`
- **适配器 id**：`langgraph`（`langgraph:<模型>`）
- **接入结构**：
  - MCP 客户端：`MultiServerMCPClient`（S13.4）。
  - 图：`create_react_agent(model=llm, tools=tools)`。
  - 循环：`agent.ainvoke({"messages": [{"role": "user", "content": task.prompt}]}, config={"recursion_limit": 2 * task.max_steps + 1})`。

## 2. 默认系统提示词

按 S13.4，适配器使用框架默认构造、默认系统提示词和默认错误处理，只传入任务 prompt、模型和 MCP 服务器。

`create_react_agent` 的 `prompt` 默认是 `None`。为 `None` 时，预置 ReAct 智能体不注入自定义系统指令、人设或核对契约。送给模型的是用户消息和 MCP 客户端提供的工具定义。适配器保持 `prompt=None`。

## 3. 超时与生命周期

- **MCP 会话超时**：`read_timeout_seconds = 20.0`，通过每个 `StdioConnection` 的 `session_kwargs` 设置，对应 S13.3 的单次工具 20 秒超时。
- **递归上限**：`recursion_limit = 2 * task.max_steps + 1`。LangGraph 的 ReAct 图每回合是一个 agent 节点加一个 tools 节点。超出时抛出 `langgraph.errors.GraphRecursionError`。适配器接住后返回空的 `final_answer`，`steps = task.max_steps`，结局为 `NO_ANSWER`。
- **墙钟超时**：由 `runner.episode.run_episode` 用 `asyncio.wait_for` 执行。
- **服务器生命周期**：由 `MultiServerMCPClient` 按会话管理，为工具调用启动 stdio 子进程，结束时关掉。

## 4. 模型路由与计价

- `openrouter/<厂商>/<模型>`：OpenRouter，`ChatOpenAI` 上带 `extra_body={"usage": {"include": True}}`。
- `openai/<模型>`：经 `ChatOpenAI` 走 OpenAI API。
- `compat/<模型>`：`SKEPTIC_COMPAT_BASE_URL` 和 `SKEPTIC_COMPAT_API_KEY`。
- `fake/<脚本>`：本地 FakeLLM，不访问网络。
