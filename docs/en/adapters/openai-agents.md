# OpenAI Agents SDK Adapter (`openai-agents`)

This document records the configuration, versioning, default prompt settings, and timeout controls for the OpenAI Agents SDK adapter (`openai-agents`), satisfying S13.2, S13.4, and E42 specifications.

## 1. Framework Version and Overview

- **Package**: `openai-agents`
- **Installed Version**: `0.24.0` (pinned in `uv.lock`)
- **Module import**: `import agents`
- **Adapter identifier**: `openai-agents` (`openai-agents:<model>`)
- **Integration architecture**:
  - MCP Client: `agents.mcp.server.MCPServerStdio` (per S13.4).
  - Agent Graph: `agents.Agent(name="openai_agent", model=model, mcp_servers=mcp_servers, model_settings=model_settings)`.
  - Loop Runner: `agents.Runner.run(agent, input=task.prompt, max_turns=task.max_steps)`.

## 2. Default System Prompt Excerpt

Per S13.4:
> The adapter must use the framework's default agent construction, default system prompt, and default error handling, passing only the task prompt, model, and MCP servers. The adapter must not modify framework behaviors for score gaming.

In `openai-agents` 0.24.0, the default instructions and prompt on `agents.Agent` are:

```python
instructions: str | Callable[...] | None = None
prompt: Prompt | DynamicPromptFunction | None = None
```

When `instructions=None` and `prompt=None`, the framework does not inject any custom system instructions, persona, or verification contract. The prompt presented to the LLM consists solely of the user input item (`task.prompt`) and the function schemas published by the active `MCPServerStdio` instances.

The adapter strictly leaves `instructions=None` and `prompt=None`, ensuring full fidelity to the native framework ReAct loop.

## 3. Timeout and Lifecycle Settings

- **MCP Client Session Timeout**: `client_session_timeout_seconds = 20.0`.
  - Configured on `MCPServerStdio(..., client_session_timeout_seconds=20.0)` to enforce the S13.3 single-tool 20-second timeout.
- **Turn Limit**: `max_turns = task.max_steps` (defaults to scenario limits, e.g. 12 turns).
  - If the agent exceeds `max_steps`, the framework raises `agents.exceptions.MaxTurnsExceeded`. Per S13.3, the adapter catches this exception, returns `final_answer = ""` with `steps = task.max_steps`, and yields a `NO_ANSWER` outcome without raising an infrastructure error.
- **Wall-clock Timeout**: Enforced by `runner.episode.run_episode` via `asyncio.wait_for(adapter.run(task), timeout=task.timeout_s)`.
- **Server Lifecycle**: Managed via `contextlib.AsyncExitStack()`, ensuring all stdio subprocesses are initialized with `server.connect()` and gracefully terminated with `server.cleanup()` upon run completion or failure.

## 4. Model Routing & Pricing

The adapter routes model specifications (`<provider>/<model>`):
- `openrouter/<vendor>/<model>`: uses OpenRouter API with `extra_body={"usage": {"include": True}}` in `ModelSettings` to capture provider-reported costs.
- `openai/<model>`: standard OpenAI API.
- `compat/<model>`: custom compatibility endpoint via `SKEPTIC_COMPAT_BASE_URL` and `SKEPTIC_COMPAT_API_KEY`.
- `fake/<script>`: local `FakeLLM` mock without network calls for deterministic evaluations and testing.
