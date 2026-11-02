"""LangGraph Adapter (S13.2, S13.4, E43).

Connects MCP servers via langchain-mcp-adapters MultiServerMCPClient,
configures a prebuilt ReAct agent with ChatOpenAI, and executes turns
using the framework default settings.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import types
import warnings
from typing import Any

# Disable tracing to avoid unauthenticated telemetry export attempts
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

CLIENT_SESSION_TIMEOUT_SECONDS: float = 20.0


def _ensure_mcp_compat() -> None:
    """Install backwards-compatibility shims between langchain-mcp-adapters and mcp 2.3+."""
    import mcp.shared.context

    if not hasattr(mcp.shared.context, "RequestContext"):
        mcp.shared.context.RequestContext = mcp.shared.context.BaseContext  # type: ignore[attr-defined]

    import mcp.shared.dispatcher

    if "mcp.shared.session" not in sys.modules:
        shared_session = types.ModuleType("mcp.shared.session")
        shared_session.ProgressFnT = mcp.shared.dispatcher.ProgressFnT  # type: ignore[attr-defined]
        sys.modules["mcp.shared.session"] = shared_session

    if "mcp.server.fastmcp.tools" not in sys.modules:
        fastmcp_tools = types.ModuleType("mcp.server.fastmcp.tools")
        fastmcp_tools.Tool = object  # type: ignore[attr-defined]
        sys.modules["mcp.server.fastmcp.tools"] = fastmcp_tools

    if "mcp.server.fastmcp.utilities.func_metadata" not in sys.modules:
        fastmcp_meta = types.ModuleType("mcp.server.fastmcp.utilities.func_metadata")
        fastmcp_meta.ArgModelBase = object  # type: ignore[attr-defined]
        fastmcp_meta.FuncMetadata = object  # type: ignore[attr-defined]
        sys.modules["mcp.server.fastmcp.utilities.func_metadata"] = fastmcp_meta

    from mcp import ClientSession
    from mcp import types as mcp_types

    if not hasattr(mcp_types.ListToolsResult, "nextCursor"):
        mcp_types.ListToolsResult.nextCursor = property(  # type: ignore[attr-defined]
            lambda self: self.next_cursor
        )
    if not hasattr(mcp_types.Tool, "inputSchema"):
        mcp_types.Tool.inputSchema = property(  # type: ignore[attr-defined]
            lambda self: self.input_schema
        )
    if not hasattr(mcp_types.CallToolResult, "isError"):
        mcp_types.CallToolResult.isError = property(  # type: ignore[attr-defined]
            lambda self: self.is_error
        )
    if not hasattr(mcp_types.CallToolResult, "structuredContent"):
        mcp_types.CallToolResult.structuredContent = property(  # type: ignore[attr-defined]
            lambda self: self.structured_content
        )
    if not hasattr(mcp_types.ImageContent, "mimeType"):
        mcp_types.ImageContent.mimeType = property(  # type: ignore[attr-defined]
            lambda self: self.mime_type
        )
    if not hasattr(mcp_types.ResourceLink, "mimeType"):
        mcp_types.ResourceLink.mimeType = property(  # type: ignore[attr-defined]
            lambda self: self.mime_type
        )

    orig_list_tools = ClientSession.list_tools
    if getattr(orig_list_tools, "__name__", "") != "_patched_list_tools":

        async def _patched_list_tools(
            self: ClientSession,
            *args: Any,
            cursor: str | None = None,
            params: mcp_types.PaginatedRequestParams | None = None,
            **kwargs: Any,
        ) -> mcp_types.ListToolsResult:
            if cursor is not None and params is None:
                params = mcp_types.PaginatedRequestParams(cursor=cursor)
            return await orig_list_tools(self, *args, params=params, **kwargs)

        ClientSession.list_tools = _patched_list_tools  # type: ignore[method-assign]


# Run compatibility shim before importing langchain_mcp_adapters
_ensure_mcp_compat()

from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402
from langchain_mcp_adapters.sessions import Connection, StdioConnection  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.errors import GraphRecursionError  # noqa: E402
from pydantic import SecretStr  # noqa: E402

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langgraph.prebuilt import create_react_agent

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask, Usage  # noqa: E402
from skeptic_agent.runner.llm import (  # noqa: E402
    calculate_cost,
    create_llm_client,
    resolve_model,
)


def _build_transcript(
    messages: list[BaseMessage],
    fallback_prompt: str,
    final_answer: str,
) -> list[dict[str, Any]]:
    """Convert LangChain messages into standard OpenAI-compatible transcript messages."""
    transcript: list[dict[str, Any]] = []

    for msg in messages:
        msg_type = getattr(msg, "type", "")
        if isinstance(msg, HumanMessage) or msg_type == "human":
            transcript.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage) or msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                transcript.append(
                    {
                        "role": "assistant",
                        "content": str(msg.content) if msg.content else None,
                        "tool_calls": [
                            {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": (
                                        json.dumps(tc.get("args", {}))
                                        if isinstance(tc.get("args"), dict)
                                        else str(tc.get("args", "{}"))
                                    ),
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )
            else:
                transcript.append({"role": "assistant", "content": str(msg.content)})
        elif isinstance(msg, ToolMessage) or msg_type == "tool":
            call_id = getattr(msg, "tool_call_id", "")
            content = msg.content
            if isinstance(content, list):
                parts: list[str] = []
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        parts.append(str(p["text"]))
                    elif isinstance(p, str):
                        parts.append(p)
                    else:
                        parts.append(str(p))
                content_text = "".join(parts) or json.dumps(content)
            elif isinstance(content, dict):
                content_text = json.dumps(content)
            else:
                content_text = str(content)
            transcript.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content_text,
                }
            )

    if not transcript:
        transcript.append({"role": "user", "content": fallback_prompt})

    if final_answer and not any(
        turn.get("role") == "assistant" and turn.get("content") for turn in transcript
    ):
        transcript.append({"role": "assistant", "content": final_answer})

    return transcript


class LangGraphAdapter:
    """Adapter wrapping LangGraph framework satisfying AgentAdapter protocol (S13.2, S13.4)."""

    name: str = "langgraph"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run the LangGraph ReAct agent on the given task."""
        llm_client = create_llm_client(task.model, scenario=task.scenario)
        config = resolve_model(task.model)

        if config.is_fake:
            llm = ChatOpenAI(
                model=config.model_name,
                async_client=llm_client.chat.completions,
                api_key=SecretStr("dummy"),
            )
        else:
            model_kwargs: dict[str, Any] = {
                "model": config.model_name,
                "api_key": SecretStr(config.api_key or "sk-dummy"),
            }
            if config.base_url:
                model_kwargs["base_url"] = config.base_url
            if config.provider == "openrouter":
                model_kwargs["extra_body"] = {"usage": {"include": True}}
            llm = ChatOpenAI(**model_kwargs)

        usage = Usage()
        connections: dict[str, Connection] = {}

        for server_spec in task.servers:
            env = dict(os.environ)
            env.update(task.env)
            env.update(server_spec.env)

            connection: StdioConnection = {
                "transport": "stdio",
                "command": server_spec.command[0],
                "args": server_spec.command[1:],
                "env": env,
                "cwd": str(task.workdir),
                "session_kwargs": {
                    "read_timeout_seconds": CLIENT_SESSION_TIMEOUT_SECONDS,
                },
            }
            connections[server_spec.name] = connection

        mcp_client = MultiServerMCPClient(connections)

        try:
            tools = await mcp_client.get_tools()
        except Exception as exc:
            infra_error = f"Failed to initialize MCP servers: {exc}"
            return AgentRunResult(
                final_answer="",
                usage=usage,
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=infra_error,
            )

        # Framework default agent construction (S13.4): no custom prompts or hooks
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            agent = create_react_agent(
                model=llm,
                tools=tools,
            )

        # In LangGraph ReAct, each turn alternates agent and tools nodes.
        # recursion_limit bounds the total node executions to 2 * max_steps + 1.
        recursion_limit = 2 * task.max_steps + 1
        messages: list[BaseMessage] = []
        final_answer = ""
        steps = 0

        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": task.prompt}]},
                config={"recursion_limit": recursion_limit},
            )
            messages = result.get("messages", [])
            last_msg = messages[-1] if messages else None
            final_answer = (
                str(last_msg.content) if last_msg and getattr(last_msg, "content", None) else ""
            )
        except GraphRecursionError:
            # S13.3: when max_steps is reached, final answer is empty string
            final_answer = ""
            steps = task.max_steps
        except Exception as exc:
            return AgentRunResult(
                final_answer="",
                usage=usage,
                transcript=[{"role": "user", "content": task.prompt}],
                steps=steps,
                error=f"LangGraph runner error: {exc}",
            )

        # Calculate consumption and counts
        tokens_in = 0
        tokens_out = 0
        reported_cost: float | None = None
        tool_calls = 0

        for msg in messages:
            if isinstance(msg, AIMessage):
                if steps < task.max_steps:
                    steps += 1
                tool_calls += len(getattr(msg, "tool_calls", []))
                usage_meta = getattr(msg, "usage_metadata", None)
                if isinstance(usage_meta, dict):
                    tokens_in += int(usage_meta.get("input_tokens", 0) or 0)
                    tokens_out += int(usage_meta.get("output_tokens", 0) or 0)

                resp_meta = getattr(msg, "response_metadata", None)
                if isinstance(resp_meta, dict):
                    if not usage_meta:
                        t_usage = resp_meta.get("token_usage", {})
                        if isinstance(t_usage, dict):
                            tokens_in += int(t_usage.get("prompt_tokens", 0) or 0)
                            tokens_out += int(t_usage.get("completion_tokens", 0) or 0)

                    raw_usage = resp_meta.get("usage", {})
                    if isinstance(raw_usage, dict) and "cost" in raw_usage:
                        with contextlib.suppress(Exception):
                            cost_val = float(raw_usage["cost"])
                            reported_cost = (reported_cost or 0.0) + cost_val

        cost_usd = calculate_cost(
            task.model,
            tokens_in,
            tokens_out,
            reported_cost=reported_cost,
        )

        usage = Usage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            steps=steps,
            tool_calls=tool_calls,
        )

        transcript = _build_transcript(messages, task.prompt, final_answer)

        return AgentRunResult(
            final_answer=final_answer,
            usage=usage,
            transcript=transcript,
            steps=steps,
            error=None,
        )
