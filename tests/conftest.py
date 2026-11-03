"""Pytest configuration and global fixtures for Skeptic test suite."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_BENCH_LEDGER = REPO_ROOT / "bench" / "ledger.csv"


@pytest.fixture(autouse=True)
def isolate_test_ledger(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Path, None, None]:
    """Ensure all tests write ledger.csv to tmp_path, never into bench/ (E49fix)."""
    temp_dir = tmp_path_factory.mktemp("test_ledger")
    temp_ledger = temp_dir / "ledger.csv"
    monkeypatch.setenv("SKEPTIC_LEDGER_PATH", str(temp_ledger))

    yield temp_ledger

    # Fail closed: ensure no test ever writes into repo's bench/ledger.csv
    assert not REPO_BENCH_LEDGER.exists(), (
        f"Test isolation failure: {REPO_BENCH_LEDGER} was created during testing! "
        "Tests must write ledger.csv to tmp_path, never into the repo's bench/ directory."
    )
