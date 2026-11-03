"""Reference ReAct agent implementation (S13.3, E40).

Connects to wrapped MCP servers via stdio client, drives OpenAI-compatible models,
and obeys the S13.3 loop, prompt, retry, and timeout rules.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from typing import Any

from mcp import Client, StdioServerParameters
from openai import APIStatusError

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.llm import calculate_cost, create_llm_client, resolve_model

PLAIN_SYSTEM_PROMPT: str = (
    "You are a helpful assistant. Complete the user's task using the available tools. "
    "Use tools to obtain facts; do not guess. When you are done, give a concise final answer."
)

EVIDENCE_CONTRACT_EXTENSION: str = (
    '\n\nBefore your final answer, output exactly one line: "RETRIEVAL_STATUS: OK" '
    "if every fact you rely on came from a tool result that looked complete, "
    "current and consistent; "
    'otherwise "RETRIEVAL_STATUS: FAILED" followed by what is missing. '
    "Never state values that the tools did not return."
)

TOOL_TIMEOUT_SECONDS: float = 20.0
MAX_API_RETRIES: int = 3
RETRY_BACKOFFS: list[float] = [2.0, 4.0, 8.0]


def sanitize_func_name(name: str) -> str:
    """Sanitize function name to match ^[a-zA-Z0-9_-]{1,64}$ (S13.3)."""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return clean[:64]


def extract_tool_result_text(res: Any) -> str:
    """Extract concatenated text blocks from CallToolResult (S13.3)."""
    text_parts: list[str] = []
    content = getattr(res, "content", None)
    if isinstance(content, list):
        for block in content:
            txt = getattr(block, "text", None)
            if isinstance(txt, str):
                text_parts.append(txt)
    elif isinstance(content, str):
        text_parts.append(content)

    joined = "\n".join(text_parts) if text_parts else ""
    is_err = getattr(res, "is_error", False) or getattr(res, "isError", False)
    if is_err:
        return f"ERROR: {joined}"
    return joined


class ReferenceAgent:
    """Reference ReAct agent implementing S13.3 specification."""

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run the reference agent loop on the provided episode task."""
        model_config = resolve_model(task.model)
        llm = create_llm_client(task.model, scenario=task.scenario)

        # Build system prompt (S13.3)
        if task.prompt_variant == "evidence_contract":
            system_prompt = f"{PLAIN_SYSTEM_PROMPT}{EVIDENCE_CONTRACT_EXTENSION}"
        else:
            system_prompt = PLAIN_SYSTEM_PROMPT

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task.prompt},
        ]

        usage = Usage()
        step_count = 0
        final_answer = ""
        infra_error: str | None = None

        # Connect to each MCP server via stdio using high-level SDK v2 Client (ADR-0004, S13.3)
        connect_mode = task.env.get("SKEPTIC_MCP_MODE", "auto")
        async with contextlib.AsyncExitStack() as stack:
            clients: dict[str, Client] = {}
            tools_map: dict[str, tuple[str, str]] = {}  # func_name -> (server_name, tool_name)
            tools_by_toolname: dict[
                str, tuple[str, str]
            ] = {}  # tool_name -> (server_name, tool_name)
            openai_tools: list[dict[str, Any]] = []

            for server_spec in task.servers:
                env = dict(os.environ)
                env.update(task.env)
                env.update(server_spec.env)

                params = StdioServerParameters(
                    command=server_spec.command[0],
                    args=server_spec.command[1:],
                    env=env,
                    cwd=str(task.workdir),
                )
                try:
                    client = await stack.enter_async_context(Client(params, mode=connect_mode))
                    clients[server_spec.name] = client

                    tool_list = await client.list_tools()
                    for t in tool_list.tools:
                        s_name = sanitize_func_name(server_spec.name)
                        t_name = sanitize_func_name(t.name)
                        func_name = f"{s_name}__{t_name}"

                        # Handle collisions
                        base_func = func_name
                        suffix = 2
                        while func_name in tools_map:
                            func_name = f"{base_func}_{suffix}"
                            suffix += 1

                        tools_map[func_name] = (server_spec.name, t.name)
                        tools_by_toolname[t.name] = (server_spec.name, t.name)

                        openai_tools.append(
                            {
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "description": t.description or "",
                                    "parameters": (
                                        getattr(t, "input_schema", None)
                                        or getattr(t, "inputSchema", None)
                                        or {"type": "object", "properties": {}}
                                    ),
                                },
                            }
                        )
                except Exception as exc:
                    infra_error = f"Failed to start MCP server {server_spec.name}: {exc}"
                    return AgentRunResult(
                        final_answer="",
                        usage=usage,
                        transcript=messages,
                        steps=0,
                        error=infra_error,
                    )

            # Execution loop (up to max_steps)
            for _ in range(task.max_steps):
                step_count += 1

                # Call LLM with retry on 429/5xx (S13.3)
                call_kwargs: dict[str, Any] = {
                    "model": model_config.model_name,
                    "messages": messages,
                    "temperature": 0,
                    "max_tokens": 1024,
                }
                if openai_tools:
                    call_kwargs["tools"] = openai_tools
                if model_config.provider == "openrouter" or task.model.startswith("openrouter/"):
                    call_kwargs["extra_body"] = {"usage": {"include": True}}

                response: Any = None
                temperature_retry_occurred = False

                for attempt_idx in range(MAX_API_RETRIES + 1):
                    try:
                        response = await llm.chat.completions.create(**call_kwargs)
                        break
                    except APIStatusError as err:
                        # If model rejects temperature (S13.3)
                        if "temperature" in str(err).lower() and "temperature" in call_kwargs:
                            call_kwargs.pop("temperature", None)
                            temperature_retry_occurred = True
                            try:
                                response = await llm.chat.completions.create(**call_kwargs)
                                break
                            except Exception as inner_err:
                                infra_error = f"LLM API error after temperature retry: {inner_err}"
                                return AgentRunResult(
                                    final_answer="",
                                    usage=usage,
                                    transcript=messages,
                                    steps=step_count,
                                    error=infra_error,
                                )

                        if (
                            err.status_code == 429 or err.status_code >= 500
                        ) and attempt_idx < MAX_API_RETRIES:
                            await asyncio.sleep(RETRY_BACKOFFS[attempt_idx])
                            continue
                        infra_error = f"LLM API error status {err.status_code}: {err}"
                        return AgentRunResult(
                            final_answer="",
                            usage=usage,
                            transcript=messages,
                            steps=step_count,
                            error=infra_error,
                        )
                    except TypeError:
                        # Model may reject temperature parameter locally (S13.3)
                        if "temperature" in call_kwargs:
                            call_kwargs.pop("temperature", None)
                            temperature_retry_occurred = True
                            try:
                                response = await llm.chat.completions.create(**call_kwargs)
                                break
                            except Exception as inner_err:
                                infra_error = f"LLM API error: {inner_err}"
                                return AgentRunResult(
                                    final_answer="",
                                    usage=usage,
                                    transcript=messages,
                                    steps=step_count,
                                    error=infra_error,
                                )
                        else:
                            infra_error = "LLM API type error"
                            return AgentRunResult(
                                final_answer="",
                                usage=usage,
                                transcript=messages,
                                steps=step_count,
                                error=infra_error,
                            )
                    except Exception as exc:
                        infra_error = f"LLM API unexpected error: {exc}"
                        return AgentRunResult(
                            final_answer="",
                            usage=usage,
                            transcript=messages,
                            steps=step_count,
                            error=infra_error,
                        )

                if response is None:
                    infra_error = "LLM API returned no response"
                    return AgentRunResult(
                        final_answer="",
                        usage=usage,
                        transcript=messages,
                        steps=step_count,
                        error=infra_error,
                    )

                if temperature_retry_occurred:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Note: Model does not support temperature parameter; "
                                "retried without temperature."
                            ),
                        }
                    )

                # Track usage (S13.3)
                resp_usage = getattr(response, "usage", None)
                if resp_usage:
                    tin = getattr(resp_usage, "prompt_tokens", 0) or 0
                    tout = getattr(resp_usage, "completion_tokens", 0) or 0
                    usage.tokens_in += tin
                    usage.tokens_out += tout

                    # Check for reported cost (e.g. OpenRouter usage.cost)
                    reported_cost: float | None = None
                    if hasattr(resp_usage, "cost") and resp_usage.cost is not None:
                        with contextlib.suppress(TypeError, ValueError):
                            reported_cost = float(resp_usage.cost)
                    elif hasattr(resp_usage, "model_extra") and isinstance(
                        resp_usage.model_extra, dict
                    ):
                        c = resp_usage.model_extra.get("cost")
                        if c is not None:
                            with contextlib.suppress(TypeError, ValueError):
                                reported_cost = float(c)
                    elif isinstance(resp_usage, dict) and "cost" in resp_usage:
                        with contextlib.suppress(TypeError, ValueError):
                            reported_cost = float(resp_usage["cost"])

                    cost = calculate_cost(task.model, tin, tout, reported_cost=reported_cost)
                    usage.cost_usd += cost

                choice = response.choices[0]
                assistant_msg = choice.message
                assistant_dict: dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_msg.content,
                }
                tool_calls = getattr(assistant_msg, "tool_calls", None)
                if tool_calls:
                    assistant_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ]

                messages.append(assistant_dict)

                # Process tool calls or complete
                if tool_calls:
                    for tc in tool_calls:
                        fn_name = tc.function.name
                        # Resolve server and tool
                        server_name: str | None = None
                        tool_name: str = fn_name
                        if fn_name in tools_map:
                            server_name, tool_name = tools_map[fn_name]
                        elif fn_name in tools_by_toolname:
                            server_name, tool_name = tools_by_toolname[fn_name]
                        elif "__" in fn_name:
                            s_part, t_part = fn_name.split("__", 1)
                            server_name = s_part
                            tool_name = t_part
                        elif task.servers:
                            server_name = task.servers[0].name

                        target_client = clients.get(server_name) if server_name else None
                        if target_client is None and clients:
                            target_client = next(iter(clients.values()))

                        try:
                            args = (
                                json.loads(tc.function.arguments) if tc.function.arguments else {}
                            )
                        except Exception:
                            args = {}

                        tool_output: str
                        usage.tool_calls += 1
                        if target_client is None:
                            tool_output = f"ERROR: unknown MCP server for tool {fn_name}"
                        else:
                            try:
                                tool_res = await asyncio.wait_for(
                                    target_client.call_tool(tool_name, args),
                                    timeout=TOOL_TIMEOUT_SECONDS,
                                )
                                tool_output = extract_tool_result_text(tool_res)
                            except TimeoutError:
                                tool_output = "ERROR: tool call timed out"
                            except Exception as tool_exc:
                                tool_output = f"ERROR: tool execution exception: {tool_exc}"

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": tool_output,
                            }
                        )
                else:
                    # Model provided final content and no tool calls
                    final_answer = assistant_msg.content or ""
                    break

        usage.steps = step_count
        return AgentRunResult(
            final_answer=final_answer,
            usage=usage,
            transcript=messages,
            steps=step_count,
            error=infra_error,
        )
