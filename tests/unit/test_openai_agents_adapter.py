"""Unit tests for OpenAIAgentsAdapter (S13.2, S13.4, E42)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from agents.exceptions import MaxTurnsExceeded

from skeptic_agent.runner.adapters import ADAPTERS, get_adapter
from skeptic_agent.runner.adapters.base import EpisodeTask, McpServerSpec
from skeptic_agent.runner.adapters.openai_agents import (
    OpenAIAgentsAdapter,
    _build_transcript,
)
from skeptic_agent.scenario.model import load_scenario

pytestmark = pytest.mark.unit

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"


def test_adapter_registration() -> None:
    """Verify openai-agents is registered in ADAPTERS and conforms to AgentAdapter protocol."""
    assert "openai-agents" in ADAPTERS
    adapter = get_adapter("openai-agents")
    assert isinstance(adapter, OpenAIAgentsAdapter)
    assert adapter.name == "openai-agents"
    assert hasattr(adapter, "run")
    assert callable(adapter.run)


def test_transcript_formatting() -> None:
    """Verify conversion of SDK run items into OpenAI-compatible transcript dictionaries."""

    @dataclass
    class RawToolCall:
        call_id: str = "call_abc_123"
        name: str = "get_forecast"
        arguments: str = '{"city": "Paris"}'

    @dataclass
    class DummyToolCallItem:
        type: str = "tool_call_item"
        raw_item: RawToolCall = field(default_factory=RawToolCall)

    @dataclass
    class DummyToolOutputItem:
        type: str = "tool_call_output_item"
        raw_item: dict[str, str] = field(default_factory=lambda: {"call_id": "call_abc_123"})
        output: dict[str, str] = field(default_factory=lambda: {"text": '{"max_c": 14.5}'})

    @dataclass
    class DummyPart:
        type: str = "output_text"
        text: str = "The temperature is 14.5"

    @dataclass
    class RawMessage:
        content: list[DummyPart] = field(default_factory=lambda: [DummyPart()])

    @dataclass
    class DummyMessageOutputItem:
        type: str = "message_output_item"
        raw_item: RawMessage = field(default_factory=RawMessage)

    new_items = [DummyToolCallItem(), DummyToolOutputItem(), DummyMessageOutputItem()]
    transcript = _build_transcript(
        prompt="Check weather",
        new_items=new_items,
        final_answer="The temperature is 14.5",
    )

    assert len(transcript) == 4
    assert transcript[0] == {"role": "user", "content": "Check weather"}
    assert transcript[1]["role"] == "assistant"
    assert transcript[1]["tool_calls"][0]["id"] == "call_abc_123"
    assert transcript[1]["tool_calls"][0]["function"]["name"] == "get_forecast"
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
    """If no message output item was emitted, final_answer is added as an assistant turn."""
    transcript = _build_transcript(
        prompt="Hello",
        new_items=[],
        final_answer="World",
    )
    assert transcript == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "World"},
    ]


@pytest.mark.asyncio
async def test_server_failure_returns_infra_error(tmp_path: Path) -> None:
    """If an MCP server fails to launch, run returns AgentRunResult with error set."""
    adapter = OpenAIAgentsAdapter()
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
        timeout_s=10,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is not None
    assert "Failed to start MCP server failing_server" in result.error
    assert result.final_answer == ""
    assert result.steps == 0


@pytest.mark.asyncio
async def test_runner_max_turns_exceeded_handled_gracefully(tmp_path: Path) -> None:
    """When MaxTurnsExceeded is raised, final_answer is empty string per S13.3 without error."""
    adapter = OpenAIAgentsAdapter()
    task = EpisodeTask(
        episode_id="test_ep_turns",
        prompt="Loop forever",
        servers=[],
        model="fake/oracle_follower",
        max_steps=3,
        timeout_s=10,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    with patch("agents.Runner.run", side_effect=MaxTurnsExceeded("Max turns (3) exceeded")):
        result = await adapter.run(task)

    assert result.error is None
    assert result.final_answer == ""
    assert result.steps == 3


@pytest.mark.asyncio
async def test_runner_unexpected_exception_returns_error(tmp_path: Path) -> None:
    """When Runner.run raises an unexpected Exception, result has error populated."""
    adapter = OpenAIAgentsAdapter()
    task = EpisodeTask(
        episode_id="test_ep_err",
        prompt="Crash",
        servers=[],
        model="fake/oracle_follower",
        max_steps=3,
        timeout_s=10,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    with patch("agents.Runner.run", side_effect=RuntimeError("Unexpected SDK crash")):
        result = await adapter.run(task)

    assert result.error is not None
    assert "OpenAI agents runner error: Unexpected SDK crash" in result.error
    assert result.final_answer == ""


@pytest.mark.asyncio
async def test_fake_llm_execution_no_servers(tmp_path: Path) -> None:
    """FakeLLM directly generates a text completion when scenario has no oracle steps."""
    adapter = OpenAIAgentsAdapter()
    task = EpisodeTask(
        episode_id="test_ep_fake",
        prompt="What is the forecast?",
        servers=[],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=10,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
        scenario=None,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "No oracle scenario available."
    assert len(result.transcript) >= 2
    assert result.usage.steps >= 1


@pytest.mark.asyncio
async def test_adapter_with_mcp_server(tmp_path: Path) -> None:
    """OpenAIAgentsAdapter executes oracle tool calls through a wrapped MCP server."""
    scenario = load_scenario(SCENARIO_PATH)
    adapter = OpenAIAgentsAdapter()
    server_spec = McpServerSpec(
        name="sb_weather",
        command=[sys.executable, "-m", "skeptic_agent.sandboxes.sb_weather"],
        env={"SKEPTIC_FROZEN_NOW": "2026-11-01T09:00:00Z"},
    )
    task = EpisodeTask(
        episode_id="test_ep_weather",
        prompt="What will the maximum temperature in Paris be on 2026-11-02?",
        servers=[server_spec],
        model="fake/oracle_follower",
        max_steps=5,
        timeout_s=20,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
        scenario=scenario,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "14.5"
    assert result.usage.tool_calls >= 1
    assert any(m.get("role") == "tool" for m in result.transcript)


@pytest.mark.asyncio
async def test_model_settings_routing_openrouter_extra_body(tmp_path: Path) -> None:
    """OpenRouter models configure extra_body={"usage": {"include": True}} in ModelSettings."""
    adapter = OpenAIAgentsAdapter()
    task = EpisodeTask(
        episode_id="test_ep_or",
        prompt="Hi",
        servers=[],
        model="openrouter/openai/gpt-4o-mini",
        max_steps=2,
        timeout_s=5,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    captured_agent: list[Any] = []

    async def fake_runner_run(agent: Any, **kwargs: Any) -> Any:
        captured_agent.append(agent)

        @dataclass
        class FakeRes:
            final_output: str = "Done"
            raw_responses: list[Any] = field(default_factory=list)
            new_items: list[Any] = field(default_factory=list)

        return FakeRes()

    with patch("agents.Runner.run", side_effect=fake_runner_run):
        await adapter.run(task)

    assert len(captured_agent) == 1
    agent_inst = captured_agent[0]
    assert agent_inst.model_settings.extra_body == {"usage": {"include": True}}
    # Instructions and prompt must remain framework defaults (S13.4)
    assert agent_inst.instructions is None
    assert agent_inst.prompt is None
