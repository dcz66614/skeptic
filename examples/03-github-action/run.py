"""Local execution simulator for the Skeptic GitHub Action (D61, K57).

Runs the exact sequence of steps defined in workflow.yml using FakeLLM without
requiring external network access, credentials, or a live GitHub runner:
1. skeptic run (--suite smoke --agent reference:fake/oracle_follower --profile none)
2. skeptic report
3. Step summary and outputs verification (sks, fsr, report-path)
4. skeptic gate --min-sks 70 (passes, exit code 0)
5. skeptic gate --min-sks 101 (fails, exit code 10, confirming expected failure)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DIR = Path(__file__).resolve().parent
REPO_ROOT = DIR.parents[1]
DEFAULT_SCENARIO = (
    REPO_ROOT / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"
)


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a skeptic CLI command via the current Python interpreter."""
    return subprocess.run(
        [sys.executable, "-m", "skeptic_agent.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def simulate_workflow(use_full_smoke: bool = False) -> int:
    """Run the GitHub Action workflow steps locally."""
    print("=" * 70)
    print("Skeptic GitHub Action: Local Workflow Simulation")
    print("=" * 70)

    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp_str:
        tmp_dir = Path(tmp_str)
        run_out = tmp_dir / "skeptic-run"
        ledger_path = tmp_dir / "ledger.csv"

        # 1. Action Step: skeptic run
        # In workflow.yml: suite: smoke, profile: none, agent: reference:fake/oracle_follower
        print("\n[Step 1/5] Executing: skeptic run (FakeLLM oracle_follower)...")
        target_args = (
            ["--suite", "smoke"] if use_full_smoke else ["--scenario", str(DEFAULT_SCENARIO)]
        )
        run_res = _run_cli(
            [
                "run",
                *target_args,
                "--agent",
                "reference:fake/oracle_follower",
                "--profile",
                "none",
                "--max-cost-usd",
                "1",
                "--out",
                str(run_out),
                "--ledger",
                str(ledger_path),
            ]
        )
        if run_res.returncode != 0:
            print(f"Run step failed: {run_res.stderr}", file=sys.stderr)
            return run_res.returncode

        summary_file = run_out / "summary.json"
        assert summary_file.is_file(), "Missing summary.json from action run"
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        metrics = summary["agents"][0]["metrics"]
        sks = float(metrics["SKS"]["estimate"])
        fsr = float(metrics["FSR"]["estimate"])
        print(f"   [Step 1 OK] Run finished with SKS={sks:.2f}, FSR={fsr:.2f}")

        # 2. Action Step: skeptic report
        print("\n[Step 2/5] Executing: skeptic report...")
        rep_res = _run_cli(["report", str(run_out)])
        if rep_res.returncode != 0:
            print(f"Report step failed: {rep_res.stderr}", file=sys.stderr)
            return rep_res.returncode
        report_md = run_out / "report.md"
        assert report_md.is_file(), "Missing report.md"
        print(f"   [Step 2 OK] Generated report.md ({report_md.stat().st_size} bytes)")

        # 3. Action Step: Outputs verification & job summary
        print("\n[Step 3/5] Verifying outputs (sks, fsr, report-path)...")
        assert sks >= 70, f"Expected SKS >= 70, got {sks}"
        assert 0.0 <= fsr <= 1.0, f"Invalid FSR: {fsr}"
        assert run_out.is_dir(), f"Report path is not a directory: {run_out}"
        print(f"   [Step 3 OK] outputs.sks={sks} outputs.fsr={fsr} outputs.report-path={run_out}")

        # 4. Action Step: skeptic gate (pass branch, min-sks 70)
        print("\n[Step 4/5] Executing passing gate: skeptic gate --min-sks 70...")
        pass_gate = _run_cli(["gate", str(run_out), "--min-sks", "70"])
        assert pass_gate.returncode == 0, f"Expected exit 0, got {pass_gate.returncode}"
        print("   [Step 4 OK] Quality gate passed (exit code 0).")

        # 5. Action Step: skeptic gate (fail branch, min-sks 101)
        print("\n[Step 5/5] Executing failing gate check: skeptic gate --min-sks 101...")
        fail_gate = _run_cli(["gate", str(run_out), "--min-sks", "101"])
        assert fail_gate.returncode == 10, (
            f"Expected exit code 10 from gate failure, got {fail_gate.returncode}"
        )
        print("   [Step 5 OK] Gate failed with exit code 10 (expected failure for red check).")

    print("\n" + "=" * 70)
    print("GitHub Action simulation completed all steps successfully!")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Skeptic GitHub Action locally")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run full smoke suite (20 episodes) instead of single scenario",
    )
    args = parser.parse_args()
    return simulate_workflow(use_full_smoke=args.smoke)


if __name__ == "__main__":
    sys.exit(main())
