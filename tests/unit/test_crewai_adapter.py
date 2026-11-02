"""Unit tests for CrewAIAdapter (S13.2, S13.4, E44, ADR-0006)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skeptic_agent.runner.adapters import ADAPTERS, get_adapter
from skeptic_agent.runner.adapters.base import EpisodeTask, McpServerSpec
from skeptic_agent.runner.adapters.crewai import (
    CrewAIAdapter,
    SkepticCrewAILLM,
    _build_transcript,
)
from skeptic_agent.runner.fake_llm import FakeLLM
from skeptic_agent.scenario.model import load_scenario

pytestmark = pytest.mark.unit

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"


def test_adapter_registration() -> None:
    """Verify crewai is registered in ADAPTERS and conforms to AgentAdapter protocol."""
    assert "crewai" in ADAPTERS
    adapter = get_adapter("crewai")
    assert isinstance(adapter, CrewAIAdapter)
    assert adapter.name == "crewai"
    assert hasattr(adapter, "run")
    assert callable(adapter.run)


def test_transcript_formatting() -> None:
    """Verify conversion of tools_results into standard OpenAI-compatible transcript messages."""
    tools_results = [
        {
            "tool_name": "get_forecast",
            "tool_args": {"city": "Paris", "date": "2026-11-02"},
            "result": '{"max_c": 14.5}',
        }
    ]
    transcript = _build_transcript(
        prompt="What will the max temp in Paris be?",
        final_answer="14.5",
        tools_results=tools_results,
    )

    assert len(transcript) == 4
    assert transcript[0] == {"role": "user", "content": "What will the max temp in Paris be?"}
    assert transcript[1]["role"] == "assistant"
    assert transcript[1]["tool_calls"][0]["id"] == "call_1"
    assert transcript[1]["tool_calls"][0]["function"]["name"] == "get_forecast"
    assert '{"city": "Paris"' in transcript[1]["tool_calls"][0]["function"]["arguments"]
    assert transcript[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"max_c": 14.5}',
    }
    assert transcript[3] == {
        "role": "assistant",
        "content": "14.5",
    }


def test_transcript_formatting_fallback_final_answer() -> None:
    """When no tool calls occurred, transcript includes user prompt and final answer."""
    transcript = _build_transcript(
        prompt="Hello",
        final_answer="World",
        tools_results=[],
    )
    assert len(transcript) == 2
    assert transcript[0] == {"role": "user", "content": "Hello"}
    assert transcript[1] == {"role": "assistant", "content": "World"}


def test_skeptic_crewai_llm_tool_call_and_final_answer() -> None:
    """Verify SkepticCrewAILLM translates FakeLLM tool_calls and completions to ReAct strings."""
    scenario = load_scenario(SCENARIO_PATH)
    fake = FakeLLM("oracle_follower", scenario=scenario)
    llm = SkepticCrewAILLM(fake, "fake/oracle_follower")

    # Call 1: FakeLLM returns tool_call -> formatted as ReAct Action
    action_text = llm.call(messages="What is the weather?")
    assert "Action: get_forecast" in action_text
    assert "Action Input:" in action_text

    # Call 2 with Observation -> FakeLLM returns final answer
    messages = [
        {"role": "user", "content": "What is the weather?"},
        {
            "role": "assistant",
            "content": action_text + '\nObservation: {"max_c": 14.5}',
        },
    ]
    final_text = llm.call(messages=messages)
    assert "Final Answer: 14.5" in final_text


@pytest.mark.asyncio
async def test_mcpadapt_start_failure_captured_as_infra_error(tmp_path: Path) -> None:
    """When MCPAdapt fails to initialize, the error is caught and returned as infra error."""
    adapter = CrewAIAdapter()
    server_spec = McpServerSpec(
        name="nonexistent",
        command=["nonexistent_mcp_binary_xyz_123"],
    )
    task = EpisodeTask(
        episode_id="test_ep_fail",
        prompt="Check weather",
        servers=[server_spec],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is not None
    assert "MCPAdapt error" in result.error or "Failed" in result.error
    assert result.final_answer == ""
    assert result.steps == 0


@pytest.mark.asyncio
async def test_max_steps_exceeded_handled_gracefully(tmp_path: Path) -> None:
    """When iterations reach max_steps, final_answer is empty string and error=None."""
    adapter = CrewAIAdapter()
    task = EpisodeTask(
        episode_id="test_ep_max",
        prompt="Endless task",
        servers=[],
        model="fake/oracle_follower",
        max_steps=3,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    mock_result = MagicMock()
    mock_result.raw = "Forced partial answer"
    mock_result.token_usage = MagicMock(
        prompt_tokens=50, completion_tokens=20, successful_requests=4
    )

    mock_agent = MagicMock()
    mock_agent.tools_results = []
    mock_agent.agent_executor = MagicMock(iterations=4)

    with patch("skeptic_agent.runner.adapters.crewai.Crew") as mock_crew_cls:
        mock_crew = mock_crew_cls.return_value
        mock_crew.kickoff.return_value = mock_result

        # Simulate execution
        result = await adapter.run(task)
        assert result.final_answer == ""
        assert result.steps == 3
        assert result.error is None


@pytest.mark.asyncio
async def test_unexpected_runner_exception_returns_error(tmp_path: Path) -> None:
    """Unexpected runtime exceptions during execution are caught as infra errors."""
    adapter = CrewAIAdapter()
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

    with patch("skeptic_agent.runner.adapters.crewai.Crew") as mock_crew_cls:
        mock_crew = mock_crew_cls.return_value
        mock_crew.kickoff.side_effect = RuntimeError("Crew fatal crash")

        result = await adapter.run(task)
        assert result.error is not None
        assert "CrewAI kickoff error: Crew fatal crash" in result.error
        assert result.final_answer == ""


@pytest.mark.asyncio
async def test_clean_text_run_without_tools(tmp_path: Path) -> None:
    """Verify clean execution with no tools on a pure text prompt."""
    adapter = CrewAIAdapter()
    task = EpisodeTask(
        episode_id="test_ep_text",
        prompt="Say hello concisely",
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
    assert result.final_answer != ""
    assert result.steps >= 1
    assert len(result.transcript) >= 2


@pytest.mark.asyncio
async def test_stdio_server_with_echo_fixture(tmp_path: Path) -> None:
    """Verify stdio server connection via MCPAdapt using sandbox server."""
    scenario = load_scenario(SCENARIO_PATH)
    adapter = CrewAIAdapter()
    server_spec = McpServerSpec(
        name="weather",
        command=[sys.executable, "-m", "skeptic_agent.sandboxes.sb_weather"],
    )
    task = EpisodeTask(
        episode_id="test_ep_weather",
        prompt=scenario.prompt,
        servers=[server_spec],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
        scenario=scenario,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.usage.tool_calls >= 1
    assert result.final_answer == "14.5"
