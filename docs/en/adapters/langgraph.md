# LangGraph Adapter (`langgraph`)

This document records the configuration, versioning, default prompt settings, and timeout controls for the LangGraph adapter (`langgraph`), satisfying S13.2, S13.4, and E43 specifications.

## 1. Framework Version and Overview

- **Packages**:
  - `langgraph`: `1.2.18` (pinned in `uv.lock`)
  - `langchain-mcp-adapters`: `0.3.1` (pinned in `uv.lock`)
  - `langchain-openai`: `1.7.3` (pinned in `uv.lock`)
- **Module imports**:
  - `from langgraph.prebuilt import create_react_agent`
  - `from langchain_mcp_adapters.client import MultiServerMCPClient`
  - `from langchain_openai import ChatOpenAI`
- **Adapter identifier**: `langgraph` (`langgraph:<model>`)
- **Integration architecture**:
  - MCP Client: `langchain_mcp_adapters.client.MultiServerMCPClient` (per S13.4).
  - Agent Graph: `langgraph.prebuilt.create_react_agent(model=llm, tools=tools)`.
  - Loop Runner: `agent.ainvoke({"messages": [{"role": "user", "content": task.prompt}]}, config={"recursion_limit": 2 * task.max_steps + 1})`.

## 2. Default System Prompt Excerpt

Per S13.4:
> The adapter must use the framework's default agent construction, default system prompt, and default error handling, passing only the task prompt, model, and MCP servers. The adapter must not modify framework behaviors for score gaming.

In `langgraph.prebuilt.create_react_agent`, the prompt parameter signature is:

```python
prompt: Union[
    SystemMessage,
    str,
    Callable[[StateSchema], PromptValue | str | Sequence[BaseMessage]],
    Runnable[StateSchema, PromptValue | str | Sequence[BaseMessage]],
    None,
] = None
```

When `prompt=None`, the prebuilt ReAct agent does not inject any custom system instructions, persona, or verification contract. The prompt presented to the LLM consists solely of the user input messages (`{"messages": [{"role": "user", "content": task.prompt}]}`) and the tool definitions provided by the MCP client.

The adapter strictly leaves `prompt=None`, ensuring full fidelity to the native framework ReAct loop.

## 3. Timeout and Lifecycle Settings

- **MCP Client Session Timeout**: `read_timeout_seconds = 20.0`.
  - Configured via `session_kwargs={"read_timeout_seconds": 20.0}` on each `StdioConnection` in `MultiServerMCPClient` to enforce the S13.3 single-tool 20-second timeout.
- **Turn and Recursion Limit**: `recursion_limit = 2 * task.max_steps + 1`.
  - In LangGraph's ReAct state graph, each turn executes an agent node followed by a tools node. The recursion limit corresponds to `2 * max_steps + 1` total node steps.
  - If the agent exceeds this limit, LangGraph raises `langgraph.errors.GraphRecursionError`. Per S13.3, the adapter catches this exception, returns `final_answer = ""` with `steps = task.max_steps`, and yields a `NO_ANSWER` outcome without raising an infrastructure error.
- **Wall-clock Timeout**: Enforced by `runner.episode.run_episode` via `asyncio.wait_for(adapter.run(task), timeout=task.timeout_s)`.
- **Server Lifecycle**: Managed per session by `MultiServerMCPClient`, which spawns stdio subprocesses for each tool invocation and terminates them cleanly upon completion.

## 4. Model Routing & Pricing

The adapter routes model specifications (`<provider>/<model>`):
- `openrouter/<vendor>/<model>`: uses OpenRouter API with `extra_body={"usage": {"include": True}}` on `ChatOpenAI` to capture provider-reported costs.
- `openai/<model>`: standard OpenAI API via `ChatOpenAI`.
- `compat/<model>`: custom compatibility endpoint via `SKEPTIC_COMPAT_BASE_URL` and `SKEPTIC_COMPAT_API_KEY`.
- `fake/<script>`: local `FakeLLM` mock without network calls for deterministic evaluations and testing.
