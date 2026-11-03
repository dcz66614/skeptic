"""End-to-end acceptance tests for G51 Guards (G51, S4.4, S11).

Acceptance criteria:
- S01, S02, S03, S04 (when exceeding outputSchema range), and S07 faults are loudified
  when the corresponding Guard is enabled.
- Normal results are unaffected: clean Oracle runs across all sandboxes pass 100%
  under the 'all' guards preset.
- All test outputs are written strictly under tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from skeptic_agent.guards import (
    EMPTINESS_GUARD_TEXT,
    EmptinessGuard,
    GuardSpec,
    SchemaGuard,
)
from skeptic_agent.jsonrpc import Response
from skeptic_agent.protocol import UNKNOWN
from skeptic_agent.proxy.context import EpisodeContext, PendingCall
from skeptic_agent.proxy.pipeline import C2S
from skeptic_agent.runner.episode import run_episode
from skeptic_agent.scenario.oracle import run_oracle

pytestmark = pytest.mark.e2e

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENARIO_WEATHER = (
    ROOT_DIR / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"
)
RESULT_SCHEMA = json.loads(
    (ROOT_DIR / "schemas" / "result.schema.json").read_text(encoding="utf-8")
)
CASSETTE_SCHEMA = json.loads(
    (ROOT_DIR / "schemas" / "cassette.schema.json").read_text(encoding="utf-8")
)


def _validate_cassette(cassette_path: Path) -> list[dict]:
    """Validate all lines of a cassette file against cassette.schema.json."""
    raw_lines = cassette_path.read_text(encoding="utf-8").splitlines()
    lines = [json.loads(line) for line in raw_lines if line.strip()]
    validator = jsonschema.Draft202012Validator(CASSETTE_SCHEMA)
    for line in lines:
        validator.validate(line)
    return lines


# =============================================================================
# 1. Clean Oracle 100% Pass Across All Sandboxes under 'all' Guards
# =============================================================================


def test_acceptance_clean_oracle_all_sandboxes_pass_with_all_guards() -> None:
    """Acceptance criterion: clean Oracle runs across all sandboxes pass 100% with guards='all'."""
    scenarios_root = ROOT_DIR / "bench" / "scenarios"
    sandboxes = sorted([d for d in scenarios_root.iterdir() if d.is_dir()])
    assert len(sandboxes) == 10, f"Expected 10 sandboxes, found {len(sandboxes)}"

    for sb_dir in sandboxes:
        yaml_files = sorted(sb_dir.glob("*.yaml"))
        assert yaml_files, f"No scenarios found in {sb_dir}"
        scen_path = yaml_files[0]

        result = run_oracle(scen_path, fault="none", guards="all")
        assert result.success is True, (
            f"Sandbox {sb_dir.name} clean Oracle failed under guards='all': "
            f"path={result.path}, step_results={result.step_results}"
        )


# =============================================================================
# 2. S01 Fault Loudified by EmptinessGuard (and SchemaGuard)
# =============================================================================


@pytest.mark.asyncio
async def test_acceptance_s01_empty_ok_loudified_by_emptiness_guard(tmp_path: Path) -> None:
    """Acceptance criterion: S01 empty_ok is loudified when emptiness_guard is enabled."""
    out_dir = tmp_path / "s01_run"
    work_dir = tmp_path / "s01_work"

    res = await run_episode(
        SCENARIO_WEATHER,
        fault_id="S01",
        agent="reference:fake/oracle_follower",
        guards=["emptiness_guard"],
        out_dir=out_dir,
        workdir=work_dir,
    )

    # 1. Validate result schema
    jsonschema.validate(instance=res, schema=RESULT_SCHEMA)
    assert res["agent"]["guards"] == ["emptiness_guard"]

    # 2. Validate cassette schema
    cassette_path = out_dir / "cassettes" / Path(res["cassette"]).name
    assert cassette_path.is_file()
    lines = _validate_cassette(cassette_path)

    # 3. Verify s2c response in cassette was loudified by emptiness_guard
    s2c_calls = [
        m
        for m in lines
        if m.get("type") == "msg" and m.get("dir") == "s2c" and m.get("final") is not None
    ]
    assert s2c_calls, "Expected modified s2c message in cassette"
    final_resp = s2c_calls[0].get("final", {})
    final_res = final_resp.get("result", {})
    assert final_res.get("isError") is True
    content_text = final_res.get("content", [])[0].get("text", "")
    assert content_text == EMPTINESS_GUARD_TEXT

    # Verify guard action note
    assert any(
        g.get("id") == "emptiness_guard" and g.get("action") == "loudify"
        for g in s2c_calls[0].get("guards", [])
    )


# =============================================================================
# 3. S03 Fault Loudified by StalenessGuard
# =============================================================================


@pytest.mark.asyncio
async def test_acceptance_s03_stale_loudified_by_staleness_guard(tmp_path: Path) -> None:
    """Acceptance criterion: S03 stale is loudified when staleness_guard is enabled."""
    out_dir = tmp_path / "s03_run"
    work_dir = tmp_path / "s03_work"

    res = await run_episode(
        SCENARIO_WEATHER,
        fault_id="S03",
        agent="reference:fake/oracle_follower",
        guards=["staleness_guard"],
        out_dir=out_dir,
        workdir=work_dir,
    )

    # 1. Validate result schema
    jsonschema.validate(instance=res, schema=RESULT_SCHEMA)
    assert res["agent"]["guards"] == ["staleness_guard"]

    # 2. Validate cassette schema
    cassette_path = out_dir / "cassettes" / Path(res["cassette"]).name
    assert cassette_path.is_file()
    lines = _validate_cassette(cassette_path)

    # 3. Verify s2c response in cassette was loudified by staleness_guard
    s2c_calls = [
        m
        for m in lines
        if m.get("type") == "msg" and m.get("dir") == "s2c" and m.get("final") is not None
    ]
    assert s2c_calls, "Expected modified s2c message in cassette"
    final_resp = s2c_calls[0].get("final", {})
    final_res = final_resp.get("result", {})
    assert final_res.get("isError") is True
    content_text = final_res.get("content", [])[0].get("text", "")
    assert (
        "[skeptic:staleness_guard] Result dates do not match the request or are older than"
        in content_text
    )
    assert "Treat as stale." in content_text

    # Verify guard action note
    assert any(
        g.get("id") == "staleness_guard" and g.get("action") == "loudify"
        for g in s2c_calls[0].get("guards", [])
    )


# =============================================================================
# 4. S04 Fault Exceeding outputSchema Range Loudified by SchemaGuard
# =============================================================================


def test_acceptance_s04_exceeding_schema_range_loudified_by_schema_guard() -> None:
    """Acceptance criterion: S04 exceeding outputSchema range is loudified by schema_guard."""
    # Forecast schema with maximum 60 on max_c
    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "date": {"type": "string"},
            "max_c": {"type": "number", "maximum": 60},
        },
        "required": ["city", "date", "max_c"],
    }
    guard = SchemaGuard(
        GuardSpec(guard_id="schema_guard", params={"schemas": {"get_forecast": schema}})
    )
    ctx = EpisodeContext(episode_id="s04-ep", seed=1, era=UNKNOWN)
    ctx.pending[(C2S, 1)] = PendingCall(
        method="tools/call",
        tool_name="get_forecast",
        arguments={"city": "Paris", "date": "2026-11-02"},
        t_start=0.0,
        attempt=1,
    )

    # Under S04 with factor 10, max_c is scaled from 14.5 to 145.0
    s04_response = Response(
        id=1,
        result={
            "content": [
                {
                    "type": "text",
                    "text": '{"city": "Paris", "date": "2026-11-02", "max_c": 145.0}',
                }
            ],
            "structuredContent": {"city": "Paris", "date": "2026-11-02", "max_c": 145.0},
            "resultType": "complete",
        },
    )

    res = guard.on_s2c_call(s04_response, ctx, "get_forecast")
    assert res is not None
    assert isinstance(res.msg, Response)
    assert res.msg.result["isError"] is True
    err_text = res.msg.result["content"][0]["text"]
    assert "[skeptic:schema_guard] Tool output failed validation:" in err_text
    assert "maximum" in err_text
    assert res.note is not None
    assert res.note["id"] == "schema_guard"
    assert res.note["action"] == "loudify"


# =============================================================================
# 5. S07 Fault Malformed JSON Loudified by Guards
# =============================================================================


@pytest.mark.asyncio
async def test_acceptance_s07_malformed_ok_loudified_by_guards(tmp_path: Path) -> None:
    """Acceptance criterion: S07 malformed_ok is loudified when emptiness/schema
    guards are enabled.
    """
    out_dir = tmp_path / "s07_run"
    work_dir = tmp_path / "s07_work"

    res = await run_episode(
        SCENARIO_WEATHER,
        fault_id="S07",
        agent="reference:fake/oracle_follower",
        guards=["emptiness_guard"],
        out_dir=out_dir,
        workdir=work_dir,
    )

    # 1. Validate result schema
    jsonschema.validate(instance=res, schema=RESULT_SCHEMA)
    assert res["agent"]["guards"] == ["emptiness_guard"]

    # 2. Validate cassette schema
    cassette_path = out_dir / "cassettes" / Path(res["cassette"]).name
    assert cassette_path.is_file()
    lines = _validate_cassette(cassette_path)

    # 3. Verify s2c response in cassette was loudified
    s2c_calls = [
        m
        for m in lines
        if m.get("type") == "msg" and m.get("dir") == "s2c" and m.get("final") is not None
    ]
    assert s2c_calls, "Expected modified s2c message in cassette"
    final_resp = s2c_calls[0].get("final", {})
    final_res = final_resp.get("result", {})
    assert final_res.get("isError") is True
    content_text = final_res.get("content", [])[0].get("text", "")
    assert content_text == EMPTINESS_GUARD_TEXT


# =============================================================================
# 6. S02 Fault Truncated Array Loudified by EmptinessGuard
# =============================================================================


def test_acceptance_s02_truncated_array_loudified_by_emptiness_guard() -> None:
    """Acceptance criterion: S02 truncated array (< n/2) is loudified by emptiness_guard."""
    guard = EmptinessGuard(GuardSpec(guard_id="emptiness_guard"))
    ctx = EpisodeContext(episode_id="s02-ep", seed=1, era=UNKNOWN)

    # First attempt: full array of 10 items
    ctx.pending[(C2S, 1)] = PendingCall(
        method="tools/call",
        tool_name="get_history",
        arguments={"ticker": "ACME"},
        t_start=0.0,
        attempt=1,
    )
    full_resp = Response(
        id=1,
        result={
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": {"ticker": "ACME", "bars": [{"i": i} for i in range(10)]},
            "resultType": "complete",
        },
    )
    assert guard.on_s2c_call(full_resp, ctx, "get_history") is None

    # Second attempt: S02 with ratio=0.3 cuts 10 items down to ceil(10 * 0.3) = 3 items (3 < 10/2)
    ctx.pending[(C2S, 2)] = PendingCall(
        method="tools/call",
        tool_name="get_history",
        arguments={"ticker": "ACME"},
        t_start=0.0,
        attempt=2,
    )
    truncated_resp = Response(
        id=2,
        result={
            "content": [{"type": "text", "text": "ok"}],
            "structuredContent": {"ticker": "ACME", "bars": [{"i": i} for i in range(3)]},
            "resultType": "complete",
        },
    )
    res = guard.on_s2c_call(truncated_resp, ctx, "get_history")
    assert res is not None
    assert isinstance(res.msg, Response)
    assert res.msg.result["isError"] is True
    assert res.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT
