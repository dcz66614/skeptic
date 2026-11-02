"""Unit tests for skeptic report CLI command (S2, S12, E49)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skeptic_agent.cli import app

pytestmark = pytest.mark.unit
runner = CliRunner()


@pytest.fixture
def minimal_run_dir(tmp_path: Path) -> Path:
    """Create a minimal run directory with valid summary.json."""
    run_dir = tmp_path / "min_run"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_doc = {
        "schema": "skeptic.report/v1",
        "run_id": "20261105-142233-a1b2c3",
        "time": "2026-11-05T14:22:33Z",
        "version": "0.1.0",
        "command": "skeptic run --suite smoke",
        "git_sha": "c507cee",
        "config": {
            "schema": "skeptic.config/v1",
            "project": "min",
            "servers": {"weather": {"transport": "stdio", "command": ["dummy"]}},
            "profile": "none",
            "guards": [],
            "gate": {"min_sks": 70.0, "max_fsr": 0.10, "max_icr": 0.00},
            "budget": {"max_cost_usd_per_run": 5.0},
        },
        "agents": [
            {
                "adapter": "reference",
                "model": "fake/oracle_follower",
                "prompt_variant": "plain",
                "guards": [],
                "metrics": {
                    "TSR_clean": {"estimate": 1.0, "low": 1.0, "high": 1.0},
                    "TSR_rec": {"estimate": 1.0, "low": 1.0, "high": 1.0},
                    "RR": {"estimate": 1.0, "low": 1.0, "high": 1.0},
                    "SafeRate": {"estimate": 1.0, "low": 1.0, "high": 1.0},
                    "FSR": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "SCR": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "ICR": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "LoopRate": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "DetectRate": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "UntriggeredRate": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "Cost": {"estimate": 0.0, "low": 0.0, "high": 0.0},
                    "Latency": {"estimate": 0.5, "low": 0.5, "high": 0.5},
                    "SKS": {"estimate": 100.0, "low": 100.0, "high": 100.0, "partial": False},
                },
            }
        ],
        "by_fault": {},
        "by_sandbox": {"sb_weather": {"SUCCESS": 1}},
        "worst_scenarios": [],
        "guard_actions": {},
        "total_cost_usd": 0.0,
        "episodes": [
            {
                "episode_id": "20261105-142233-a1b2c3:weather.forecast.max-temp.001:clean:1",
                "scenario_id": "weather.forecast.max-temp.001",
                "sandbox": "sb_weather",
                "seed": 1,
                "outcome": "SUCCESS",
                "fault_id": None,
                "cassette": "",
            }
        ],
    }

    (run_dir / "summary.json").write_text(json.dumps(summary_doc, indent=2), encoding="utf-8")
    return run_dir


def test_cli_report_default_all_formats(minimal_run_dir: Path) -> None:
    """Test skeptic report generates all 6 formats in the run directory by default."""
    result = runner.invoke(app, ["report", str(minimal_run_dir)])
    assert result.exit_code == 0, result.output
    assert "Generated 6 report(s)" in result.output

    assert (minimal_run_dir / "report.json").is_file()
    assert (minimal_run_dir / "report.md").is_file()
    assert (minimal_run_dir / "report.html").is_file()
    assert (minimal_run_dir / "junit.xml").is_file()
    assert (minimal_run_dir / "skeptic.sarif").is_file()
    assert (minimal_run_dir / "badge.svg").is_file()


def test_cli_report_specific_formats_and_out_dir(minimal_run_dir: Path, tmp_path: Path) -> None:
    """Test --format and --out options."""
    out_dir = tmp_path / "custom_out"
    result = runner.invoke(
        app,
        ["report", str(minimal_run_dir), "--format", "html,md", "--out", str(out_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "Generated 2 report(s)" in result.output

    assert (out_dir / "report.html").is_file()
    assert (out_dir / "report.md").is_file()
    assert not (out_dir / "report.json").is_file()
    assert not (out_dir / "junit.xml").is_file()


def test_cli_report_nonexistent_run_dir(tmp_path: Path) -> None:
    """Test error when run directory does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    result = runner.invoke(app, ["report", str(nonexistent)])
    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_cli_report_invalid_format(minimal_run_dir: Path) -> None:
    """Test error on invalid format specification."""
    result = runner.invoke(app, ["report", str(minimal_run_dir), "--format", "pdf"])
    assert result.exit_code == 2
    assert "Invalid report format: 'pdf'" in result.output
