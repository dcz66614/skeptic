"""Cluster bootstrap confidence intervals and ranking algorithms (E47, S10.4).

Implements scenario-level cluster bootstrap with replacement (B=1000, default_rng(0)),
reports point estimate [low, high] confidence intervals (2.5% and 97.5% percentiles),
and provides configuration ranking with tied group labeling (e.g. 'T-3').
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from skeptic_agent.scoring.metrics import (
    ConfidenceInterval,
    ReportMetrics,
    SKSScore,
    _get_val,
    compute_point_metrics,
)


def compute_bootstrap_ci(
    episodes: Sequence[Any],
    *,
    b: int = 1000,
    seed: int | np.random.Generator | None = 0,
    alpha: float = 0.05,
) -> ReportMetrics:
    """Compute cluster bootstrap confidence intervals grouped by scenario_id (S10.4).

    Algorithm:
    - Clusters are unique scenario IDs.
    - Draws B resamples with replacement of size equal to total scenarios count.
    - Recomputes all metrics on the aggregated resampled episodes.
    - Uses default_rng(seed) (default seed=0) for full reproducibility.
    - Takes (alpha/2) and (1 - alpha/2) percentiles (default 2.5% and 97.5%).
    - Reports Point estimate with [low, high] CI.
    """
    point_est = compute_point_metrics(episodes)
    if not episodes:
        zero_ci = ConfidenceInterval(estimate=0.0, low=0.0, high=0.0)
        return ReportMetrics(
            TSR_clean=zero_ci,
            TSR_rec=zero_ci,
            RR=zero_ci,
            SafeRate=zero_ci,
            FSR=zero_ci,
            SCR=zero_ci,
            ICR=zero_ci,
            LoopRate=zero_ci,
            DetectRate=zero_ci,
            UntriggeredRate=zero_ci,
            Cost=zero_ci,
            Latency=zero_ci,
            SKS=SKSScore(estimate=0.0, low=0.0, high=0.0, partial=True),
        )

    # Group episodes by scenario_id
    scenarios_map: dict[str, list[Any]] = {}
    for ep in episodes:
        sc_id = str(_get_val(ep, "scenario_id", ""))
        scenarios_map.setdefault(sc_id, []).append(ep)

    scenario_ids = sorted(scenarios_map.keys())
    n_scenarios = len(scenario_ids)

    if n_scenarios <= 1 or b <= 0:

        def _make_single_ci(val: float) -> ConfidenceInterval:
            return ConfidenceInterval(estimate=val, low=val, high=val)

        return ReportMetrics(
            TSR_clean=_make_single_ci(point_est.TSR_clean),
            TSR_rec=_make_single_ci(point_est.TSR_rec),
            RR=_make_single_ci(point_est.RR),
            SafeRate=_make_single_ci(point_est.SafeRate),
            FSR=_make_single_ci(point_est.FSR),
            SCR=_make_single_ci(point_est.SCR),
            ICR=_make_single_ci(point_est.ICR),
            LoopRate=_make_single_ci(point_est.LoopRate),
            DetectRate=_make_single_ci(point_est.DetectRate),
            UntriggeredRate=_make_single_ci(point_est.UntriggeredRate),
            Cost=_make_single_ci(point_est.Cost),
            Latency=_make_single_ci(point_est.Latency),
            SKS=SKSScore(
                estimate=point_est.SKS,
                low=point_est.SKS,
                high=point_est.SKS,
                partial=point_est.partial,
            ),
        )

    # Initialize deterministic RNG (S10.4: default_rng(0))
    if isinstance(seed, np.random.Generator):
        rng = seed
    elif seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    # Pre-draw random indices for all B resamples: shape (b, n_scenarios)
    resample_matrix = rng.choice(n_scenarios, size=(b, n_scenarios), replace=True)

    # Pre-map scenario indices to lists of episodes
    scenario_episode_lists = [scenarios_map[sid] for sid in scenario_ids]

    # Arrays to accumulate bootstrap replicates
    tsr_clean_boot = np.empty(b, dtype=float)
    tsr_rec_boot = np.empty(b, dtype=float)
    rr_boot = np.empty(b, dtype=float)
    safe_rate_boot = np.empty(b, dtype=float)
    fsr_boot = np.empty(b, dtype=float)
    scr_boot = np.empty(b, dtype=float)
    icr_boot = np.empty(b, dtype=float)
    loop_rate_boot = np.empty(b, dtype=float)
    detect_rate_boot = np.empty(b, dtype=float)
    untriggered_rate_boot = np.empty(b, dtype=float)
    cost_boot = np.empty(b, dtype=float)
    latency_boot = np.empty(b, dtype=float)
    sks_boot = np.empty(b, dtype=float)

    for i in range(b):
        sampled_indices = resample_matrix[i]
        batch_episodes: list[Any] = []
        for idx in sampled_indices:
            batch_episodes.extend(scenario_episode_lists[idx])

        m = compute_point_metrics(batch_episodes)
        tsr_clean_boot[i] = m.TSR_clean
        tsr_rec_boot[i] = m.TSR_rec
        rr_boot[i] = m.RR
        safe_rate_boot[i] = m.SafeRate
        fsr_boot[i] = m.FSR
        scr_boot[i] = m.SCR
        icr_boot[i] = m.ICR
        loop_rate_boot[i] = m.LoopRate
        detect_rate_boot[i] = m.DetectRate
        untriggered_rate_boot[i] = m.UntriggeredRate
        cost_boot[i] = m.Cost
        latency_boot[i] = m.Latency
        sks_boot[i] = m.SKS

    pct_low = 100.0 * (alpha / 2.0)
    pct_high = 100.0 * (1.0 - (alpha / 2.0))

    def _ci(
        est: float,
        samples: np.ndarray,
        is_rate: bool = True,
        is_sks: bool = False,
    ) -> tuple[float, float]:
        l_val = float(np.percentile(samples, pct_low))
        h_val = float(np.percentile(samples, pct_high))
        if is_rate:
            l_val = max(0.0, min(1.0, l_val))
            h_val = max(0.0, min(1.0, h_val))
        elif is_sks:
            l_val = max(0.0, min(100.0, l_val))
            h_val = max(0.0, min(100.0, h_val))
        else:
            l_val = max(0.0, l_val)
        return l_val, h_val

    tc_low, tc_high = _ci(point_est.TSR_clean, tsr_clean_boot)
    tr_low, tr_high = _ci(point_est.TSR_rec, tsr_rec_boot)
    rr_low, rr_high = _ci(point_est.RR, rr_boot)
    sr_low, sr_high = _ci(point_est.SafeRate, safe_rate_boot)
    fsr_low, fsr_high = _ci(point_est.FSR, fsr_boot)
    scr_low, scr_high = _ci(point_est.SCR, scr_boot)
    icr_low, icr_high = _ci(point_est.ICR, icr_boot)
    loop_low, loop_high = _ci(point_est.LoopRate, loop_rate_boot)
    det_low, det_high = _ci(point_est.DetectRate, detect_rate_boot)
    untr_low, untr_high = _ci(point_est.UntriggeredRate, untriggered_rate_boot)
    cost_low, cost_high = _ci(point_est.Cost, cost_boot, is_rate=False)
    lat_low, lat_high = _ci(point_est.Latency, latency_boot, is_rate=False)
    sks_low, sks_high = _ci(point_est.SKS, sks_boot, is_rate=False, is_sks=True)

    return ReportMetrics(
        TSR_clean=ConfidenceInterval(estimate=point_est.TSR_clean, low=tc_low, high=tc_high),
        TSR_rec=ConfidenceInterval(estimate=point_est.TSR_rec, low=tr_low, high=tr_high),
        RR=ConfidenceInterval(estimate=point_est.RR, low=rr_low, high=rr_high),
        SafeRate=ConfidenceInterval(estimate=point_est.SafeRate, low=sr_low, high=sr_high),
        FSR=ConfidenceInterval(estimate=point_est.FSR, low=fsr_low, high=fsr_high),
        SCR=ConfidenceInterval(estimate=point_est.SCR, low=scr_low, high=scr_high),
        ICR=ConfidenceInterval(estimate=point_est.ICR, low=icr_low, high=icr_high),
        LoopRate=ConfidenceInterval(estimate=point_est.LoopRate, low=loop_low, high=loop_high),
        DetectRate=ConfidenceInterval(estimate=point_est.DetectRate, low=det_low, high=det_high),
        UntriggeredRate=ConfidenceInterval(
            estimate=point_est.UntriggeredRate, low=untr_low, high=untr_high
        ),
        Cost=ConfidenceInterval(estimate=point_est.Cost, low=cost_low, high=cost_high),
        Latency=ConfidenceInterval(estimate=point_est.Latency, low=lat_low, high=lat_high),
        SKS=SKSScore(estimate=point_est.SKS, low=sks_low, high=sks_high, partial=point_est.partial),
    )


def intervals_overlap(
    ci1: ConfidenceInterval | SKSScore | tuple[float, float] | dict[str, Any] | Any,
    ci2: ConfidenceInterval | SKSScore | tuple[float, float] | dict[str, Any] | Any,
) -> bool:
    """Check if two confidence intervals overlap (S10.4)."""

    def _extract(ci: Any) -> tuple[float, float]:
        if isinstance(ci, (ConfidenceInterval, SKSScore)):
            return ci.low, ci.high
        if isinstance(ci, tuple):
            if len(ci) == 3:
                return float(ci[1]), float(ci[2])
            return float(ci[0]), float(ci[1])
        if isinstance(ci, dict):
            return float(ci["low"]), float(ci["high"])
        return float(ci.low), float(ci.high)

    low1, high1 = _extract(ci1)
    low2, high2 = _extract(ci2)
    return max(low1, low2) <= min(high1, high2)


def rank_configurations(
    configs: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rank leaderboard configurations by SKS point estimate and group overlapping CIs (S10.4).

    Configs are sorted descending by point estimate. If adjacent configs have overlapping
    confidence intervals, they are grouped into a tied rank group (e.g. 'T-3').
    """
    if not configs:
        return []

    def _get_sks(item: dict[str, Any]) -> tuple[float, float, float]:
        if "sks" in item:
            s = item["sks"]
        elif "metrics" in item and "SKS" in item["metrics"]:
            s = item["metrics"]["SKS"]
        else:
            raise KeyError("Configuration missing 'sks' or 'metrics.SKS'")

        if isinstance(s, (ConfidenceInterval, SKSScore)):
            return s.estimate, s.low, s.high
        return float(s["estimate"]), float(s["low"]), float(s["high"])

    # Sort descending by point estimate
    sorted_items = sorted(
        configs,
        key=lambda c: _get_sks(c)[0],
        reverse=True,
    )

    n = len(sorted_items)
    # Determine contiguous groups of overlapping adjacent CIs
    groups: list[list[int]] = []
    current_group: list[int] = [0]
    for i in range(1, n):
        prev_sks = _get_sks(sorted_items[i - 1])
        curr_sks = _get_sks(sorted_items[i])
        if intervals_overlap(prev_sks, curr_sks):
            current_group.append(i)
        else:
            groups.append(current_group)
            current_group = [i]
    groups.append(current_group)

    results: list[dict[str, Any]] = []
    for group in groups:
        rank_num = group[0] + 1
        rank_str = f"T-{rank_num}" if len(group) > 1 else str(rank_num)
        for idx in group:
            res = dict(sorted_items[idx])
            res["rank_group"] = rank_str
            results.append(res)

    return results
