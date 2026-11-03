"""CrewAI Adapter (S13.2, S13.4, E44, ADR-0006).

Connects MCP servers via mcpadapt (without crewai-tools/pymupdf per ADR-0006),
configures a single Agent and Task using framework default construction, and
executes turns via Crew.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from typing import Any

# Disable telemetry and interactive prompt handlers
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_DISABLE_TRACKING", "true")
os.environ.setdefault("CREWAI_TESTING", "true")

CLIENT_SESSION_TIMEOUT_SECONDS: float = 20.0


def _ensure_mcpadapt_compat() -> None:
    """Install backwards-compatibility shims for mcpadapt under mcp 2.3+."""
    import mcp.client.streamable_http

    if not hasattr(mcp.client.streamable_http, "streamablehttp_client"):
        mcp.client.streamable_http.streamablehttp_client = (  # type: ignore[attr-defined]
            mcp.client.streamable_http.streamable_http_client
        )

    if "mcp.client.websocket" not in sys.modules:
        ws_mod = types.ModuleType("mcp.client.websocket")
        ws_mod.websocket_client = None  # type: ignore[attr-defined]
        sys.modules["mcp.client.websocket"] = ws_mod

    from datetime import timedelta

    import mcp.client.session
    import mcp.types as mcp_types

    orig_client_session_init = mcp.client.session.ClientSession.__init__
    if getattr(orig_client_session_init, "__name__", "") != "_patched_session_init":

        def _patched_session_init(self: Any, *args: Any, **kwargs: Any) -> None:
            args_list = list(args)
            if len(args_list) >= 3 and isinstance(args_list[2], timedelta):
                args_list[2] = args_list[2].total_seconds()
            if "read_timeout_seconds" in kwargs and isinstance(
                kwargs["read_timeout_seconds"], timedelta
            ):
                kwargs["read_timeout_seconds"] = kwargs["read_timeout_seconds"].total_seconds()
            orig_client_session_init(self, *args_list, **kwargs)

        _patched_session_init.__name__ = "_patched_session_init"
        mcp.client.session.ClientSession.__init__ = _patched_session_init  # type: ignore[method-assign]

    if not hasattr(mcp_types.Tool, "inputSchema") or not hasattr(
        mcp_types.Tool.inputSchema, "fset"
    ):
        mcp_types.Tool.inputSchema = property(  # type: ignore[attr-defined]
            lambda self: self.input_schema,
            lambda self, val: setattr(self, "input_schema", val),
        )


try:
    _ensure_mcpadapt_compat()
    import crewai  # noqa: F401
    from crewai import Agent, Crew, Task
    from crewai.llms.providers.openai.completion import OpenAICompletion
    from mcp import StdioServerParameters
    from mcpadapt.core import MCPAdapt
    from mcpadapt.crewai_adapter import CrewAIAdapter as CrewAIToolAdapter
except ImportError as exc:
    raise ImportError(
        f"CrewAI adapter requires the 'crewai' extra: {exc}. "
        "Install with: uv pip install 'skeptic-agent[crewai]'"
    ) from exc

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask, Usage  # noqa: E402
from skeptic_agent.runner.fake_llm import FakeLLM  # noqa: E402
from skeptic_agent.runner.llm import calculate_cost, create_llm_client, resolve_model  # noqa: E402


class SkepticCrewAILLM(OpenAICompletion):
    """CrewAI LLM adapter driving FakeLLM for tests and local evaluations (S13.5)."""

    def __init__(
        self,
        fake_llm: FakeLLM,
        model_name: str,
        tools_spec: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(model=model_name, api_key="sk-fake")
        self._fake_llm = fake_llm
        self._tools_spec = tools_spec or []

    def set_tools_spec(self, tools_spec: list[dict[str, Any]]) -> None:
        """Update available tools specification for FakeLLM resolution."""
        self._tools_spec = tools_spec

    def call(
        self,
        messages: str | list[Any],
        tools: list[Any] | None = None,
        callbacks: list[Any] | None = None,
        available_functions: dict[str, Any] | None = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        """Call FakeLLM and translate tool calls / completions into ReAct formatted text."""
        msg_list: list[dict[str, Any]] = []
        if isinstance(messages, str):
            msg_list = [{"role": "user", "content": messages}]
        else:
            for m in messages:
                if isinstance(m, dict):
                    msg_list.append(m)
                else:
                    msg_list.append(
                        {
                            "role": getattr(m, "role", "user"),
                            "content": getattr(m, "content", ""),
                        }
                    )

        resp = asyncio.run(
            self._fake_llm.generate(
                model=self.model,
                messages=msg_list,
                tools=self._tools_spec or None,
            )
        )
        choice = resp.choices[0]
        if choice.message.tool_calls:
            tc = choice.message.tool_calls[0]
            func = getattr(tc, "function", None)
            if func is not None:
                name = getattr(func, "name", "")
                args = getattr(func, "arguments", "{}")
                return f"Thought: Call {name}\nAction: {name}\nAction Input: {args}"

        content = choice.message.content or ""
        if "Final Answer:" not in content:
            return f"Thought: Finished task.\nFinal Answer: {content}"
        return content


def _build_transcript(
    prompt: str,
    final_answer: str,
    tools_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert CrewAI execution history into standard OpenAI-compatible transcript messages."""
    transcript: list[dict[str, Any]] = [
        {"role": "user", "content": prompt},
    ]

    for i, tr in enumerate(tools_results):
        tname = str(tr.get("tool_name", "tool"))
        targs = tr.get("tool_args", {})
        tresult = str(tr.get("result", ""))
        call_id = f"call_{i + 1}"
        transcript.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tname,
                            "arguments": (
                                json.dumps(targs) if isinstance(targs, dict) else str(targs)
                            ),
                        },
                    }
                ],
            }
        )
        transcript.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": tresult,
            }
        )

    if final_answer:
        transcript.append({"role": "assistant", "content": final_answer})

    return transcript


