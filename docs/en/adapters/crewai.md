# CrewAI Adapter (`crewai`)

This document records the configuration, versioning, default prompt settings, and timeout controls for the CrewAI adapter (`crewai`), satisfying S13.2, S13.4, E44, and ADR-0006 specifications.

## 1. Framework Version and Overview

- **Packages**:
  - `crewai`: `1.6.1` (pinned in `uv.lock`)
  - `mcpadapt`: `0.1.20` (pinned in `uv.lock`, per ADR-0006)
- **Module imports**:
  - `from crewai import Agent, Task, Crew`
  - `from mcpadapt.core import MCPAdapt`
  - `from mcpadapt.crewai_adapter import CrewAIAdapter`
- **Adapter identifier**: `crewai` (`crewai:<model>`)
- **Integration architecture**:
  - MCP Client: `mcpadapt.core.MCPAdapt` with `mcpadapt.crewai_adapter.CrewAIAdapter` (per ADR-0006, strictly without `crewai-tools[mcp]` or `pymupdf`).
  - Agent & Task: `crewai.Agent(role="Assistant", goal="Complete the user's task", backstory="You are a helpful assistant.", llm=llm, tools=tools, max_iter=task.max_steps, verbose=False)` and `crewai.Task(description=task.prompt, expected_output="Final answer to the user's task.", agent=agent)`.
  - Loop Runner: `crew = Crew(agents=[agent], tasks=[task_obj], verbose=False)` executed via `crew.kickoff()`.

## 2. Default System Prompt Excerpt

Per S13.4:
> The adapter must use the framework's default agent construction, default system prompt, and default error handling, passing only the task prompt, model, and MCP servers. The adapter must not modify framework behaviors for score gaming.

In CrewAI 1.6.1, the framework constructs its system prompt using role-playing components and ReAct formatting slices (`crewai.utilities.prompts.Prompts`):

```python
system_template: str | None = None
prompt_template: str | None = None
response_template: str | None = None
use_system_prompt: bool = True
```

The default prompt specifies the ReAct loop contract (`Thought: ... Action: ... Action Input: ... Observation: ... Final Answer: ...`). The adapter strictly keeps `system_template=None`, `prompt_template=None`, and `response_template=None`, leaving the framework's default ReAct prompt and behavior untouched.

## 3. Timeout and Lifecycle Settings

- **MCP Client Session Timeout**: `client_session_timeout_seconds = 20.0`.
  - Configured on `MCPAdapt(..., client_session_timeout_seconds=20.0)` to enforce the S13.3 single-tool 20-second timeout.
- **Turn Limit**: `max_iter = task.max_steps` (defaults to scenario limits, e.g. 12 turns).
  - If the agent loop exceeds `max_iter`, the framework forces completion or triggers iteration fallback. Per S13.3, if `iterations >= task.max_steps` or `steps > task.max_steps`, the adapter returns `final_answer = ""` with `steps = task.max_steps`, yielding a `NO_ANSWER` outcome without raising an infrastructure error.
- **Wall-clock Timeout**: Enforced by `runner.episode.run_episode` via `asyncio.wait_for(adapter.run(task), timeout=task.timeout_s)`.
- **Server Lifecycle**: Managed synchronously via `with MCPAdapt(...) as mcp_tools:`, ensuring all stdio subprocesses and helper threads are properly stopped and closed with `MCPAdapt.close()` upon task completion or failure.
- **Telemetry & Tracing**: All interactive tracing prompts and background telemetry exporters are disabled via environment variables (`OTEL_SDK_DISABLED=true`, `CREWAI_DISABLE_TELEMETRY=true`, `CREWAI_DISABLE_TRACKING=true`, `CREWAI_TESTING=true`).

## 4. Model Routing & Pricing

The adapter routes model specifications (`<provider>/<model>`):
- `openrouter/<vendor>/<model>`: uses OpenRouter API (`https://openrouter.ai/api/v1`) via `OpenAICompletion` with `OPENROUTER_API_KEY`.
- `openai/<model>`: standard OpenAI API via `OpenAICompletion` with `OPENAI_API_KEY`.
- `compat/<model>`: custom compatibility endpoint via `SKEPTIC_COMPAT_BASE_URL` and `SKEPTIC_COMPAT_API_KEY`.
- `fake/<script>`: local `FakeLLM` mock using `SkepticCrewAILLM` for deterministic evaluations and testing without network calls.
