# PydanticAI Adapter (`pydantic-ai`)

This document records the configuration, versioning, default prompt settings, and timeout controls for the PydanticAI adapter (`pydantic-ai`), satisfying S13.2, S13.4, and E44 specifications.

## 1. Framework Version and Overview

- **Package**: `pydantic-ai`
- **Installed Version**: `2.38.0` (pinned in `uv.lock`)
- **Module imports**:
  - `from pydantic_ai import Agent`
  - `from pydantic_ai.mcp import MCPToolset`
  - `from fastmcp.client.transports.stdio import StdioTransport`
  - `from pydantic_ai.models.openai import OpenAIChatModel`
  - `from pydantic_ai.providers.openai import OpenAIProvider`
- **Adapter identifier**: `pydantic-ai` (`pydantic-ai:<model>`)
- **Integration architecture**:
  - MCP Client: `pydantic_ai.mcp.MCPToolset` with `fastmcp.client.transports.stdio.StdioTransport` (per S13.4).
  - Agent: `pydantic_ai.Agent(model=model, toolsets=toolsets)`.
  - Loop Runner: `agent.run(task.prompt, usage_limits=UsageLimits(request_limit=task.max_steps))`.

## 2. Default System Prompt Excerpt

Per S13.4:
> The adapter must use the framework's default agent construction, default system prompt, and default error handling, passing only the task prompt, model, and MCP servers. The adapter must not modify framework behaviors for score gaming.

In `pydantic-ai` 2.38.0, the default instructions and system prompt parameters on `Agent` are:

```python
instructions: AgentInstructions[AgentDepsT] = None
system_prompt: str | Sequence[str] = ()
```

When `instructions=None` and `system_prompt=()`, the framework does not inject any custom system persona or verification contract. The prompt presented to the LLM consists solely of the user prompt and the tool schemas published by the active `MCPToolset` instances.

The adapter strictly leaves `instructions=None` and `system_prompt=()`, ensuring full fidelity to the native framework loop.

## 3. Timeout and Lifecycle Settings

- **MCP Client Session Timeout**: `read_timeout = 20.0, init_timeout = 20.0`.
  - Configured on `MCPToolset(transport, read_timeout=20.0, init_timeout=20.0)` to enforce the S13.3 single-tool 20-second timeout.
- **Turn Limit**: `request_limit = task.max_steps` (configured via `UsageLimits(request_limit=task.max_steps)`).
  - If the agent exceeds `request_limit`, PydanticAI raises `pydantic_ai.exceptions.UsageLimitExceeded`. Per S13.3, the adapter catches this exception, returns `final_answer = ""` with `steps = task.max_steps`, and yields a `NO_ANSWER` outcome without raising an infrastructure error.
- **Wall-clock Timeout**: Enforced by `runner.episode.run_episode` via `asyncio.wait_for(adapter.run(task), timeout=task.timeout_s)`.
- **Server Lifecycle**: Managed via `contextlib.AsyncExitStack()`, ensuring all stdio MCP client connections are entered with `await stack.enter_async_context(toolset)` and gracefully terminated with `toolset.__aexit__()` upon run completion or failure.

## 4. Model Routing & Pricing

The adapter routes model specifications (`<provider>/<model>`):
- `openrouter/<vendor>/<model>`: uses OpenRouter API (`https://openrouter.ai/api/v1`) via `OpenAIProvider` with `OPENROUTER_API_KEY`.
- `openai/<model>`: standard OpenAI API via `OpenAIProvider` with `OPENAI_API_KEY`.
- `compat/<model>`: custom compatibility endpoint via `SKEPTIC_COMPAT_BASE_URL` and `SKEPTIC_COMPAT_API_KEY`.
- `fake/<script>`: local `FakeLLM` mock using `OpenAIProvider(openai_client=fake_client)` for deterministic evaluations and testing without network calls.
