"""Skeptic test runner for the minimal LangGraph agent (D61, S13.4, E43).

Demonstrates:
1. Standalone execution of the minimal LangGraph ReAct agent with FakeLLM.
2. Clean baseline evaluation using `skeptic run` (profile none).
3. Fault injection evaluation using `skeptic run` (profile silent-core).
4. Generating markdown and html reliability reports with `skeptic report`.
5. Enforcing quality gates with `skeptic gate` (pass on 70, fail on 101).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DIR = Path(__file__).resolve().parent
REPO_ROOT = DIR.parents[1]
SCENARIO = REPO_ROOT / "bench" / "scenarios" / "weather" / "weather.forecast.paris-max.001.yaml"

from agent import run_agent  # noqa: E402


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute skeptic CLI command."""
    return subprocess.run(
        [sys.executable, "-m", "skeptic_agent.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_standalone_agent() -> None:
    """Verify that the agent runs offline and produces an answer."""
    prompt = "What is the maximum temperature in Paris today? Answer with just the number."
    res = asyncio.run(run_agent(prompt))
    assert res["final_answer"] == "14.5", f"Unexpected answer: {res['final_answer']}"
    assert res["steps"] >= 2, f"Expected at least 2 steps, got {res['steps']}"
    print(f"   [Agent OK] Final answer: {res['final_answer']} ({res['steps']} turns)")


def run_full_suite(quick: bool = False) -> int:
    print("=" * 70)
    print("Skeptic LangGraph Example: Agent Execution & Chaos Evaluation")
    print("=" * 70)

    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmp_str:
        tmp_dir = Path(tmp_str)
        clean_out = tmp_dir / "clean_run"
        fault_out = tmp_dir / "fault_run"
        ledger_path = tmp_dir / "ledger.csv"

        # 1. Standalone execution
        print("\n[Step 1/5] Testing minimal LangGraph agent with FakeLLM...")
        test_standalone_agent()

        # 2. Skeptic clean evaluation
        print("\n[Step 2/5] Running Skeptic clean evaluation (profile: none)...")
        clean_res = _run_cli(
            [
                "run",
                "--scenario",
                str(SCENARIO),
                "--agent",
                "langgraph:fake/oracle_follower",
                "--profile",
                "none",
                "--max-cost-usd",
                "1",
                "--out",
                str(clean_out),
                "--ledger",
                str(ledger_path),
            ]
        )
        if clean_res.returncode != 0:
            print(f"Clean run failed: {clean_res.stderr}", file=sys.stderr)
            return clean_res.returncode

        summary_file = clean_out / "summary.json"
        assert summary_file.is_file(), "Missing summary.json from clean run"
        clean_summary = json.loads(summary_file.read_text(encoding="utf-8"))
        episodes = clean_summary.get("episodes", [])
        assert len(episodes) > 0, "No episodes recorded"
        outcome = episodes[0]["outcome"]
        assert outcome == "SUCCESS", f"Expected SUCCESS, got {outcome}"
        sks = float(clean_summary["agents"][0]["metrics"]["SKS"]["estimate"])
        print(f"   [Skeptic OK] Baseline SKS: {sks:.2f}, Outcome: {episodes[0]['outcome']}")

        # 3. Skeptic fault injection evaluation
        if not quick:
            print("\n[Step 3/5] Running Skeptic chaos evaluation (profile: silent-core)...")
            fault_res = _run_cli(
                [
                    "run",
                    "--scenario",
                    str(SCENARIO),
                    "--agent",
                    "langgraph:fake/oracle_follower",
                    "--profile",
                    "silent-core",
                    "--max-cost-usd",
                    "1",
                    "--out",
                    str(fault_out),
                    "--ledger",
                    str(ledger_path),
                ]
            )
            if fault_res.returncode != 0:
                print(f"Fault run failed: {fault_res.stderr}", file=sys.stderr)
                return fault_res.returncode

            fault_summary_file = fault_out / "summary.json"
            assert fault_summary_file.is_file(), "Missing summary.json from fault run"
            fault_summary = json.loads(fault_summary_file.read_text(encoding="utf-8"))
            fault_episodes = fault_summary.get("episodes", [])
            print(f"   [Chaos OK] Evaluated {len(fault_episodes)} episode(s) under silent-core.")
        else:
            print("\n[Step 3/5] Skipping full chaos matrix in --quick mode.")

        # 4. Generate report
        print("\n[Step 4/5] Generating reports with: skeptic report...")
        rep_res = _run_cli(["report", str(clean_out)])
        if rep_res.returncode != 0:
            print(f"Report failed: {rep_res.stderr}", file=sys.stderr)
            return rep_res.returncode
        report_md = clean_out / "report.md"
        assert report_md.is_file(), "report.md not generated"
        print("   [Report OK] Generated markdown and html reports.")

        # 5. Quality gate evaluation
        print("\n[Step 5/5] Evaluating quality gates with: skeptic gate...")
        # Passing gate (threshold 70)
        gate_pass = _run_cli(["gate", str(clean_out), "--min-sks", "70"])
        assert gate_pass.returncode == 0, f"Expected gate to pass, got exit {gate_pass.returncode}"
        print("   [Gate Pass OK] Threshold 70 passed (exit 0).")

        # Failing gate (threshold 101)
        gate_fail = _run_cli(["gate", str(clean_out), "--min-sks", "101"])
        assert gate_fail.returncode == 10, f"Expected exit code 10, got {gate_fail.returncode}"
        print("   [Gate Fail OK] Threshold 101 correctly failed (exit 10).")

    print("\n" + "=" * 70)
    print("LangGraph example completed all evaluation steps successfully!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    quick_mode = "--quick" in sys.argv
    sys.exit(run_full_suite(quick=quick_mode))