class CrewAIAdapter:
    """Adapter wrapping CrewAI satisfying AgentAdapter protocol (S13.2, S13.4, ADR-0006)."""

    name: str = "crewai"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run CrewAI agent on the given episode task."""
        config = resolve_model(task.model)
        llm: Any = None
        if config.is_fake:
            fake_client = create_llm_client(task.model, scenario=task.scenario)
            llm = SkepticCrewAILLM(fake_client, config.model_name)
        else:
            llm = OpenAICompletion(
                model=config.model_name,
                provider="openai",
                base_url=config.base_url,
                api_key=config.api_key or "sk-dummy",
            )

        params_list: list[StdioServerParameters | dict[str, Any]] = []
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
            params_list.append(params)

        usage = Usage()

        def _execute_crew(tools: list[Any]) -> tuple[Any, Any, str | None]:
            if isinstance(llm, SkepticCrewAILLM):
                tools_spec = [
                    {
                        "type": "function",
                        "function": {
                            "name": getattr(t, "name", ""),
                            "description": getattr(t, "description", "") or "",
                        },
                    }
                    for t in tools
                ]
                llm.set_tools_spec(tools_spec)

            agent = Agent(
                role="Assistant",
                goal="Complete the user's task",
                backstory="You are a helpful assistant.",
                llm=llm,
                tools=tools,
                max_iter=task.max_steps,
                verbose=False,
            )
            task_obj = Task(
                description=task.prompt,
                expected_output="Final answer to the user's task.",
                agent=agent,
            )
            crew = Crew(
                agents=[agent],
                tasks=[task_obj],
                verbose=False,
            )
            try:
                result = crew.kickoff()
                return result, agent, None
            except Exception as exc:
                return None, agent, f"CrewAI kickoff error: {exc}"

        try:
            if params_list:
                with MCPAdapt(
                    params_list,
                    CrewAIToolAdapter(),
                    connect_timeout=10,
                    client_session_timeout_seconds=CLIENT_SESSION_TIMEOUT_SECONDS,
                ) as mcp_tools:
                    result, agent, run_err = await asyncio.to_thread(_execute_crew, mcp_tools)
            else:
                result, agent, run_err = await asyncio.to_thread(_execute_crew, [])
        except Exception as exc:
            return AgentRunResult(
                final_answer="",
                usage=usage,
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=f"MCPAdapt error: {exc}",
            )

        if run_err:
            return AgentRunResult(
                final_answer="",
                usage=usage,
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=run_err,
            )

        tools_results: list[dict[str, Any]] = getattr(agent, "tools_results", []) if agent else []
        tool_calls_count = len(tools_results)
        token_usage = getattr(result, "token_usage", None) if result else None
        tokens_in = getattr(token_usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(token_usage, "completion_tokens", 0) or 0
        successful_requests = getattr(token_usage, "successful_requests", 0) or 0
        steps = successful_requests or (tool_calls_count + 1)

        final_answer = str(getattr(result, "raw", "")) if result else ""

        # S13.3: when max_steps is reached, final answer is empty string
        executor = getattr(agent, "agent_executor", None) if agent else None
        iterations = getattr(executor, "iterations", 0) if executor else 0
        if iterations >= task.max_steps or steps > task.max_steps:
            final_answer = ""
            steps = task.max_steps

        cost_usd = calculate_cost(task.model, tokens_in, tokens_out)
        usage = Usage(
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            steps=steps,
            tool_calls=tool_calls_count,
        )

        transcript = _build_transcript(task.prompt, final_answer, tools_results)

        return AgentRunResult(
            final_answer=final_answer,
            usage=usage,
            transcript=transcript,
            steps=steps,
            error=None,
        )
