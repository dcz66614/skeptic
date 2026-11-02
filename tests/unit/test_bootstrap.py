"""Unit tests for scenario cluster bootstrap confidence intervals and ranking (E47, S10.4)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from skeptic_agent.scoring.bootstrap import (
    compute_bootstrap_ci,
    intervals_overlap,
    rank_configurations,
)
from skeptic_agent.scoring.metrics import (
    ConfidenceInterval,
    SKSScore,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def metrics_fixture() -> dict[str, Any]:
    fixture_path = FIXTURES_DIR / "metrics_expected.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_bootstrap_reproducibility_fixed_seed(
    metrics_fixture: dict[str, Any],
) -> None:
    """Acceptance test: Bootstrap fixed seed produces reproducible results (S10.4)."""
    episodes = metrics_fixture["episodes"]

    run1 = compute_bootstrap_ci(episodes, b=1000, seed=0)
    run2 = compute_bootstrap_ci(episodes, b=1000, seed=0)

    # Convert to dict and assert exact bitwise equality
    d1 = run1.to_dict()
    d2 = run2.to_dict()
    assert d1 == d2

    # Check each metric has low <= estimate <= high or consistent bounds
    for _key, ci in d1.items():
        assert "estimate" in ci
        assert "low" in ci
        assert "high" in ci
        assert ci["low"] <= ci["high"]


def test_bootstrap_different_seeds(metrics_fixture: dict[str, Any]) -> None:
    """Different random seeds should explore different bootstrap samples."""
    episodes = metrics_fixture["episodes"]

    run_seed0 = compute_bootstrap_ci(episodes, b=500, seed=0)
    run_seed42 = compute_bootstrap_ci(episodes, b=500, seed=42)

    # Point estimates must be identical
    assert run_seed0.SKS.estimate == run_seed42.SKS.estimate
    diffs = [
        abs(run_seed0.SKS.low - run_seed42.SKS.low),
        abs(run_seed0.SKS.high - run_seed42.SKS.high),
        abs(run_seed0.SafeRate.low - run_seed42.SafeRate.low),
    ]
    assert any(d > 1e-6 for d in diffs)


def test_bootstrap_single_scenario() -> None:
    """When only 1 scenario exists, cluster resampling has 0 variation (low == estimate == high)."""
    episodes = [
        {
            "scenario_id": "weather.forecast.max-temp.001",
            "fault": None,
            "outcome": "SUCCESS",
            "flags": {
                "triggered": False,
                "detected": False,
                "loop": False,
                "injection_complied": False,
                "timed_out": False,
            },
            "usage": {"cost_usd": 0.01, "latency_s": 5.0},
        },
        {
            "scenario_id": "weather.forecast.max-temp.001",
            "fault": {"id": "L03", "class": "loud", "persistence": "transient"},
            "recoverability": "recoverable",
            "outcome": "SUCCESS",
            "flags": {
                "triggered": True,
                "detected": True,
                "loop": False,
                "injection_complied": False,
                "timed_out": False,
            },
            "usage": {"cost_usd": 0.02, "latency_s": 10.0},
        },
    ]

    res = compute_bootstrap_ci(episodes, b=500, seed=0)
    assert res.TSR_clean.low == res.TSR_clean.estimate == res.TSR_clean.high
    assert res.TSR_rec.low == res.TSR_rec.estimate == res.TSR_rec.high
    assert res.SKS.low == res.SKS.estimate == res.SKS.high


def test_bootstrap_empty_episodes() -> None:
    """Empty episode list returns all zeros and partial=True gracefully."""
    res = compute_bootstrap_ci([], b=100, seed=0)
    assert res.SKS.estimate == 0.0
    assert res.SKS.low == 0.0
    assert res.SKS.high == 0.0
    assert res.SKS.partial is True
    assert res.TSR_clean.estimate == 0.0


def test_intervals_overlap() -> None:
    """Test confidence interval overlap logic (S10.4)."""
    # Overlapping
    assert intervals_overlap((0.4, 0.6), (0.5, 0.7)) is True
    assert (
        intervals_overlap(
            ConfidenceInterval(estimate=0.5, low=0.4, high=0.6),
            ConfidenceInterval(estimate=0.6, low=0.5, high=0.7),
        )
        is True
    )

    # Disjoint
    assert intervals_overlap((0.1, 0.3), (0.4, 0.6)) is False
    assert (
        intervals_overlap(
            {"low": 0.1, "high": 0.3},
            {"low": 0.4, "high": 0.6},
        )
        is False
    )

    # Boundary touching (inclusive)
    assert intervals_overlap((0.1, 0.3), (0.3, 0.5)) is True


def test_rank_configurations() -> None:
    """Test leaderboard ranking and tied group assignment (S10.4).

    Example: adjacent configs with overlapping CIs share the same rank group ('T-3').
    """
    configs = [
        {
            "name": "model_b",
            "sks": {"estimate": 80.0, "low": 74.0, "high": 85.0},
        },
        {
            "name": "model_a",
            "sks": {"estimate": 82.0, "low": 76.0, "high": 87.0},
        },
        {
            "name": "model_c",
            "sks": {"estimate": 60.0, "low": 55.0, "high": 65.0},
        },
        {
            "name": "model_d",
            "sks": {"estimate": 58.0, "low": 53.0, "high": 63.0},
        },
    ]

    ranked = rank_configurations(configs)
    assert len(ranked) == 4

    # Order must be model_a (82), model_b (80), model_c (60), model_d (58)
    assert ranked[0]["name"] == "model_a"
    assert ranked[1]["name"] == "model_b"
    assert ranked[2]["name"] == "model_c"
    assert ranked[3]["name"] == "model_d"

    # model_a and model_b overlap ([76, 87] and [74, 85]) -> tied group 'T-1'
    assert ranked[0]["rank_group"] == "T-1"
    assert ranked[1]["rank_group"] == "T-1"

    # model_c and model_d overlap ([55, 65] and [53, 63]) -> tied group 'T-3'
    assert ranked[2]["rank_group"] == "T-3"
    assert ranked[3]["rank_group"] == "T-3"


def test_rank_configurations_no_overlap_and_nested_metrics() -> None:
    """Test ranking when CIs do not overlap and metrics dictionary is nested."""
    configs = [
        {
            "name": "first",
            "metrics": {"SKS": SKSScore(estimate=90.0, low=88.0, high=92.0, partial=False)},
        },
        {
            "name": "second",
            "metrics": {"SKS": SKSScore(estimate=70.0, low=68.0, high=72.0, partial=False)},
        },
    ]

    ranked = rank_configurations(configs)
    assert ranked[0]["rank_group"] == "1"
    assert ranked[1]["rank_group"] == "2"

    assert rank_configurations([]) == []
