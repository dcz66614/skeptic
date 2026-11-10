# OpenAI Agents SDK 适配器（`openai-agents`）

本文记录 OpenAI Agents SDK 适配器（`openai-agents`）的配置、版本、默认提示词和超时，对应 S13.2、S13.4 和 E42。

## 1. 框架版本

- **包**：`openai-agents`
- **已安装版本**：`0.24.0`（锁在 `uv.lock`）
- **导入**：`import agents`
- **适配器 id**：`openai-agents`（`openai-agents:<模型>`）
- **接入结构**：
  - MCP 客户端：`agents.mcp.server.MCPServerStdio`（S13.4）。
  - 智能体：`agents.Agent(name="openai_agent", model=model, mcp_servers=mcp_servers, model_settings=model_settings)`。
  - 循环：`agents.Runner.run(agent, input=task.prompt, max_turns=task.max_steps)`。

## 2. 默认系统提示词

按 S13.4，适配器使用框架默认的智能体构造、默认系统提示词和默认错误处理，只传入任务 prompt、模型和 MCP 服务器。

`openai-agents` 0.24.0 里，`agents.Agent` 的默认值是：

```python
instructions: str | Callable[...] | None = None
prompt: Prompt | DynamicPromptFunction | None = None
```

`instructions=None` 且 `prompt=None` 时，框架不注入自定义系统指令、人设或核对契约。送给模型的内容就是用户输入（`task.prompt`）和当前 `MCPServerStdio` 公布的函数 schema。适配器保持这两个参数为 `None`。

## 3. 超时与生命周期

- **MCP 会话超时**：`client_session_timeout_seconds = 20.0`，加在 `MCPServerStdio` 上，对应 S13.3 的单次工具 20 秒超时。
- **回合上限**：`max_turns = task.max_steps`（场景限制，例如 12）。超出时框架抛出 `agents.exceptions.MaxTurnsExceeded`。适配器接住后返回空的 `final_answer`，`steps = task.max_steps`，结局为 `NO_ANSWER`，不把它当成基础设施错误。
- **墙钟超时**：由 `runner.episode.run_episode` 用 `asyncio.wait_for(adapter.run(task), timeout=task.timeout_s)` 执行。
- **服务器生命周期**：`contextlib.AsyncExitStack()`。`server.connect()` 启动，结束或失败时 `server.cleanup()`。

## 4. 模型路由与计价

- `openrouter/<厂商>/<模型>`：OpenRouter，`ModelSettings` 里带 `extra_body={"usage": {"include": True}}`，用来读取供应商报告的费用。
- `openai/<模型>`：OpenAI API。
- `compat/<模型>`：`SKEPTIC_COMPAT_BASE_URL` 和 `SKEPTIC_COMPAT_API_KEY`。
- `fake/<脚本>`：本地 FakeLLM，不访问网络。
