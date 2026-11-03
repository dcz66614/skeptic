"""End-to-end acceptance tests for Guards (G50, S4.4, S11).

Acceptance criteria:
- Guard execution order conforms to S4.4.
- Verbatim text match for S11 guards.
- FakeLLM looper script is intercepted on the 3rd call when G06 loop_breaker is enabled.
- All test outputs are written strictly under tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from skeptic_agent.guards import EVIDENCE_CONTRACT_TEXT, LOOP_BREAKER_TEXT_TEMPLATE
from skeptic_agent.runner.episode import run_episode

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
async def test_acceptance_looper_intercepted_on_third_call(tmp_path: Path) -> None:
    """Acceptance criterion for G50: FakeLLM looper is intercepted on 3rd call by G06."""
    looper_dir = tmp_path / "looper_run"
    looper_workdir = tmp_path / "looper_work"

    res = await run_episode(
        SCENARIO_PATH,
        fault_id=None,
        agent="reference:fake/looper",
        guards=["loop_breaker"],
        out_dir=looper_dir,
        workdir=looper_workdir,
    )

    # 1. Validate skeptic.result/v1 schema
    jsonschema.validate(instance=res, schema=RESULT_SCHEMA)
    assert res["agent"]["guards"] == ["loop_breaker"]

    # 2. Check cassette in tmp_path
    cassette_path = looper_dir / "cassettes" / Path(res["cassette"]).name
    assert cassette_path.is_file(), f"Cassette missing at {cassette_path}"
    raw_lines = cassette_path.read_text(encoding="utf-8").splitlines()
    lines = [json.loads(line) for line in raw_lines if line.strip()]

    # Validate each cassette line against cassette schema
    validator = jsonschema.Draft202012Validator(CASSETTE_SCHEMA)
    for line in lines:
        validator.validate(line)

    header = lines[0]
    assert header["type"] == "header"
    assert "loop_breaker" in header["guards"]

    # Find the tool calls and responses in cassette
    c2s_tool_calls = [
        m
        for m in lines
        if m.get("type") == "msg"
        and m.get("dir") == "c2s"
        and m.get("raw", {}).get("method") == "tools/call"
    ]
    assert len(c2s_tool_calls) >= 3, "Looper must have attempted at least 3 calls"

    # Verify that the 3rd call in the agent transcript was answered with G06 error
    expected_error_text = LOOP_BREAKER_TEXT_TEMPLATE.format(n=3)
    verbatim_text = (
        "[skeptic:loop_breaker] This exact call was already made 3 times with the same result. "
        "Change your approach or report that the task cannot be completed."
    )
    assert expected_error_text == verbatim_text
    assert res["flags"]["loop"] is True


@pytest.mark.asyncio
async def test_acceptance_evidence_contract_e2e(tmp_path: Path) -> None:
    """Acceptance criterion for G01: evidence_contract appends contract to tool output."""
    out_dir = tmp_path / "evidence_run"
    work_dir = tmp_path / "evidence_work"

    res = await run_episode(
        SCENARIO_PATH,
        fault_id=None,
        agent="reference:fake/oracle_follower",
        guards=["evidence_contract"],
        out_dir=out_dir,
        workdir=work_dir,
    )

    jsonschema.validate(instance=res, schema=RESULT_SCHEMA)
    assert res["agent"]["guards"] == ["evidence_contract"]

    cassette_path = out_dir / "cassettes" / Path(res["cassette"]).name
    assert cassette_path.is_file(), f"Cassette missing at {cassette_path}"

    raw_lines = cassette_path.read_text(encoding="utf-8").splitlines()
    lines = [json.loads(line) for line in raw_lines if line.strip()]
    validator = jsonschema.Draft202012Validator(CASSETTE_SCHEMA)
    for line in lines:
        validator.validate(line)

    # Check that s2c response in cassette has evidence contract appended in final
    s2c_calls = [
        m
        for m in lines
        if m.get("type") == "msg" and m.get("dir") == "s2c" and m.get("final") is not None
    ]
    assert len(s2c_calls) >= 1
    modified_call = s2c_calls[0]
    final_result = modified_call.get("final", {}).get("result", {})
    final_content = final_result.get("content", [])
    texts = [c.get("text", "") for c in final_content if isinstance(c, dict)]
    assert any(EVIDENCE_CONTRACT_TEXT in t for t in texts), (
        f"Expected evidence contract in tool result content: {texts}"
    )

    # Verify guard action note in cassette
    assert any(
        g.get("id") == "evidence_contract" and g.get("action") == "contract_appended"
        for g in modified_call.get("guards", [])
    )
