# PydanticAI 适配器（`pydantic-ai`）

本文记录 PydanticAI 适配器（`pydantic-ai`）的配置、版本、默认提示词和超时，对应 S13.2、S13.4 和 E44。

## 1. 框架版本

- **包**：`pydantic-ai`
- **已安装版本**：`2.38.0`（锁在 `uv.lock`）
- **导入**：
  - `from pydantic_ai import Agent`
  - `from pydantic_ai.mcp import MCPToolset`
  - `from fastmcp.client.transports.stdio import StdioTransport`
  - `from pydantic_ai.models.openai import OpenAIChatModel`
  - `from pydantic_ai.providers.openai import OpenAIProvider`
- **适配器 id**：`pydantic-ai`（`pydantic-ai:<模型>`）
- **接入结构**：
  - MCP 客户端：`MCPToolset` 加 `StdioTransport`（S13.4）。
  - 智能体：`Agent(model=model, toolsets=toolsets)`。
  - 循环：`agent.run(task.prompt, usage_limits=UsageLimits(request_limit=task.max_steps))`。

## 2. 默认系统提示词

按 S13.4，适配器使用框架默认构造、默认系统提示词和默认错误处理。

`pydantic-ai` 2.38.0 里，`Agent` 的默认值是：

```python
instructions: AgentInstructions[AgentDepsT] = None
system_prompt: str | Sequence[str] = ()
```

`instructions=None` 且 `system_prompt=()` 时，框架不注入自定义人设或核对契约。送给模型的是用户 prompt 和当前 `MCPToolset` 公布的工具 schema。适配器保持这两个默认值。

## 3. 超时与生命周期

- **MCP 会话超时**：`read_timeout = 20.0`，`init_timeout = 20.0`，加在 `MCPToolset` 上，对应 S13.3 的单次工具 20 秒超时。
- **回合上限**：`UsageLimits(request_limit=task.max_steps)`。超出时 PydanticAI 抛出 `pydantic_ai.exceptions.UsageLimitExceeded`。适配器接住后返回空的 `final_answer`，`steps = task.max_steps`，结局为 `NO_ANSWER`。
- **墙钟超时**：由 `runner.episode.run_episode` 用 `asyncio.wait_for` 执行。
- **服务器生命周期**：`contextlib.AsyncExitStack()`。`await stack.enter_async_context(toolset)` 进入连接，结束或失败时 `toolset.__aexit__()`。

## 4. 模型路由与计价

- `openrouter/<厂商>/<模型>`：`https://openrouter.ai/api/v1`，经 `OpenAIProvider`，使用 `OPENROUTER_API_KEY`。
- `openai/<模型>`：经 `OpenAIProvider`，使用 `OPENAI_API_KEY`。
- `compat/<模型>`：`SKEPTIC_COMPAT_BASE_URL` 和 `SKEPTIC_COMPAT_API_KEY`。
- `fake/<脚本>`：本地 FakeLLM，`OpenAIProvider(openai_client=fake_client)`，不访问网络。
