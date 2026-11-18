"""Unit tests for the scratch-root resolver (CI313)."""

import tempfile
from pathlib import Path

import pytest

from skeptic_agent.runner.adapters.base import AgentAdapter, AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.episode import run_episode
from skeptic_agent.tmpdir import TMP_ENV, resolve_tmp_dir

pytestmark = pytest.mark.unit

SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "scenarios"
    / "weather.forecast.max-temp.001.yaml"
)


class _MockAdapter(AgentAdapter):
    """Instant adapter that answers without touching a model."""

    name: str = "tmpdir_mock"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        return AgentRunResult(
            final_answer="ANSWER: Paris max temp is 22C",
            usage=Usage(tokens_in=1, tokens_out=1, steps=1),
            transcript=[],
            steps=1,
        )


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``SKEPTIC_TMP`` names the scratch root."""
    monkeypatch.setenv(TMP_ENV, str(tmp_path / "scratch"))
    assert resolve_tmp_dir() == tmp_path / "scratch"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_env_falls_back_to_system_temp(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """An empty or blank variable counts as unset."""
    monkeypatch.setenv(TMP_ENV, value)
    assert resolve_tmp_dir() == Path(tempfile.gettempdir()) / "skeptic"


def test_default_ignores_a_checkout_in_the_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ``bench`` directory in the cwd no longer sends scratch files to ``./.tmp``."""
    monkeypatch.delenv(TMP_ENV, raising=False)
    (tmp_path / "bench").mkdir()
    monkeypatch.chdir(tmp_path)
    resolved = resolve_tmp_dir()
    assert resolved == Path(tempfile.gettempdir()) / "skeptic"
    assert tmp_path not in resolved.parents


def test_resolver_does_not_create_the_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Resolving is pure; the caller creates the directory."""
    target = tmp_path / "later"
    monkeypatch.setenv(TMP_ENV, str(target))
    resolve_tmp_dir()
    assert not target.exists()


@pytest.mark.asyncio
async def test_run_episode_workdir_lands_under_env_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without an explicit workdir, the episode directory is created under ``SKEPTIC_TMP``."""
    root = tmp_path / "root"
    cwd = tmp_path / "checkout"
    (cwd / "bench").mkdir(parents=True)
    monkeypatch.setenv(TMP_ENV, str(root))
    monkeypatch.delenv("SKEPTIC_EPISODE_TIMEOUT_S", raising=False)
    monkeypatch.chdir(cwd)
    adapter = _MockAdapter()
    await run_episode(SCENARIO_PATH, adapter=adapter, out_dir=tmp_path / "out")
    assert [p.name.startswith("ep_") for p in root.iterdir()] == [True]
    assert not (cwd / ".tmp").exists()
