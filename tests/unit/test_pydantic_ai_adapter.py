"""Unit tests for PydanticAIAdapter (S13.2, S13.4, E44)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart

from skeptic_agent.runner.adapters import ADAPTERS, get_adapter
from skeptic_agent.runner.adapters.base import EpisodeTask, McpServerSpec
from skeptic_agent.runner.adapters.pydantic_ai import (
    PydanticAIAdapter,
    _build_transcript,
)
from skeptic_agent.scenario.model import load_scenario

pytestmark = pytest.mark.unit

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"


def test_adapter_registration() -> None:
    """Verify pydantic-ai is registered in ADAPTERS and conforms to AgentAdapter protocol."""
    assert "pydantic-ai" in ADAPTERS
    adapter = get_adapter("pydantic-ai")
    assert isinstance(adapter, PydanticAIAdapter)
    assert adapter.name == "pydantic-ai"
    assert hasattr(adapter, "run")
    assert callable(adapter.run)


def test_transcript_formatting() -> None:
    """Verify conversion of PydanticAI messages into standard OpenAI transcript messages."""
    req1 = ModelRequest(parts=[TextPart(content="Check weather")])
    resp1 = ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="get_forecast",
                args={"city": "Paris"},
                tool_call_id="call_abc_123",
            )
        ]
    )
    req2 = ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name="get_forecast",
                content='{"max_c": 14.5}',
                tool_call_id="call_abc_123",
            )
        ]
    )
    resp2 = ModelResponse(parts=[TextPart(content="The temperature is 14.5")])

    transcript = _build_transcript(
        prompt="Check weather",
        messages=[req1, resp1, req2, resp2],
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
    """When no messages were captured, transcript includes user prompt and final answer."""
    transcript = _build_transcript(
        prompt="Hello",
        messages=[],
        final_answer="World",
    )
    assert len(transcript) == 2
    assert transcript[0] == {"role": "user", "content": "Hello"}
    assert transcript[1] == {"role": "assistant", "content": "World"}


@pytest.mark.asyncio
async def test_mcp_server_start_failure_captured_as_infra_error(tmp_path: Path) -> None:
    """When MCP server fails to start, the error is caught and returned as infra error."""
    adapter = PydanticAIAdapter()
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
    assert "Failed to start MCP server" in result.error
    assert result.final_answer == ""
    assert result.steps == 0


@pytest.mark.asyncio
async def test_usage_limit_exceeded_handled_gracefully(tmp_path: Path) -> None:
    """When UsageLimitExceeded is raised, final_answer is empty string and error=None."""
    adapter = PydanticAIAdapter()
    task = EpisodeTask(
        episode_id="test_ep_limit",
        prompt="Endless task",
        servers=[],
        model="fake/oracle_follower",
        max_steps=4,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    with patch("skeptic_agent.runner.adapters.pydantic_ai.Agent") as mock_agent_cls:
        mock_agent = mock_agent_cls.return_value
        mock_agent.run = AsyncMock(side_effect=UsageLimitExceeded("The request limit was exceeded"))

        result = await adapter.run(task)
        assert result.final_answer == ""
        assert result.steps == 4
        assert result.error is None


@pytest.mark.asyncio
async def test_unexpected_runner_exception_returns_error(tmp_path: Path) -> None:
    """Unexpected runtime exceptions during execution are caught as infra errors."""
    adapter = PydanticAIAdapter()
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

    with patch("skeptic_agent.runner.adapters.pydantic_ai.Agent") as mock_agent_cls:
        mock_agent = mock_agent_cls.return_value
        mock_agent.run = AsyncMock(side_effect=RuntimeError("PydanticAI internal crash"))

        result = await adapter.run(task)
        assert result.error is not None
        assert "PydanticAI runner error: PydanticAI internal crash" in result.error
        assert result.final_answer == ""


@pytest.mark.asyncio
async def test_clean_text_run_without_tools(tmp_path: Path) -> None:
    """Verify clean execution with no tools on a pure text prompt."""
    scenario = load_scenario(SCENARIO_PATH)
    adapter = PydanticAIAdapter()
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
        scenario=scenario,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer != ""
    assert result.steps >= 1
    assert len(result.transcript) >= 2


@pytest.mark.asyncio
async def test_stdio_server_with_echo_fixture(tmp_path: Path) -> None:
    """Verify stdio server connection via MCPToolset using echo fixture."""
    scenario = load_scenario(SCENARIO_PATH)
    adapter = PydanticAIAdapter()
    server_spec = McpServerSpec(
        name="echo",
        command=[sys.executable, str(ROOT_DIR / "tests" / "fixtures" / "echo_server.py")],
    )
    task = EpisodeTask(
        episode_id="test_ep_echo",
        prompt="Echo test",
        servers=[server_spec],
        model="fake/oracle_follower",
        max_steps=3,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
        scenario=scenario,
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.steps >= 1
