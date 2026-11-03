"""OpenAI Agents SDK Adapter (S13.2, S13.4, E42).

Connects MCP servers via MCPServerStdio, configures an Agent with the framework-default
instructions and behaviors, and executes turns via Runner.run.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import Any

try:
    import agents
    from agents import Agent, ModelSettings, Runner
    from agents.exceptions import MaxTurnsExceeded
    from agents.mcp.server import MCPServer, MCPServerStdio, MCPServerStdioParams
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

    # Disable tracing to avoid unauthenticated telemetry export attempts
    agents.set_tracing_disabled(True)
except ImportError as exc:
    raise ImportError(
        f"OpenAI Agents adapter requires the 'openai-agents' extra: {exc}. "
        "Install with: uv pip install 'skeptic-agent[openai-agents]'"
    ) from exc

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.llm import calculate_cost, create_llm_client, resolve_model

CLIENT_SESSION_TIMEOUT_SECONDS: float = 20.0


def _build_transcript(
    prompt: str,
    new_items: list[Any],
    final_answer: str,
) -> list[dict[str, Any]]:
    """Convert SDK run items into standard OpenAI-compatible transcript messages."""
    transcript: list[dict[str, Any]] = [
        {"role": "user", "content": prompt},
    ]

    for item in new_items:
        item_type = getattr(item, "type", "")
        if item_type == "tool_call_item":
            raw = getattr(item, "raw_item", None)
            call_id = getattr(raw, "call_id", "") or getattr(raw, "id", "")
            func_name = getattr(raw, "name", "")
            func_args = getattr(raw, "arguments", "{}")
            transcript.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "arguments": (
                                    func_args
                                    if isinstance(func_args, str)
                                    else json.dumps(func_args)
                                ),
                            },
                        }
                    ],
                }
            )
        elif item_type == "tool_call_output_item":
            raw = getattr(item, "raw_item", {})
            call_id = (
                raw.get("call_id", "") if isinstance(raw, dict) else getattr(raw, "call_id", "")
            )
            output = getattr(item, "output", "")
            if isinstance(output, dict):
                content_text = str(output.get("text", "")) or json.dumps(output)
            elif isinstance(output, str):
                content_text = output
            else:
                content_text = str(output)
            transcript.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": content_text,
                }
            )
        elif item_type == "message_output_item":
            raw = getattr(item, "raw_item", None)
            text = ""
            if raw and getattr(raw, "content", None):
                text_parts = [
                    getattr(part, "text", "")
                    for part in raw.content
                    if getattr(part, "type", "") == "output_text" or hasattr(part, "text")
                ]
                text = "".join(text_parts)
            else:
                text = str(getattr(item, "text", ""))
            transcript.append(
                {
                    "role": "assistant",
                    "content": text or final_answer,
                }
            )

    if final_answer and not any(
        m.get("role") == "assistant" and m.get("content") for m in transcript
    ):
        transcript.append({"role": "assistant", "content": final_answer})

    return transcript


class OpenAIAgentsAdapter:
    """Adapter wrapping OpenAI Agents SDK satisfying AgentAdapter protocol (S13.2, S13.4)."""

    name: str = "openai-agents"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run the OpenAI Agents SDK runner on the given task."""
        llm_client = create_llm_client(task.model, scenario=task.scenario)
        config = resolve_model(task.model)

        model = OpenAIChatCompletionsModel(
            model=config.model_name,
            openai_client=llm_client,
        )

        model_settings = (
            ModelSettings(extra_body={"usage": {"include": True}})
            if config.provider == "openrouter"
            else ModelSettings()
        )

        usage = Usage()
        infra_error: str | None = None

        async with contextlib.AsyncExitStack() as stack:
            mcp_servers: list[MCPServer] = []
            for server_spec in task.servers:
                env = dict(os.environ)
                env.update(task.env)
                env.update(server_spec.env)

                params: MCPServerStdioParams = {
                    "command": server_spec.command[0],
                    "args": server_spec.command[1:],
                    "env": env,
                    "cwd": str(task.workdir),
                }

                server = MCPServerStdio(
                    params=params,
                    name=server_spec.name,
                    client_session_timeout_seconds=CLIENT_SESSION_TIMEOUT_SECONDS,
                )

                try:
                    await stack.enter_async_context(server)
                    mcp_servers.append(server)
                except Exception as exc:
                    infra_error = f"Failed to start MCP server {server_spec.name}: {exc}"
                    return AgentRunResult(
                        final_answer="",
                        usage=usage,
                        transcript=[{"role": "user", "content": task.prompt}],
                        steps=0,
                        error=infra_error,
                    )

            # Framework default agent construction (S13.4): no custom prompts or hooks
            agent: Agent[Any] = Agent(
                name="openai_agent",
                model=model,
                mcp_servers=mcp_servers,
                model_settings=model_settings,
            )

            result: Any = None
            final_answer = ""
            steps = 0

            try:
                result = await Runner.run(
                    agent,
                    input=task.prompt,
                    max_turns=task.max_steps,
                )
                final_answer = str(result.final_output) if result.final_output is not None else ""
            except MaxTurnsExceeded:
                # S13.3: when max_steps is reached, final answer is empty string
                final_answer = ""
                steps = task.max_steps
            except Exception as exc:
                return AgentRunResult(
                    final_answer="",
                    usage=usage,
                    transcript=[{"role": "user", "content": task.prompt}],
                    steps=steps,
                    error=f"OpenAI agents runner error: {exc}",
                )

            # Extract consumption and transcript
            tokens_in = 0
            tokens_out = 0
            reported_cost: float | None = None
            new_items: list[Any] = []

            if result is not None:
                steps = len(result.raw_responses)
                new_items = getattr(result, "new_items", [])
                for resp in result.raw_responses:
                    resp_usage = getattr(resp, "usage", None)
                    if resp_usage:
                        tokens_in += getattr(resp_usage, "input_tokens", 0)
                        tokens_out += getattr(resp_usage, "output_tokens", 0)

                    raw_usage = getattr(resp, "raw_usage", None)
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
            tool_calls = sum(
                1 for item in new_items if getattr(item, "type", "") == "tool_call_item"
            )

            usage = Usage(
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                steps=steps,
                tool_calls=tool_calls,
            )

            transcript = _build_transcript(task.prompt, new_items, final_answer)

            return AgentRunResult(
                final_answer=final_answer,
                usage=usage,
                transcript=transcript,
                steps=steps,
                error=None,
            )
