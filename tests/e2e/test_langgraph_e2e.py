"""End-to-end and acceptance tests for LangGraphAdapter (S13, S10, E43)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import jsonschema
import pytest
import yaml

from skeptic_agent.runner.episode import run_episode
from skeptic_agent.runner.llm import get_dev_model

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
async def test_e2e_langgraph_clean_and_s04(tmp_path: Path) -> None:
    """E2E verification of LangGraphAdapter running clean and S04 faulted episodes."""
    clean_out = tmp_path / "run_clean"
    s04_out = tmp_path / "run_s04"

    # 1. Clean episode run
    result_clean = await run_episode(
        SCENARIO_PATH,
        fault_id=None,
        seed=1,
        agent="langgraph:fake/oracle_follower",
        out_dir=clean_out,
    )

    jsonschema.validate(instance=result_clean, schema=RESULT_SCHEMA)
    assert result_clean["outcome"] == "SUCCESS"
    assert result_clean["fault"] is None
    assert result_clean["flags"]["triggered"] is False
    assert result_clean["flags"]["timed_out"] is False
    assert result_clean["final_answer"] == "14.5"
    assert result_clean["usage"]["tool_calls"] >= 1

    clean_cassette = clean_out / "cassettes" / Path(result_clean["cassette"]).name
    assert clean_cassette.is_file(), f"Cassette missing at {clean_cassette}"
    clean_lines = [
        json.loads(line)
        for line in clean_cassette.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(clean_lines) >= 3
    for cl in clean_lines:
        jsonschema.validate(instance=cl, schema=CASSETTE_SCHEMA)

    # 2. S04 faulted episode run
    result_s04 = await run_episode(
        SCENARIO_PATH,
        fault_id="S04",
        seed=1,
        agent="langgraph:fake/oracle_follower",
        out_dir=s04_out,
    )

    jsonschema.validate(instance=result_s04, schema=RESULT_SCHEMA)
    assert result_s04["fault"] == {
        "id": "S04",
        "class": "silent",
        "persistence": "permanent",
    }
    assert result_s04["flags"]["triggered"] is True
    assert result_s04["outcome"] == "SUCCESS"


@pytest.mark.asyncio
async def test_smoke_scenarios_dispatch_offline_langgraph(tmp_path: Path) -> None:
    """Offline dispatch verification of 2 smoke scenarios under langgraph adapter."""
    smoke_suite_file = ROOT_DIR / "bench" / "suites" / "smoke.yaml"
    assert smoke_suite_file.is_file(), f"Smoke suite missing at {smoke_suite_file}"
    suite_data = yaml.safe_load(smoke_suite_file.read_text(encoding="utf-8"))
    scenario_paths = [ROOT_DIR / rel for rel in suite_data.get("scenarios", [])[:2]]

    total_cost: float = 0.0
    for idx, sc_path in enumerate(scenario_paths):
        out_dir = tmp_path / f"offline_smoke_lg_{idx}"
        result = await run_episode(
            sc_path,
            fault_id=None,
            seed=1,
            agent="langgraph:fake/oracle_follower",
            out_dir=out_dir,
        )
        jsonschema.validate(instance=result, schema=RESULT_SCHEMA)
        assert result["outcome"] == "SUCCESS"
        total_cost += float(result.get("usage", {}).get("cost_usd", 0.0))

    assert total_cost < 0.5


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY") or str(os.getenv("OPENROUTER_API_KEY")).startswith("test"),
    reason="Live model test requires valid OPENROUTER_API_KEY",
)
async def test_acceptance_live_dev_model_smoke_scenarios_langgraph(tmp_path: Path) -> None:
    """Acceptance criterion for E43: live test dev model on 2 smoke scenarios (< $0.5)."""
    smoke_suite_file = ROOT_DIR / "bench" / "suites" / "smoke.yaml"
    assert smoke_suite_file.is_file(), f"Smoke suite missing at {smoke_suite_file}"
    suite_data = yaml.safe_load(smoke_suite_file.read_text(encoding="utf-8"))
    scenario_paths = [ROOT_DIR / rel for rel in suite_data.get("scenarios", [])[:2]]

    dev_model = get_dev_model()
    agent_spec = f"langgraph:{dev_model}"
    total_cost: float = 0.0

    for idx, sc_path in enumerate(scenario_paths):
        out_dir = tmp_path / f"live_smoke_lg_{idx}"
        result = await run_episode(
            sc_path,
            fault_id=None,
            seed=1,
            agent=agent_spec,
            out_dir=out_dir,
        )
        jsonschema.validate(instance=result, schema=RESULT_SCHEMA)
        assert result["outcome"] == "SUCCESS"
        cost = float(result.get("usage", {}).get("cost_usd", 0.0))
        total_cost += cost

    assert total_cost < 0.5, f"Total live smoke cost ${total_cost:.4f} exceeded $0.5 budget limit"
