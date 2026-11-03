"""PydanticAI Adapter (S13.2, S13.4, E44).

Connects MCP servers via pydantic_ai.mcp.MCPToolset and StdioTransport,
configures an Agent with framework default settings, and executes turns
using agent.run with UsageLimits.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any

try:
    import pydantic_ai  # noqa: F401
    from fastmcp.client.transports.stdio import StdioTransport
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import UsageLimitExceeded
    from pydantic_ai.mcp import MCPToolset
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        ToolCallPart,
        ToolReturnPart,
    )
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits
except ImportError as exc:
    raise ImportError(
        f"PydanticAI adapter requires the 'pydantic-ai' extra: {exc}. "
        "Install with: uv pip install 'skeptic-agent[pydantic-ai]'"
    ) from exc

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.llm import calculate_cost, create_llm_client, resolve_model

CLIENT_SESSION_TIMEOUT_SECONDS: float = 20.0


def _build_transcript(
    prompt: str,
    messages: list[Any],
    final_answer: str,
) -> list[dict[str, Any]]:
    """Convert PydanticAI message history into standard OpenAI-compatible transcript messages."""
    transcript: list[dict[str, Any]] = []

    for msg in messages:
        if isinstance(msg, ModelRequest):
            for part in getattr(msg, "parts", []):
                part_kind = getattr(part, "part_kind", "")
                content = getattr(part, "content", "")
                if part_kind in ("tool-return", "retry-prompt") or isinstance(part, ToolReturnPart):
                    call_id = getattr(part, "tool_call_id", "") or "call_id"
                    transcript.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": str(content),
                        }
                    )
                else:
                    transcript.append({"role": "user", "content": str(content)})

        elif isinstance(msg, ModelResponse):
            tool_calls: list[dict[str, Any]] = []
            text_parts: list[str] = []
            for part in getattr(msg, "parts", []):
                part_kind = getattr(part, "part_kind", "")
                if part_kind == "tool-call" or isinstance(part, ToolCallPart):
                    raw_args = getattr(part, "args", {})
                    args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args)
                    tool_calls.append(
                        {
                            "id": getattr(part, "tool_call_id", "") or "call_id",
                            "type": "function",
                            "function": {
                                "name": getattr(part, "tool_name", ""),
                                "arguments": args_str,
                            },
                        }
                    )
                elif part_kind == "text" or isinstance(part, TextPart):
                    text_parts.append(str(getattr(part, "content", "")))

            if tool_calls:
                transcript.append(
                    {
                        "role": "assistant",
                        "content": "".join(text_parts) if text_parts else None,
                        "tool_calls": tool_calls,
                    }
                )
            elif text_parts:
                transcript.append(
                    {
                        "role": "assistant",
                        "content": "".join(text_parts),
                    }
                )

    if not transcript:
        transcript.append({"role": "user", "content": prompt})

    if final_answer and not any(
        m.get("role") == "assistant" and m.get("content") == final_answer for m in transcript
    ):
        transcript.append({"role": "assistant", "content": final_answer})

    return transcript


class PydanticAIAdapter:
    """Adapter wrapping PydanticAI satisfying AgentAdapter protocol (S13.2, S13.4)."""

    name: str = "pydantic-ai"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run PydanticAI agent runner on the given task."""
        config = resolve_model(task.model)
        provider: OpenAIProvider
        if config.is_fake:
            fake_client = create_llm_client(task.model, scenario=task.scenario)
            provider = OpenAIProvider(openai_client=fake_client)
        else:
            provider = OpenAIProvider(
                base_url=config.base_url,
                api_key=config.api_key or "sk-dummy",
            )

        model = OpenAIChatModel(
            model_name=config.model_name,
            provider=provider,
        )

        usage = Usage()
        infra_error: str | None = None

        async with contextlib.AsyncExitStack() as stack:
            toolsets: list[MCPToolset] = []
            for server_spec in task.servers:
                env = dict(os.environ)
                env.update(task.env)
                env.update(server_spec.env)
                transport = StdioTransport(
                    command=server_spec.command[0],
                    args=server_spec.command[1:],
                    env=env,
                    cwd=str(task.workdir),
                )
                toolset = MCPToolset(
                    transport,
                    read_timeout=CLIENT_SESSION_TIMEOUT_SECONDS,
                    init_timeout=CLIENT_SESSION_TIMEOUT_SECONDS,
                )
                try:
                    await stack.enter_async_context(toolset)
                    toolsets.append(toolset)
                except Exception as exc:
                    infra_error = f"Failed to start MCP server {server_spec.name}: {exc}"
                    return AgentRunResult(
                        final_answer="",
                        usage=usage,
                        transcript=[{"role": "user", "content": task.prompt}],
                        steps=0,
                        error=infra_error,
                    )

            agent: Agent[Any] = Agent(
                model=model,
                toolsets=toolsets,
            )

            usage_limits = UsageLimits(request_limit=task.max_steps)
            result: Any = None
            final_answer = ""
            steps = 0

            try:
                result = await agent.run(task.prompt, usage_limits=usage_limits)
                final_answer = str(result.output) if result.output is not None else ""
            except UsageLimitExceeded:
                # S13.3: when max_steps is reached, final answer is empty string
                final_answer = ""
                steps = task.max_steps
            except Exception as exc:
                return AgentRunResult(
                    final_answer="",
                    usage=usage,
                    transcript=[{"role": "user", "content": task.prompt}],
                    steps=steps,
                    error=f"PydanticAI runner error: {exc}",
                )

            tokens_in = 0
            tokens_out = 0
            tool_calls_count = 0
            messages: list[Any] = []

            if result is not None:
                run_usage = getattr(result, "usage", None)
                if run_usage:
                    tokens_in = getattr(run_usage, "input_tokens", 0) or 0
                    tokens_out = getattr(run_usage, "output_tokens", 0) or 0
                    tool_calls_count = getattr(run_usage, "tool_calls", 0) or 0
                    steps = getattr(run_usage, "requests", 0) or 1
                messages = result.all_messages()

            if not tool_calls_count and messages:
                for m in messages:
                    if isinstance(m, ModelResponse):
                        tool_calls_count += sum(
                            1
                            for p in getattr(m, "parts", [])
                            if getattr(p, "part_kind", "") == "tool-call"
                            or isinstance(p, ToolCallPart)
                        )

            cost_usd = calculate_cost(task.model, tokens_in, tokens_out)
            usage = Usage(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                steps=steps,
                tool_calls=tool_calls_count,
            )

            transcript = _build_transcript(task.prompt, messages, final_answer)

            return AgentRunResult(
                final_answer=final_answer,
                usage=usage,
                transcript=transcript,
                steps=steps,
                error=None,
            )
