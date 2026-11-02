"""Integration tests for scripted Oracle and recoverability evaluation (S8.3, S36)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.scenario.oracle import (
    determine_recoverability,
    evaluate_recoverability_matrix,
    run_oracle,
)

pytestmark = pytest.mark.integration

SCENARIOS_DIR = Path("tests/fixtures/scenarios")
WEATHER_SCENARIO = SCENARIOS_DIR / "weather.forecast.max-temp.001.yaml"
FX_SCENARIO = SCENARIOS_DIR / "fx.rate.usd-eur.001.yaml"
CRM_SCENARIO = SCENARIOS_DIR / "crm.customer.get.001.yaml"


def test_oracle_clean_run_passes_on_weather() -> None:
    """S36 acceptance: example scenarios in clean mode pass Oracle."""
    result = run_oracle(WEATHER_SCENARIO, fault="none")
    assert result.success is True
    assert result.recoverability == "unaffected"
    assert result.path == "steps"
    assert len(result.step_results) == 1
    assert result.step_results[0].success is True


def test_oracle_s04_outputs_recoverable() -> None:
    """S36 acceptance: under S04 numeric corruption, outputs 'recoverable'."""
    result = run_oracle(WEATHER_SCENARIO, fault="S04")
    assert result.success is True
    assert result.recoverability == "recoverable"
    assert result.path == "recovery.default"


def test_oracle_unaffected_fault() -> None:
    """A fault targeting another tool or not triggering leaves the scenario unaffected."""
    # S10 targets $write tools; weather scenario has no write tools
    result = run_oracle(WEATHER_SCENARIO, fault="S10")
    assert result.success is True
    assert result.recoverability == "unaffected"
    assert result.path == "steps"


def test_oracle_unrecoverable_fault() -> None:
    """When steps fail and no alternate recovery path exists, outputs 'unrecoverable'."""
    # CRM scenario has no recovery block defined; L02 jsonrpc_error will break get_customer
    result = run_oracle(CRM_SCENARIO, fault="L02")
    assert result.success is False
    assert result.recoverability == "unrecoverable"
    assert result.path == "none"


def test_determine_recoverability_helper() -> None:
    """determine_recoverability returns string status."""
    status = determine_recoverability(WEATHER_SCENARIO, "S04")
    assert status == "recoverable"


def test_evaluate_recoverability_matrix(tmp_path: Path) -> None:
    """evaluate_recoverability_matrix produces mapping for multiple scenarios and faults."""
    matrix = evaluate_recoverability_matrix([WEATHER_SCENARIO], ["S04", "S10"])
    assert "weather.forecast.max-temp.001" in matrix
    assert matrix["weather.forecast.max-temp.001"]["S04"] == "recoverable"
    assert matrix["weather.forecast.max-temp.001"]["S10"] == "unaffected"


def test_cli_oracle_clean() -> None:
    """CLI scenario oracle passes on clean run."""
    runner = CliRunner()
    result = runner.invoke(app, ["scenario", "oracle", str(WEATHER_SCENARIO)])
    assert result.exit_code == 0
    assert "weather.forecast.max-temp.001: PASS" in result.output


def test_cli_oracle_fault_and_write_cache(tmp_path: Path) -> None:
    """CLI scenario oracle --faults S04 writes recoverability cache file."""
    cache_file = tmp_path / "rec.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "scenario",
            "oracle",
            "--faults",
            "S04",
            "--write-recoverability",
            str(cache_file),
            str(WEATHER_SCENARIO),
        ],
    )
    assert result.exit_code == 0
    assert "weather.forecast.max-temp.001 [S04]: recoverable" in result.output
    assert cache_file.is_file()

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    assert data["weather.forecast.max-temp.001"]["S04"] == "recoverable"
