"""The commands the K57 action runs, with FakeLLM and no network.

CliRunner cannot host the episode: it replaces stdio and the sandbox child
then fails with ``fileno``. The action runs ``skeptic`` in a real process, so
this test does too.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO = "bench/scenarios/weather/weather.forecast.paris-max.001.yaml"


def _skeptic(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "skeptic_agent.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fakellm_run_report_and_gate(tmp_path: Path) -> None:
    """A clean FakeLLM episode publishes a report and the gate exits 10 over 100."""
    out_dir = tmp_path / "skeptic-run"
    ledger = tmp_path / "ledger.csv"

    ran = _skeptic(
        [
            "run",
            "--scenario",
            SCENARIO,
            "--agent",
            "reference:fake/oracle_follower",
            "--profile",
            "none",
            "--max-cost-usd",
            "1",
            "--out",
            str(out_dir),
            "--ledger",
            str(ledger),
        ]
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    summary_path = out_dir / "summary.json"
    assert summary_path.is_file()
    assert ledger.is_file()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = summary["agents"][0]["metrics"]
    sks = float(metrics["SKS"]["estimate"])
    fsr = float(metrics["FSR"]["estimate"])
    assert sks >= 70
    assert 0.0 <= fsr <= 1.0
    assert summary["episodes"][0]["outcome"] == "SUCCESS"

    reported = _skeptic(["report", str(out_dir)])
    assert reported.returncode == 0, reported.stdout + reported.stderr
    report_md = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "SKS" in report_md
    assert "http://" not in report_md
    assert "https://" not in report_md

    passed = _skeptic(["gate", str(out_dir), "--min-sks", "70"])
    assert passed.returncode == 0, passed.stdout + passed.stderr

    failed = _skeptic(["gate", str(out_dir), "--min-sks", "101"])
    assert failed.returncode == 10
    assert "FAILED" in failed.stdout + failed.stderr
