"""Integration and acceptance tests for batch runner, matrix, resume, and gate (E48)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.runner.budget import BudgetExceededError
from skeptic_agent.runner.matrix import (
    execute_matrix,
    execute_run,
)
from skeptic_agent.scenario.suites import resolve_suite_scenarios

runner = CliRunner()


@pytest.mark.asyncio
async def test_execute_run_basic(tmp_path: Path) -> None:
    """Test basic execution of 2 scenarios from smoke with clean baseline."""
    smoke_scens = resolve_suite_scenarios("smoke")[:2]
    out_dir = tmp_path / "basic_run"
    ledger_file = tmp_path / "ledger.csv"

    summary = await execute_run(
        scenarios=smoke_scens,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=2,
        out_dir=out_dir,
        ledger_path=ledger_file,
    )

    assert (out_dir / "results.jsonl").is_file()
    assert (out_dir / "summary.json").is_file()
    assert ledger_file.is_file()

    # Check summary content
    assert summary["schema"] == "skeptic.report/v1"
    assert len(summary["agents"]) == 1
    assert len(summary["episodes"]) > 0

    lines = (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(summary["episodes"])


@pytest.mark.asyncio
async def test_execute_run_budget_limit(tmp_path: Path) -> None:
    """Test that exceeding budget cap halts execution and raises BudgetExceededError."""
    smoke_scens = resolve_suite_scenarios("smoke")[:2]
    out_dir = tmp_path / "budget_run"

    # Set budget limit to 0.0 USD so can_dispatch is immediately False
    with pytest.raises(BudgetExceededError):
        await execute_run(
            scenarios=smoke_scens,
            agent="reference:fake/oracle_follower",
            profile="silent-core",
            seeds=[1],
            max_cost_usd=0.0,
            concurrency=1,
            out_dir=out_dir,
            ledger_path=tmp_path / "ledger.csv",
        )


@pytest.mark.asyncio
async def test_resume_preserves_results_and_skips_completed(tmp_path: Path) -> None:
    """Verify that --resume skips already completed episodes and yields identical results."""
    scens = resolve_suite_scenarios("smoke")[:2]
    out_dir = tmp_path / "resume_test"
    ledger_file = tmp_path / "ledger.csv"

    # 1. Run completely once
    full_summary = await execute_run(
        scenarios=scens,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=2,
        out_dir=out_dir,
        ledger_path=ledger_file,
    )
    full_lines = (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    total_count = len(full_lines)
    assert total_count > 2

    # 2. Simulate interruption in a new directory with only first 2 lines
    interrupted_dir = tmp_path / "interrupted_run"
    interrupted_dir.mkdir()
    (interrupted_dir / "results.jsonl").write_text(
        "\n".join(full_lines[:2]) + "\n",
        encoding="utf-8",
    )

    # Resume the interrupted run
    resumed_summary = await execute_run(
        scenarios=scens,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=2,
        out_dir=interrupted_dir,
        resume=True,
        ledger_path=ledger_file,
    )

    resumed_lines = (interrupted_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(resumed_lines) == total_count

    # Compare outcomes and episode IDs
    full_docs = [json.loads(line) for line in full_lines]
    resumed_docs = [json.loads(line) for line in resumed_lines]

    for d_full, d_res in zip(full_docs, resumed_docs, strict=True):
        assert d_full["scenario_id"] == d_res["scenario_id"]
        assert d_full["outcome"] == d_res["outcome"]
        assert d_full["fault"] == d_res["fault"]

    # Compare summary SKS
    sks_full = full_summary["agents"][0]["metrics"]["SKS"]["estimate"]
    sks_res = resumed_summary["agents"][0]["metrics"]["SKS"]["estimate"]
    assert abs(sks_full - sks_res) < 1e-9


@pytest.mark.asyncio
async def test_execute_matrix_runs(tmp_path: Path) -> None:
    """Test execute_matrix runs multiple configurations from a matrix file."""
    matrix_data = {
        "schema": "skeptic.matrix/v1",
        "id": "matrix-test",
        "suite": "smoke",
        "profiles": ["silent-core"],
        "seeds": [1],
        "max_cost_usd": 10.0,
        "configs": [
            {
                "agent": "reference:${model}",
                "prompt_variant": "plain",
                "guards": "none",
                "models": ["fake/oracle_follower"],
            }
        ],
    }
    matrix_file = tmp_path / "matrix.yaml"
    matrix_file.write_text(yaml.safe_dump(matrix_data), encoding="utf-8")

    out_base = tmp_path / "matrix_runs"
    ledger_file = tmp_path / "ledger.csv"

    summaries = await execute_matrix(
        matrix_file,
        concurrency=4,
        out_dir=out_base,
        ledger_path=ledger_file,
    )

    assert len(summaries) == 1
    assert (out_base / "summary.json").is_file()
    assert (out_base / "results.jsonl").is_file()


def test_cli_bench_run_and_gate_fail(tmp_path: Path) -> None:
    """Test CLI commands skeptic bench run and skeptic gate with exit code 10 on failure."""
    matrix_data = {
        "schema": "skeptic.matrix/v1",
        "id": "cli-matrix",
        "suite": "smoke",
        "profiles": ["silent-core"],
        "seeds": [1],
        "max_cost_usd": 10.0,
        "configs": [
            {
                "agent": "reference:${model}",
                "prompt_variant": "plain",
                "guards": "none",
                "models": ["fake/oracle_follower"],
            }
        ],
    }
    matrix_file = tmp_path / "matrix.yaml"
    matrix_file.write_text(yaml.safe_dump(matrix_data), encoding="utf-8")

    out_dir = tmp_path / "cli_run"

    # Run via CLI
    res = runner.invoke(
        app,
        ["bench", "run", "--matrix", str(matrix_file), "--out", str(out_dir), "--concurrency", "4"],
    )
    assert res.exit_code == 0
    assert "Matrix benchmark completed" in res.stdout

    # Gate check passes with low threshold
    res_pass = runner.invoke(app, ["gate", str(out_dir), "--min-sks", "10.0", "--max-fsr", "1.0"])
    assert res_pass.exit_code == 0
    assert "Gate check PASSED" in res_pass.stdout

    # Gate check fails with impossible threshold: must exit with code 10 (S2, E48)
    res_fail = runner.invoke(app, ["gate", str(out_dir), "--min-sks", "101.0"])
    assert res_fail.exit_code == 10
    assert "Gate check FAILED" in res_fail.stderr or "Gate check FAILED" in res_fail.stdout


@pytest.mark.asyncio
async def test_acceptance_smoke_silent_core_kill_and_resume(tmp_path: Path) -> None:
    """Acceptance criterion for E48:

    Run smoke suite x silent-core under FakeLLM, simulate kill midway, then --resume.
    Verify final result is completely identical to running in one go.
    Verify gate returns exit code 10 when thresholds are not met.
    """
    scenarios = resolve_suite_scenarios("smoke")
    ledger_path = tmp_path / "ledger.csv"

    # Step 1: Run uninterrupted
    full_dir = tmp_path / "full_run"
    full_summary = await execute_run(
        scenarios=scenarios,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=8,
        out_dir=full_dir,
        ledger_path=ledger_path,
    )
    full_results_lines = (full_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(full_results_lines) == 158

    # Step 2: Interrupted run
    # Take first 50 episodes to simulate process killed midway
    interrupted_dir = tmp_path / "resumed_run"
    interrupted_dir.mkdir()
    (interrupted_dir / "results.jsonl").write_text(
        "\n".join(full_results_lines[:50]) + "\n",
        encoding="utf-8",
    )

    # Step 3: Resume
    resumed_summary = await execute_run(
        scenarios=scenarios,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=8,
        out_dir=interrupted_dir,
        resume=True,
        ledger_path=ledger_path,
    )

    resumed_results_lines = (
        (interrupted_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(resumed_results_lines) == 158

    # Verify every episode outcome, scenario_id, fault matches
    full_records = [json.loads(line) for line in full_results_lines]
    resumed_records = [json.loads(line) for line in resumed_results_lines]

    for r_full, r_res in zip(full_records, resumed_records, strict=True):
        assert r_full["scenario_id"] == r_res["scenario_id"]
        assert r_full["outcome"] == r_res["outcome"]
        assert r_full["fault"] == r_res["fault"]

    # Verify SKS, FSR, SafeRate and other metrics are completely identical
    ag_full = full_summary["agents"][0]["metrics"]
    ag_res = resumed_summary["agents"][0]["metrics"]

    assert abs(ag_full["SKS"]["estimate"] - ag_res["SKS"]["estimate"]) < 1e-9
    assert abs(ag_full["SafeRate"]["estimate"] - ag_res["SafeRate"]["estimate"]) < 1e-9
    assert abs(ag_full["FSR"]["estimate"] - ag_res["FSR"]["estimate"]) < 1e-9
    assert abs(ag_full["SCR"]["estimate"] - ag_res["SCR"]["estimate"]) < 1e-9

    # Step 4: Gate failure returns exit code 10
    gate_fail_res = runner.invoke(app, ["gate", str(interrupted_dir), "--min-sks", "101.0"])
    assert gate_fail_res.exit_code == 10
