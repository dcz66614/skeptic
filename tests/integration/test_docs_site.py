"""Docs locale parity, FakeLLM quickstart, and the strict MkDocs build."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_docs.py"


def _env() -> dict[str, str]:
    tmp = ROOT / "runs" / "docs-quickstart-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def test_docs_locales_and_quickstart_commands() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_quickstart_commands_execute() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--execute"],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=400,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mkdocs_build_strict() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
