"""Minimal LangGraph ReAct agent example with tool support (D61, S13.4, E43).

Demonstrates building a minimal LangGraph agent using create_react_agent,
supporting offline execution with FakeLLM as well as live OpenAI-compatible models.
"""

from __future__ import annotations

import asyncio
import sys
import warnings
from pathlib import Path
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

# Install MCP compatibility shims before importing LangGraph prebuilt
from skeptic_agent.runner.adapters.langgraph import _ensure_mcp_compat

_ensure_mcp_compat()

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from langgraph.prebuilt import create_react_agent

from skeptic_agent.runner.fake_llm import FakeLLM  # noqa: E402
from skeptic_agent.scenario.model import load_scenario  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_PATH = (
    REPO_ROOT / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"
)


@tool
def sb_weather__get_forecast(city: str) -> str:
    """Retrieve weather forecast data for a specified city (temperature, conditions)."""
    forecasts = {
        "Paris": "14.5",
        "Berlin": "10.6",
        "Tokyo": "18.0",
        "New York": "12.0",
        "London": "11.0",
    }
    return forecasts.get(city, "15.0")


def build_agent(
    model: Any | None = None,
    tools: list[BaseTool] | None = None,
) -> Any:
    """Construct a prebuilt LangGraph ReAct agent.

    Args:
        model: LangChain ChatModel or FakeLLM-backed ChatOpenAI.
        tools: List of LangChain tools. Defaults to weather forecast tool.

    Returns:
        Compiled LangGraph ReAct agent graph.
    """
    tools = tools or [sb_weather__get_forecast]

    if model is None:
        # Default to FakeLLM oracle_follower for deterministic offline execution
        scenario = load_scenario(DEFAULT_SCENARIO_PATH) if DEFAULT_SCENARIO_PATH.is_file() else None
        fake_llm = FakeLLM("oracle_follower", scenario=scenario)
        model = ChatOpenAI(
            model="fake/oracle_follower",
            async_client=fake_llm.chat.completions,
            api_key=SecretStr("dummy"),
        )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        return create_react_agent(model=model, tools=tools)


async def run_agent(
    prompt: str,
    agent: Any | None = None,
    max_steps: int = 10,
) -> dict[str, Any]:
    """Execute the agent on a given user prompt.

    Args:
        prompt: User task prompt.
        agent: Compiled agent (constructed if omitted).
        max_steps: Maximum turns limit (mapped to recursion_limit).

    Returns:
        Dictionary containing messages, final_answer, and steps.
    """
    if agent is None:
        agent = build_agent()

    recursion_limit = 2 * max_steps + 1
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"recursion_limit": recursion_limit},
    )

    messages: list[BaseMessage] = result.get("messages", [])
    final_answer = messages[-1].content if messages else ""
    return {
        "prompt": prompt,
        "final_answer": str(final_answer),
        "messages": messages,
        "steps": len(messages),
    }


def main() -> int:
    """CLI entrypoint for standalone demonstration."""
    print("=" * 70)
    print("Minimal LangGraph ReAct Agent (Offline FakeLLM Mode)")
    print("=" * 70)

    prompt = "What is the maximum temperature in Paris today? Answer with just the number."
    print(f"\nUser Prompt: {prompt}\n")

    result = asyncio.run(run_agent(prompt))

    print("Agent Execution Trace:")
    for idx, msg in enumerate(result["messages"]):
        role = getattr(msg, "type", "message")
        content = getattr(msg, "content", "")
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            print(f"  [{idx + 1}] AI Tool Calls: {tool_calls}")
        else:
            print(f"  [{idx + 1}] {role.upper()}: {content}")

    print(f"\nFinal Answer: {result['final_answer']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
