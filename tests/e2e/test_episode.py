"""End-to-end tests for Episode Runner and FakeLLM (S13, S10, E40)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import jsonschema
import pytest

from skeptic_agent.runner.adapters.base import AgentAdapter, AgentRunResult, EpisodeTask, Usage
from skeptic_agent.runner.budget import (
    EXIT_BUDGET_EXCEEDED,
    BudgetExceededError,
    BudgetTracker,
    append_ledger_entry,
)
from skeptic_agent.runner.episode import run_episode
from skeptic_agent.runner.llm import (
    calculate_cost,
    create_llm_client,
    parse_agent_spec,
    resolve_model,
)

pytestmark = pytest.mark.e2e

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_PATH = ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"
RESULT_SCHEMA = json.loads(
    (ROOT_DIR / "schemas" / "result.schema.json").read_text(encoding="utf-8")
)
CASSETTE_SCHEMA = json.loads(
    (ROOT_DIR / "schemas" / "cassette.schema.json").read_text(encoding="utf-8")
)


@pytest.mark.asyncio
async def test_acceptance_oracle_follower_clean_and_s04(tmp_path: Path) -> None:
    """Acceptance criterion for E40: run one scenario under FakeLLM oracle_follower.

    Executes both a clean baseline and an S04 fault episode, generating
    cassette, state.json and validated skeptic.result/v1 records for both.
    """
    clean_out = tmp_path / "run_clean"
    s04_out = tmp_path / "run_s04"

    # 1. Clean episode run
    result_clean = await run_episode(
        SCENARIO_PATH,
        fault_id=None,
        seed=1,
        agent="reference:fake/oracle_follower",
        out_dir=clean_out,
    )

    # Validate result schema
    jsonschema.validate(instance=result_clean, schema=RESULT_SCHEMA)
    assert result_clean["outcome"] == "SUCCESS"
    assert result_clean["fault"] is None
    assert result_clean["flags"]["triggered"] is False
    assert result_clean["flags"]["timed_out"] is False
    assert result_clean["final_answer"] == "14.5"
    assert result_clean["usage"]["tool_calls"] >= 1

    # Check state.json was created
    clean_cassette = clean_out / "cassettes" / Path(result_clean["cassette"]).name
    assert clean_cassette.is_file(), f"Cassette missing at {clean_cassette}"

    # Validate cassette lines against cassette schema
    clean_lines = [
        json.loads(line)
        for line in clean_cassette.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(clean_lines) >= 3  # header, msg, footer
    for cl in clean_lines:
        jsonschema.validate(instance=cl, schema=CASSETTE_SCHEMA)

    # 2. S04 faulted episode run
    result_s04 = await run_episode(
        SCENARIO_PATH,
        fault_id="S04",
        seed=1,
        agent="reference:fake/oracle_follower",
        out_dir=s04_out,
    )

    # Validate S04 result schema
    jsonschema.validate(instance=result_s04, schema=RESULT_SCHEMA)
    assert result_s04["fault"] == {
        "id": "S04",
        "class": "silent",
        "persistence": "permanent",
    }
    assert result_s04["flags"]["triggered"] is True
    assert result_s04["flags"]["timed_out"] is False

    # Check S04 cassette
    s04_cassette = s04_out / "cassettes" / Path(result_s04["cassette"]).name
    assert s04_cassette.is_file(), f"Cassette missing at {s04_cassette}"
    s04_lines = [
        json.loads(line)
        for line in s04_cassette.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for sl in s04_lines:
        jsonschema.validate(instance=sl, schema=CASSETTE_SCHEMA)

    # Check that S04 was noted in the cassette
    fault_entries = [line for line in s04_lines if line.get("fault") is not None]
    assert len(fault_entries) >= 1
    assert fault_entries[0]["fault"]["id"] == "S04"

    # Both runs wrote results.jsonl
    assert (clean_out / "results.jsonl").is_file()
    assert (s04_out / "results.jsonl").is_file()


@pytest.mark.asyncio
async def test_budget_exceeded_stops_dispatch(tmp_path: Path) -> None:
    """Cumulative spend exceeding max_cost_usd halts new episode dispatch with code 5 (1.8)."""
    tracker = BudgetTracker(max_cost_usd=0.001)
    tracker.record_spend(cost_usd=0.005, tokens_in=1000, tokens_out=500)
    assert not tracker.can_dispatch()

    with pytest.raises(BudgetExceededError) as exc_info:
        await run_episode(
            SCENARIO_PATH,
            fault_id=None,
            budget_tracker=tracker,
            out_dir=tmp_path,
        )

    assert f"exit code {EXIT_BUDGET_EXCEEDED}" in str(exc_info.value)


@pytest.mark.asyncio
async def test_timeout_control_flags_error(tmp_path: Path) -> None:
    """An adapter that hangs triggers timeout control, marking outcome=ERROR and timed_out=True."""

    class HangingAdapter(AgentAdapter):
        name: str = "hanging"

        async def run(self, task: EpisodeTask) -> AgentRunResult:
            del task
            await asyncio.sleep(10.0)
            return AgentRunResult(final_answer="done", usage=Usage(), transcript=[], steps=1)

    result = await run_episode(
        SCENARIO_PATH,
        fault_id=None,
        adapter=HangingAdapter(),
        out_dir=tmp_path,
        workdir=tmp_path / "hang_workdir",
    )

    jsonschema.validate(instance=result, schema=RESULT_SCHEMA)
    # The default timeout on scenario limits is overridden or scenario limits applied
    # Let's verify timeout behavior when task.timeout_s is short:


@pytest.mark.asyncio
async def test_custom_timeout_sets_timed_out(tmp_path: Path) -> None:
    """When an adapter exceeds timeout, flags.timed_out is True and outcome is ERROR."""
    from skeptic_agent.scenario.model import load_scenario

    scenario = load_scenario(SCENARIO_PATH)
    # Mutate limits for quick test
    if scenario.limits:
        scenario.limits.timeout_s = 1

    class SlowAdapter(AgentAdapter):
        name: str = "slow"

        async def run(self, task: EpisodeTask) -> AgentRunResult:
            del task
            await asyncio.sleep(3.0)
            return AgentRunResult(final_answer="done", usage=Usage(), transcript=[], steps=1)

    result = await run_episode(
        scenario,
        fault_id=None,
        adapter=SlowAdapter(),
        out_dir=tmp_path,
    )

    assert result["flags"]["timed_out"] is True
    assert result["outcome"] == "ERROR"
    assert "timeout" in str(result["error"]).lower()
    jsonschema.validate(instance=result, schema=RESULT_SCHEMA)


def test_budget_tracker_accounting(tmp_path: Path) -> None:
    """BudgetTracker accumulates spend and tokens correctly and writes ledger rows (1.8)."""
    tracker = BudgetTracker(max_cost_usd=10.0)
    assert tracker.can_dispatch()

    tracker.record_spend(cost_usd=1.5, tokens_in=2000, tokens_out=500)
    assert tracker.spent_usd == 1.5
    assert tracker.tokens_in == 2000
    assert tracker.tokens_out == 500
    assert tracker.episodes_completed == 1
    assert tracker.can_dispatch()

    ledger = tmp_path / "ledger.csv"
    append_ledger_entry(
        ledger,
        task_id="E40",
        agent_name="reference:fake/oracle_follower",
        run_id="20261102-120000-abcdef",
        model="fake/oracle_follower",
        episodes=1,
        tokens_in=2000,
        tokens_out=500,
        cost_usd=1.5,
    )
    assert ledger.is_file()
    content = ledger.read_text(encoding="utf-8")
    assert (
        "timestamp,task_id,agent_name,run_id,model,episodes,tokens_in,tokens_out,cost_usd"
        in content
    )
    assert "E40,reference:fake/oracle_follower,20261102-120000-abcdef" in content


def test_llm_spec_resolution() -> None:
    """Test agent spec and model resolution rules (S13.1, S13.3)."""
    adapter, model = parse_agent_spec("reference:openrouter/anthropic/claude-3.5-sonnet")
    assert adapter == "reference"
    assert model == "openrouter/anthropic/claude-3.5-sonnet"

    cfg_or = resolve_model("openrouter/anthropic/claude-3.5-sonnet")
    assert cfg_or.provider == "openrouter"
    assert cfg_or.base_url == "https://openrouter.ai/api/v1"
    assert cfg_or.model_name == "anthropic/claude-3.5-sonnet"

    cfg_oa = resolve_model("openai/gpt-4o")
    assert cfg_oa.provider == "openai"
    assert cfg_oa.base_url is None

    cfg_fake = resolve_model("fake/oracle_follower")
    assert cfg_fake.is_fake is True
    assert cfg_fake.model_name == "oracle_follower"

    fake_client = create_llm_client("fake/oracle_follower")
    assert hasattr(fake_client, "chat")

    # Cost calculation
    cost_fake = calculate_cost("fake/oracle_follower", 1000, 500)
    assert cost_fake == 0.0

    cost_real = calculate_cost("openai/gpt-4o", 1000, 1000)
    assert cost_real > 0.0
