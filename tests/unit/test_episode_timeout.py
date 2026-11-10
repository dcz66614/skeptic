"""Unit tests for episode timeout override and CLI/env configuration (L71fix).

Tests cover:
- Default timeout remains 180 (scenario default) when no override is set.
- Explicit parameter override in run_episode, execute_run, and execute_matrix.
- Environment variable SKEPTIC_EPISODE_TIMEOUT_S override when parameter is omitted.
- Explicit parameter takes precedence over environment variable.
- Invalid timeout values (< 1, > 1800, non-integer) are rejected with ValueError or exit code 2.
- CLI 'skeptic run' and 'skeptic bench run' apply --episode-timeout-s and env override.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.runner.adapters.base import AgentAdapter, AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.episode import resolve_episode_timeout, run_episode
from skeptic_agent.runner.matrix import execute_matrix, execute_run

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SCENARIO_PATH = FIXTURES_DIR / "scenarios" / "weather.forecast.max-temp.001.yaml"
MATRIX_PATH = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-free-hy3.yaml"


class RecordingMockAdapter(AgentAdapter):
    """Fast in-memory adapter that records the EpisodeTask passed to run()."""

    name: str = "recording_mock"

    def __init__(self) -> None:
        self.recorded_task: EpisodeTask | None = None

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        self.recorded_task = task
        return AgentRunResult(
            final_answer="ANSWER: Paris max temp is 22C",
            usage=Usage(tokens_in=10, tokens_out=5, steps=1),
            transcript=[],
            steps=1,
        )


def test_resolve_episode_timeout_defaults_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no override or env is provided, resolve_episode_timeout returns None."""
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    assert resolve_episode_timeout(None) is None
    assert resolve_episode_timeout() is None


@pytest.mark.parametrize("valid_val", [1, 60, 180, 900, 1800, "900", "1800"])
def test_resolve_episode_timeout_valid_values(valid_val: int | str) -> None:
    """Valid integer values between 1 and 1800 are accepted and returned as ints."""
    assert resolve_episode_timeout(valid_val) == int(valid_val)


def test_resolve_episode_timeout_env_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """SKEPTIC_EPISODE_TIMEOUT_S is honoured when override is None."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", "900")
    assert resolve_episode_timeout(None) == 900

    # Explicit override takes precedence over env
    assert resolve_episode_timeout(300) == 300


@pytest.mark.parametrize("invalid_val", [0, -1, -500, 1801, 2000, 99999, "not-an-int", "12.5"])
def test_resolve_episode_timeout_invalid_rejected(invalid_val: Any) -> None:
    """Values < 1, > 1800, or non-integers raise ValueError."""
    with pytest.raises(ValueError, match="timeout"):
        resolve_episode_timeout(invalid_val)


@pytest.mark.parametrize("bad_env", ["0", "-1", "1801", "abc", ""])
def test_resolve_episode_timeout_invalid_env_rejected(
    monkeypatch: pytest.MonkeyPatch, bad_env: str
) -> None:
    """Invalid environment variable values raise ValueError (empty string returns None)."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", bad_env)
    if not bad_env:
        assert resolve_episode_timeout(None) is None
    else:
        with pytest.raises(ValueError, match="timeout"):
            resolve_episode_timeout(None)


@pytest.mark.asyncio
async def test_run_episode_default_timeout_180(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no override is provided, scenario default (180s) is retained."""
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    adapter = RecordingMockAdapter()
    result = await run_episode(
        SCENARIO_PATH,
        adapter=adapter,
        out_dir=tmp_path,
        workdir=tmp_path / "workdir",
    )
    assert adapter.recorded_task is not None
    assert adapter.recorded_task.timeout_s == 180
    assert result["outcome"] in ("SUCCESS", "FALSE_SUCCESS")


@pytest.mark.asyncio
async def test_run_episode_parameter_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing episode_timeout_s overrides the scenario timeout."""
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    adapter = RecordingMockAdapter()
    await run_episode(
        SCENARIO_PATH,
        adapter=adapter,
        out_dir=tmp_path,
        workdir=tmp_path / "workdir",
        episode_timeout_s=900,
    )
    assert adapter.recorded_task is not None
    assert adapter.recorded_task.timeout_s == 900


@pytest.mark.asyncio
async def test_run_episode_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting env SKEPTIC_EPISODE_TIMEOUT_S overrides scenario timeout when unset."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", "600")
    adapter = RecordingMockAdapter()
    await run_episode(
        SCENARIO_PATH,
        adapter=adapter,
        out_dir=tmp_path,
        workdir=tmp_path / "workdir",
    )
    assert adapter.recorded_task is not None
    assert adapter.recorded_task.timeout_s == 600


@pytest.mark.asyncio
async def test_run_episode_invalid_timeout_rejected(tmp_path: Path) -> None:
    """Passing an invalid timeout to run_episode raises ValueError."""
    adapter = RecordingMockAdapter()
    with pytest.raises(ValueError, match="between 1 and 1800"):
        await run_episode(
            SCENARIO_PATH,
            adapter=adapter,
            out_dir=tmp_path,
            workdir=tmp_path / "workdir",
            episode_timeout_s=0,
        )


@pytest.mark.asyncio
async def test_execute_run_threads_episode_timeout(tmp_path: Path) -> None:
    """execute_run forwards episode_timeout_s to run_episode."""
    with patch("skeptic_agent.runner.matrix.run_episode", new_callable=AsyncMock) as mock_ep:
        mock_ep.return_value = {
            "schema": "skeptic.result/v1",
            "run_id": "20261110-120000-abcdef",
            "episode_id": "20261110-120000-abcdef:weather.forecast.paris-max.001:clean:1",
            "scenario_id": "weather.forecast.paris-max.001",
            "sandbox": "sb_weather",
            "language": "en",
            "kind": "read_only",
            "fault": None,
            "recoverability": "unaffected",
            "agent": {
                "adapter": "reference",
                "model": "fake/oracle_follower",
                "prompt_variant": "plain",
                "guards": [],
            },
            "seed": 1,
            "outcome": "SUCCESS",
            "flags": {},
            "checks": [],
            "forbid_hits": [],
            "final_answer": "done",
            "usage": {
                "tokens_in": 10,
                "tokens_out": 5,
                "cost_usd": 0.0,
                "latency_s": 0.1,
                "steps": 1,
                "tool_calls": 0,
            },
            "cassette": "cassettes/test.jsonl",
            "error": None,
        }
        await execute_run(
            scenarios=[SCENARIO_PATH],
            agent="reference:fake/oracle_follower",
            profile="silent-core",
            guards="none",
            out_dir=tmp_path,
            episode_timeout_s=900,
        )
        assert mock_ep.called
        assert mock_ep.call_args.kwargs.get("episode_timeout_s") == 900


@pytest.mark.asyncio
async def test_execute_matrix_threads_episode_timeout(tmp_path: Path) -> None:
    """execute_matrix forwards episode_timeout_s to execute_run."""
    with patch("skeptic_agent.runner.matrix.execute_run", new_callable=AsyncMock) as mock_exec_run:
        mock_exec_run.return_value = {
            "schema": "skeptic.report/v1",
            "run_id": "test-matrix-run",
            "matrix_id": "leaderboard-v1-reduced-free-hy3",
            "episodes": [],
            "agents": [],
        }
        await execute_matrix(
            MATRIX_PATH,
            out_dir=tmp_path,
            episode_timeout_s=1200,
        )
        assert mock_exec_run.called
        for call in mock_exec_run.call_args_list:
            assert call.kwargs.get("episode_timeout_s") == 1200


