"""Integration tests running D61 example scripts with FakeLLM and no external network."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"


def test_01_claude_code_run_script() -> None:
    """Verify examples/01-claude-code/run.py executes wrap, proxy test, and byte restoration."""
    script = EXAMPLES_DIR / "01-claude-code" / "run.py"
    res = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"01-claude-code run.py failed:\n{res.stdout}\n{res.stderr}"
    assert "Claude Code wrap demo completed successfully!" in res.stdout


def test_02_langgraph_run_script() -> None:
    """Verify examples/02-langgraph/run.py executes agent, clean run, report, and gate."""
    script = EXAMPLES_DIR / "02-langgraph" / "run.py"
    res = subprocess.run(
        [sys.executable, str(script), "--quick"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"02-langgraph run.py failed:\n{res.stdout}\n{res.stderr}"
    assert "LangGraph example completed all evaluation steps successfully!" in res.stdout


def test_03_github_action_run_script() -> None:
    """Verify examples/03-github-action/run.py simulates the GitHub Action steps locally."""
    script = EXAMPLES_DIR / "03-github-action" / "run.py"
    res = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"03-github-action run.py failed:\n{res.stdout}\n{res.stderr}"
    assert "GitHub Action simulation completed all steps successfully!" in res.stdout
