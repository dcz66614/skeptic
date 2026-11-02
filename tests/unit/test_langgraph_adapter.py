"""Unit tests for LangGraphAdapter (S13.2, S13.4, E43)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from skeptic_agent.runner.adapters import ADAPTERS, get_adapter
from skeptic_agent.runner.adapters.base import EpisodeTask, McpServerSpec
from skeptic_agent.runner.adapters.langgraph import (
    LangGraphAdapter,
    _build_transcript,
)
from skeptic_agent.scenario.model import load_scenario

pytestmark = pytest.mark.unit

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"


def test_adapter_registration() -> None:
    """Verify langgraph is registered in ADAPTERS and conforms to AgentAdapter protocol."""
    assert "langgraph" in ADAPTERS
    adapter = get_adapter("langgraph")
    assert isinstance(adapter, LangGraphAdapter)
    assert adapter.name == "langgraph"
    assert hasattr(adapter, "run")
    assert callable(adapter.run)


def test_transcript_formatting() -> None:
    """Verify conversion of LangChain messages into OpenAI-compatible transcript dictionaries."""
    messages = [
        HumanMessage(content="Check weather"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_forecast",
                    "args": {"city": "Paris"},
                    "id": "call_abc_123",
                }
            ],
        ),
        ToolMessage(
            content=[{"type": "text", "text": '{"max_c": 14.5}'}],
            tool_call_id="call_abc_123",
        ),
        AIMessage(content="The temperature is 14.5"),
    ]

    transcript = _build_transcript(
        messages=messages,
        fallback_prompt="Check weather",
        final_answer="The temperature is 14.5",
    )

    assert len(transcript) == 4
    assert transcript[0] == {"role": "user", "content": "Check weather"}
    assert transcript[1]["role"] == "assistant"
    assert transcript[1]["tool_calls"][0]["id"] == "call_abc_123"
    assert transcript[1]["tool_calls"][0]["function"]["name"] == "get_forecast"
    assert transcript[1]["tool_calls"][0]["function"]["arguments"] == '{"city": "Paris"}'
    assert transcript[2] == {
        "role": "tool",
        "tool_call_id": "call_abc_123",
        "content": '{"max_c": 14.5}',
    }
    assert transcript[3] == {
        "role": "assistant",
        "content": "The temperature is 14.5",
    }


def test_transcript_formatting_fallback_final_answer() -> None:
    """If no message contains final answer, final_answer is added as an assistant turn."""
    transcript = _build_transcript(
        messages=[HumanMessage(content="Hello")],
        fallback_prompt="Hello",
        final_answer="World",
    )
    assert transcript == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "World"},
    ]


@pytest.mark.asyncio
async def test_server_failure_returns_infra_error(tmp_path: Path) -> None:
    """If an MCP server fails to launch, run returns AgentRunResult with error set."""
    adapter = LangGraphAdapter()
    invalid_server = McpServerSpec(
        name="failing_server",
        command=["non_existent_command_xyz_12345", "--arg"],
        env={},
    )
    task = EpisodeTask(
        episode_id="test_ep_fail",
        prompt="Test prompt",
        servers=[invalid_server],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is not None
    assert "Failed to initialize MCP servers" in result.error
    assert result.final_answer == ""
    assert result.steps == 0


@pytest.mark.asyncio
async def test_recursion_limit_returns_empty_final_answer(tmp_path: Path) -> None:
    """When GraphRecursionError is raised, final_answer is empty string and steps=max_steps."""
    adapter = LangGraphAdapter()
    task = EpisodeTask(
        episode_id="test_ep_recursion",
        prompt="Infinite loop prompt",
        servers=[],
        model="fake/oracle_follower",
        max_steps=4,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    with patch("skeptic_agent.runner.adapters.langgraph.create_react_agent") as mock_agent_create:
        mock_graph = mock_agent_create.return_value

        async def _raise_recursion(*args: Any, **kwargs: Any) -> None:
            raise GraphRecursionError("Recursion limit of 9 reached")

        mock_graph.ainvoke.side_effect = _raise_recursion

        result = await adapter.run(task)
        assert result.final_answer == ""
        assert result.steps == 4
        assert result.error is None


@pytest.mark.asyncio
async def test_unexpected_runner_exception_returns_error(tmp_path: Path) -> None:
    """Unknown runtime exceptions during agent execution are caught as infra errors."""
    adapter = LangGraphAdapter()
    task = EpisodeTask(
        episode_id="test_ep_err",
        prompt="Error prompt",
        servers=[],
        model="fake/oracle_follower",
        max_steps=3,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    with patch("skeptic_agent.runner.adapters.langgraph.create_react_agent") as mock_agent_create:
        mock_graph = mock_agent_create.return_value

        async def _raise_generic(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Corrupted graph execution state")

        mock_graph.ainvoke.side_effect = _raise_generic

        result = await adapter.run(task)
        assert result.error is not None
        assert "LangGraph runner error: Corrupted graph execution state" in result.error
        assert result.final_answer == ""


@pytest.mark.asyncio
async def test_model_routing_openrouter_and_custom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify openrouter model settings inject extra_body and base_url."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-router-key")
    adapter = LangGraphAdapter()

    captured_kwargs: dict[str, Any] = {}

    from langchain_openai import ChatOpenAI

    orig_init = ChatOpenAI.__init__

    def mock_init(self: Any, *args: Any, **kwargs: Any) -> None:
        captured_kwargs.update(kwargs)
        orig_init(self, *args, **kwargs)

    with patch.object(ChatOpenAI, "__init__", mock_init):
        task = EpisodeTask(
            episode_id="test_ep_route",
            prompt="Hello router",
            servers=[],
            model="openrouter/anthropic/claude-3.5-sonnet",
            max_steps=2,
            timeout_s=30,
            prompt_variant="plain",
            workdir=tmp_path,
            env={},
        )
        with patch("skeptic_agent.runner.adapters.langgraph.create_react_agent") as mock_agent:
            mock_graph = mock_agent.return_value

            async def mock_invoke(*args: Any, **kwargs: Any) -> dict[str, Any]:
                return {"messages": [AIMessage(content="Done")]}

            mock_graph.ainvoke.side_effect = mock_invoke
            await adapter.run(task)

    assert captured_kwargs.get("base_url") == "https://openrouter.ai/api/v1"
    assert captured_kwargs.get("extra_body") == {"usage": {"include": True}}


@pytest.mark.asyncio
async def test_text_only_completion(tmp_path: Path) -> None:
    """Test pure text completion with no MCP servers attached."""
    adapter = LangGraphAdapter()
    task = EpisodeTask(
        episode_id="test_ep_text",
        prompt="Tell me a joke",
        servers=[],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "No oracle scenario available."
    assert result.steps >= 1
    assert len(result.transcript) >= 2


@pytest.mark.asyncio
async def test_full_stdio_mcp_run(tmp_path: Path) -> None:
    """Execute full stdio MCP tool invocation and transcript extraction using weather sandbox."""
    scenario = load_scenario(SCENARIO_PATH)
    adapter = LangGraphAdapter()

    server_spec = McpServerSpec(
        name="weather",
        command=[
            sys.executable,
            "-m",
            "skeptic_agent.sandboxes.sb_weather.server",
        ],
        env={"PYTHONPATH": str(ROOT_DIR / "src")},
    )

    task = EpisodeTask(
        episode_id="test_ep_stdio",
        prompt=f"{scenario.prompt}\n\n{scenario.answer_format}",
        servers=[server_spec],
        model="fake/oracle_follower",
        max_steps=12,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
        scenario=scenario,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "14.5"
    assert result.steps >= 2
    assert result.usage.tool_calls >= 1
    assert any(m.get("role") == "tool" for m in result.transcript)