def test_cli_run_accepts_episode_timeout_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """skeptic run accepts --episode-timeout-s and forwards it to execute_run."""
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    runner = CliRunner()
    captured_timeout: int | None = None

    async def fake_execute_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_timeout
        captured_timeout = kwargs.get("episode_timeout_s")
        return {"agents": [{"metrics": {"SKS": {"estimate": 0.95}}}], "episodes": [1]}

    with patch("skeptic_agent.runner.matrix.execute_run", side_effect=fake_execute_run):
        result = runner.invoke(
            app,
            [
                "run",
                "--scenario",
                str(SCENARIO_PATH),
                "--episode-timeout-s",
                "900",
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured_timeout == 900


def test_cli_run_honours_env_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """skeptic run honours SKEPTIC_EPISODE_TIMEOUT_S when flag is omitted."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", "750")
    runner = CliRunner()
    captured_timeout: int | None = None

    async def fake_execute_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal captured_timeout
        captured_timeout = kwargs.get("episode_timeout_s")
        return {"agents": [{"metrics": {"SKS": {"estimate": 0.95}}}], "episodes": [1]}

    with patch("skeptic_agent.runner.matrix.execute_run", side_effect=fake_execute_run):
        result = runner.invoke(
            app,
            [
                "run",
                "--scenario",
                str(SCENARIO_PATH),
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured_timeout == 750


@pytest.mark.parametrize("invalid_arg", ["0", "-10", "1801", "3600", "not-a-number"])
def test_cli_run_rejects_invalid_episode_timeout(invalid_arg: str) -> None:
    """skeptic run rejects invalid --episode-timeout-s with code 2."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            "--scenario",
            str(SCENARIO_PATH),
            "--episode-timeout-s",
            invalid_arg,
        ],
    )
    assert result.exit_code == 2


def test_cli_run_rejects_invalid_env_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """skeptic run rejects invalid SKEPTIC_EPISODE_TIMEOUT_S with code 2."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", "2500")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            "--scenario",
            str(SCENARIO_PATH),
        ],
    )
    assert result.exit_code == 2


def test_cli_bench_run_accepts_episode_timeout_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """skeptic bench run accepts --episode-timeout-s and forwards it to execute_matrix."""
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    runner = CliRunner()
    captured_timeout: int | None = None

    async def fake_execute_matrix(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal captured_timeout
        captured_timeout = kwargs.get("episode_timeout_s")
        return [{"run_id": "test"}]

    with patch("skeptic_agent.runner.matrix.execute_matrix", side_effect=fake_execute_matrix):
        result = runner.invoke(
            app,
            [
                "bench",
                "run",
                "--matrix",
                str(MATRIX_PATH),
                "--episode-timeout-s",
                "900",
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured_timeout == 900


def test_cli_bench_run_honours_env_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """skeptic bench run honours SKEPTIC_EPISODE_TIMEOUT_S when flag is omitted."""
    monkeypatch.setenv("SKEPTIC_EPISODE_TIMEOUT_S", "850")
    runner = CliRunner()
    captured_timeout: int | None = None

    async def fake_execute_matrix(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal captured_timeout
        captured_timeout = kwargs.get("episode_timeout_s")
        return [{"run_id": "test"}]

    with patch("skeptic_agent.runner.matrix.execute_matrix", side_effect=fake_execute_matrix):
        result = runner.invoke(
            app,
            [
                "bench",
                "run",
                "--matrix",
                str(MATRIX_PATH),
            ],
        )
        assert result.exit_code == 0, result.output
        assert captured_timeout == 850


@pytest.mark.parametrize("invalid_arg", ["0", "-5", "1801", "not-a-number"])
def test_cli_bench_run_rejects_invalid_episode_timeout(invalid_arg: str) -> None:
    """skeptic bench run rejects invalid --episode-timeout-s with code 2."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "bench",
            "run",
            "--matrix",
            str(MATRIX_PATH),
            "--episode-timeout-s",
            invalid_arg,
        ],
    )
    assert result.exit_code == 2
