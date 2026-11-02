"""Unit tests for BudgetTracker and ledger accounting (1.8, E40)."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeptic_agent.runner.budget import (
    DEFAULT_MAX_COST_USD,
    EXIT_BUDGET_EXCEEDED,
    BudgetExceededError,
    BudgetTracker,
    append_ledger_entry,
)

pytestmark = pytest.mark.unit


def test_budget_tracker_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """BudgetTracker picks up SKEPTIC_MAX_COST_USD or falls back to 5.0 (1.8)."""
    monkeypatch.delenv("SKEPTIC_MAX_COST_USD", raising=False)
    tracker = BudgetTracker()
    assert tracker.max_cost_usd == DEFAULT_MAX_COST_USD
    assert tracker.can_dispatch()

    monkeypatch.setenv("SKEPTIC_MAX_COST_USD", "12.5")
    tracker2 = BudgetTracker()
    assert tracker2.max_cost_usd == 12.5

    monkeypatch.setenv("SKEPTIC_MAX_COST_USD", "invalid_number")
    tracker3 = BudgetTracker()
    assert tracker3.max_cost_usd == DEFAULT_MAX_COST_USD


def test_budget_tracker_exhaustion() -> None:
    """When spent_usd reaches max_cost_usd, check_can_dispatch raises BudgetExceededError."""
    tracker = BudgetTracker(max_cost_usd=2.0)
    tracker.record_spend(cost_usd=1.0, tokens_in=500, tokens_out=200)
    assert tracker.can_dispatch()
    tracker.check_can_dispatch()

    tracker.record_spend(cost_usd=1.0, tokens_in=500, tokens_out=200)
    assert not tracker.can_dispatch()
    with pytest.raises(BudgetExceededError) as exc_info:
        tracker.check_can_dispatch()
    assert f"exit code {EXIT_BUDGET_EXCEEDED}" in str(exc_info.value)


def test_ledger_append(tmp_path: Path) -> None:
    """Ledger writes header on first entry and appends subsequent entries (1.8)."""
    ledger = tmp_path / "bench" / "ledger.csv"

    append_ledger_entry(
        ledger,
        task_id="E40",
        agent_name="reference:fake/oracle_follower",
        run_id="20261102-140000-112233",
        model="fake/oracle_follower",
        episodes=1,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.0,
        timestamp="2026-11-02T14:00:00Z",
    )
    assert ledger.is_file()

    append_ledger_entry(
        ledger,
        task_id="E40",
        agent_name="reference:fake/oracle_follower",
        run_id="20261102-140000-112233",
        model="fake/oracle_follower",
        episodes=1,
        tokens_in=200,
        tokens_out=100,
        cost_usd=0.05,
        timestamp="2026-11-02T14:05:00Z",
    )

    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert (
        lines[0]
        == "timestamp,task_id,agent_name,run_id,model,episodes,tokens_in,tokens_out,cost_usd"
    )
    assert "E40,reference:fake/oracle_follower,20261102-140000-112233" in lines[1]
    assert "E40,reference:fake/oracle_follower,20261102-140000-112233" in lines[2]
