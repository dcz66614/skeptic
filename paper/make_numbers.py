#!/usr/bin/env python3
"""Deterministic numbers extraction for L74 reduced-scope flash experiment.

Reads:
- paper/data/l71_flash/none/summary.json
- paper/data/l71_flash/recommended/summary.json
- paper/data/l71_flash/ledger_flash.csv

Writes:
- paper/numbers.json (LF, 2-space indent, sorted keys, no timestamps)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

METRIC_NAMES = [
    "DetectRate",
    "FSR",
    "ICR",
    "LoopRate",
    "SCR",
    "SafeRate",
    "SKS",
]

OFF_PEAK_RATE_IN_PER_MTOK = 14.29
OFF_PEAK_RATE_OUT_PER_MTOK = 57.10
HARD_CAP_CREDITS = 150


def compute_credits_upper_bound(tokens_in: int, tokens_out: int) -> float:
    """Compute upper bound credit estimate from token counts using off-peak rates."""
    return (tokens_in / 1_000_000.0) * OFF_PEAK_RATE_IN_PER_MTOK + (
        tokens_out / 1_000_000.0
    ) * OFF_PEAK_RATE_OUT_PER_MTOK


def generate_numbers(base_dir: Path | None = None) -> dict[str, Any]:
    """Extract and compute deterministic experiment numbers from raw data files."""
    repo_root = Path(__file__).resolve().parent.parent if base_dir is None else base_dir

    data_dir = repo_root / "paper" / "data" / "l71_flash"
    none_summary_path = data_dir / "none" / "summary.json"
    rec_summary_path = data_dir / "recommended" / "summary.json"
    ledger_path = data_dir / "ledger_flash.csv"

    with none_summary_path.open("r", encoding="utf-8") as f:
        none_data: dict[str, Any] = json.load(f)

    with rec_summary_path.open("r", encoding="utf-8") as f:
        rec_data: dict[str, Any] = json.load(f)

    # Outcome counts derived from episodes
    def summarize_config(
        data: dict[str, Any],
    ) -> tuple[int, int, dict[str, int], dict[str, Any]]:
        episodes_list = data.get("episodes", [])
        ep_count = len(episodes_list)
        err_count = sum(1 for ep in episodes_list if ep.get("outcome") == "ERROR")
        outcomes: dict[str, int] = {}
        for ep in episodes_list:
            outcome = ep.get("outcome", "UNKNOWN")
            outcomes[outcome] = outcomes.get(outcome, 0) + 1

        agent_metrics = data.get("agents", [{}])[0].get("metrics", {}) if data.get("agents") else {}
        metrics: dict[str, Any] = {}
        for k in METRIC_NAMES:
            if k in agent_metrics:
                metrics[k] = agent_metrics[k]

        return ep_count, err_count, outcomes, metrics

    none_ep, none_err, none_outcomes, none_metrics = summarize_config(none_data)
    rec_ep, rec_err, rec_outcomes, rec_metrics = summarize_config(rec_data)

    total_episodes = none_ep + rec_ep
    total_errors = none_err + rec_err

    # Deltas (recommended minus none)
    sks_delta = (
        rec_metrics["SKS"]["estimate"] - none_metrics["SKS"]["estimate"]
        if "SKS" in rec_metrics and "SKS" in none_metrics
        else 0.0
    )
    fsr_delta = (
        rec_metrics["FSR"]["estimate"] - none_metrics["FSR"]["estimate"]
        if "FSR" in rec_metrics and "FSR" in none_metrics
        else 0.0
    )
    detect_delta = (
        rec_metrics["DetectRate"]["estimate"] - none_metrics["DetectRate"]["estimate"]
        if "DetectRate" in rec_metrics and "DetectRate" in none_metrics
        else 0.0
    )
    safe_delta = (
        rec_metrics["SafeRate"]["estimate"] - none_metrics["SafeRate"]["estimate"]
        if "SafeRate" in rec_metrics and "SafeRate" in none_metrics
        else 0.0
    )
    scr_delta = (
        rec_metrics["SCR"]["estimate"] - none_metrics["SCR"]["estimate"]
        if "SCR" in rec_metrics and "SCR" in none_metrics
        else 0.0
    )

    # Ledger deduplication by run_id (keep last row per run_id)
    ledger_runs: dict[str, dict[str, Any]] = {}
    with ledger_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r_id = row["run_id"]
            tin = int(row["tokens_in"])
            tout = int(row["tokens_out"])
            ledger_runs[r_id] = {
                "cost_usd": float(row["cost_usd"]),
                "episodes": int(row["episodes"]),
                "estimated_credits_from_tokens": round(compute_credits_upper_bound(tin, tout), 8),
                "model": row["model"],
                "run_id": r_id,
                "tokens_in": tin,
                "tokens_out": tout,
                "tokens_total": tin + tout,
            }

    none_run_id = none_data.get("run_id", "")
    rec_run_id = rec_data.get("run_id", "")

    total_tokens_in = sum(r["tokens_in"] for r in ledger_runs.values())
    total_tokens_out = sum(r["tokens_out"] for r in ledger_runs.values())
    total_tokens = total_tokens_in + total_tokens_out
    total_cost_usd = sum(r["cost_usd"] for r in ledger_runs.values())
    total_credits = round(compute_credits_upper_bound(total_tokens_in, total_tokens_out), 8)

    tokens_by_run: dict[str, dict[str, Any]] = {}
    for r_id, r_info in ledger_runs.items():
        cfg_name = (
            "none" if r_id == none_run_id else "recommended" if r_id == rec_run_id else "other"
        )
        tokens_by_run[r_id] = {
            "config": cfg_name,
            "cost_usd": r_info["cost_usd"],
            "episodes": r_info["episodes"],
            "estimated_credits_from_tokens": r_info["estimated_credits_from_tokens"],
            "model": r_info["model"],
            "run_id": r_id,
            "tokens_in": r_info["tokens_in"],
            "tokens_out": r_info["tokens_out"],
            "tokens_total": r_info["tokens_total"],
        }

    # Build complete deterministic numbers dictionary
    numbers: dict[str, Any] = {
        "configs": {
            "none": {
                "by_fault": none_data.get("by_fault", {}),
                "episodes": none_ep,
                "errors": none_err,
                "guard_actions": none_data.get("guard_actions", {}),
                "metrics": none_metrics,
                "outcomes": dict(sorted(none_outcomes.items())),
                "run_id": none_run_id,
                "total_cost_usd": float(none_data.get("total_cost_usd", 0.0)),
            },
            "recommended": {
                "by_fault": rec_data.get("by_fault", {}),
                "episodes": rec_ep,
                "errors": rec_err,
                "guard_actions": rec_data.get("guard_actions", {}),
                "metrics": rec_metrics,
                "outcomes": dict(sorted(rec_outcomes.items())),
                "run_id": rec_run_id,
                "total_cost_usd": float(rec_data.get("total_cost_usd", 0.0)),
            },
        },
        "deltas": {
            "recommended_minus_none": {
                "DetectRate": detect_delta,
                "FSR": fsr_delta,
                "SCR": scr_delta,
                "SKS": sks_delta,
                "SafeRate": safe_delta,
            }
        },
        "formatted": {
            "configs": {
                "none": {
                    "DetectRate": (
                        f"{none_metrics['DetectRate']['estimate'] * 100:.2f}%"
                        f" [{none_metrics['DetectRate']['low'] * 100:.2f}%,"
                        f" {none_metrics['DetectRate']['high'] * 100:.2f}%]"
                    ),
                    "FSR": (
                        f"{none_metrics['FSR']['estimate'] * 100:.2f}%"
                        f" [{none_metrics['FSR']['low'] * 100:.2f}%,"
                        f" {none_metrics['FSR']['high'] * 100:.2f}%]"
                    ),
                    "SCR": (
                        f"{none_metrics['SCR']['estimate'] * 100:.2f}%"
                        f" [{none_metrics['SCR']['low'] * 100:.2f}%,"
                        f" {none_metrics['SCR']['high'] * 100:.2f}%]"
                    ),
                    "SafeRate": (
                        f"{none_metrics['SafeRate']['estimate'] * 100:.2f}%"
                        f" [{none_metrics['SafeRate']['low'] * 100:.2f}%,"
                        f" {none_metrics['SafeRate']['high'] * 100:.2f}%]"
                    ),
                    "SKS": (
                        f"{none_metrics['SKS']['estimate']:.2f}"
                        f" [{none_metrics['SKS']['low']:.2f},"
                        f" {none_metrics['SKS']['high']:.2f}]"
                    ),
                },
                "recommended": {
                    "DetectRate": (
                        f"{rec_metrics['DetectRate']['estimate'] * 100:.2f}%"
                        f" [{rec_metrics['DetectRate']['low'] * 100:.2f}%,"
                        f" {rec_metrics['DetectRate']['high'] * 100:.2f}%]"
                    ),
                    "FSR": (
                        f"{rec_metrics['FSR']['estimate'] * 100:.2f}%"
                        f" [{rec_metrics['FSR']['low'] * 100:.2f}%,"
                        f" {rec_metrics['FSR']['high'] * 100:.2f}%]"
                    ),
                    "SCR": (
                        f"{rec_metrics['SCR']['estimate'] * 100:.2f}%"
                        f" [{rec_metrics['SCR']['low'] * 100:.2f}%,"
                        f" {rec_metrics['SCR']['high'] * 100:.2f}%]"
                    ),
                    "SafeRate": (
                        f"{rec_metrics['SafeRate']['estimate'] * 100:.2f}%"
                        f" [{rec_metrics['SafeRate']['low'] * 100:.2f}%,"
                        f" {rec_metrics['SafeRate']['high'] * 100:.2f}%]"
                    ),
                    "SKS": (
                        f"{rec_metrics['SKS']['estimate']:.2f}"
                        f" [{rec_metrics['SKS']['low']:.2f},"
                        f" {rec_metrics['SKS']['high']:.2f}]"
                    ),
                },
            },
            "credits": {
                "none": f"{ledger_runs[none_run_id]['estimated_credits_from_tokens']:.2f}",
                "recommended": f"{ledger_runs[rec_run_id]['estimated_credits_from_tokens']:.2f}",
                "total": f"{total_credits:.2f}",
            },
            "deltas": {
                "DetectRate": f"{detect_delta * 100:+.2f}%",
                "FSR": f"{fsr_delta * 100:+.2f}%",
                "SCR": f"{scr_delta * 100:+.2f}%",
                "SKS": f"{sks_delta:+.2f}",
                "SafeRate": f"{safe_delta * 100:+.2f}%",
            },
        },
        "provenance": {
            "document_labels": {
                "official_matrix_reference": "S16.2",
                "prior_rerun": "L71ds",
                "prior_task": "L71",
                "task": "L74",
                "task_reduced": "L74-reduced",
            },
            "experiment_date": "2026-11-11",
            "git_sha": none_data.get("git_sha", "8624def"),
            "hard_cap_credits": HARD_CAP_CREDITS,
            "matrix_id": none_data.get("config", {}).get("project", "leaderboard-v1-reduced-flash"),
            "model_id": (
                none_data.get("agents", [{}])[0].get("model", "")
                if none_data.get("agents")
                else "compat/deepseek-v4.1-flash-sg"
            ),
            "note": "reduced scope; not S16.2",
            "profile": none_data.get("config", {}).get("profile", "silent-core"),
            "run_ids": {
                "none": none_run_id,
                "recommended": rec_run_id,
            },
            "scenarios": 56,
            "seed": 1,
            "suite": "core-v1-l71-reduced",
        },
        "rounded": {
            "configs": {
                "none": {
                    "DetectRate": {
                        "estimate": round(none_metrics["DetectRate"]["estimate"] * 100, 2),
                        "high": round(none_metrics["DetectRate"]["high"] * 100, 2),
                        "low": round(none_metrics["DetectRate"]["low"] * 100, 2),
                    },
                    "FSR": {
                        "estimate": round(none_metrics["FSR"]["estimate"] * 100, 2),
                        "high": round(none_metrics["FSR"]["high"] * 100, 2),
                        "low": round(none_metrics["FSR"]["low"] * 100, 2),
                    },
                    "SCR": {
                        "estimate": round(none_metrics["SCR"]["estimate"] * 100, 2),
                        "high": round(none_metrics["SCR"]["high"] * 100, 2),
                        "low": round(none_metrics["SCR"]["low"] * 100, 2),
                    },
                    "SafeRate": {
                        "estimate": round(none_metrics["SafeRate"]["estimate"] * 100, 2),
                        "high": round(none_metrics["SafeRate"]["high"] * 100, 2),
                        "low": round(none_metrics["SafeRate"]["low"] * 100, 2),
                    },
                    "SKS": {
                        "estimate": round(none_metrics["SKS"]["estimate"], 2),
                        "high": round(none_metrics["SKS"]["high"], 2),
                        "low": round(none_metrics["SKS"]["low"], 2),
                    },
                },
                "recommended": {
                    "DetectRate": {
                        "estimate": round(rec_metrics["DetectRate"]["estimate"] * 100, 2),
                        "high": round(rec_metrics["DetectRate"]["high"] * 100, 2),
                        "low": round(rec_metrics["DetectRate"]["low"] * 100, 2),
                    },
                    "FSR": {
                        "estimate": round(rec_metrics["FSR"]["estimate"] * 100, 2),
                        "high": round(rec_metrics["FSR"]["high"] * 100, 2),
                        "low": round(rec_metrics["FSR"]["low"] * 100, 2),
                    },
                    "SCR": {
                        "estimate": round(rec_metrics["SCR"]["estimate"] * 100, 2),
                        "high": round(rec_metrics["SCR"]["high"] * 100, 2),
                        "low": round(rec_metrics["SCR"]["low"] * 100, 2),
                    },
                    "SafeRate": {
                        "estimate": round(rec_metrics["SafeRate"]["estimate"] * 100, 2),
                        "high": round(rec_metrics["SafeRate"]["high"] * 100, 2),
                        "low": round(rec_metrics["SafeRate"]["low"] * 100, 2),
                    },
                    "SKS": {
                        "estimate": round(rec_metrics["SKS"]["estimate"], 2),
                        "high": round(rec_metrics["SKS"]["high"], 2),
                        "low": round(rec_metrics["SKS"]["low"], 2),
                    },
                },
            },
            "credits": {
                "none": round(ledger_runs[none_run_id]["estimated_credits_from_tokens"], 2),
                "recommended": round(ledger_runs[rec_run_id]["estimated_credits_from_tokens"], 2),
                "total": round(total_credits, 2),
            },
            "deltas": {
                "DetectRate": round(detect_delta * 100, 2),
                "FSR": round(fsr_delta * 100, 2),
                "SCR": round(scr_delta * 100, 2),
                "SKS": round(sks_delta, 2),
                "SafeRate": round(safe_delta * 100, 2),
            },
        },
        "tokens": {
            "by_run": tokens_by_run,
            "cost_usd_note": (
                "WorkBuddy bills credits that the relay does not report in"
                " responses; relay cost_usd is 0.0"
            ),
            "credit_rates_per_mtok": {
                "formula": ("(tokens_in / 1_000_000) * 14.29 + (tokens_out / 1_000_000) * 57.1"),
                "notes": ("UPPER BOUND ESTIMATE ignoring cached rate discount (0.29/MTok)"),
                "off_peak_in": OFF_PEAK_RATE_IN_PER_MTOK,
                "off_peak_out": OFF_PEAK_RATE_OUT_PER_MTOK,
            },
            "total": {
                "cost_usd": total_cost_usd,
                "episodes": total_episodes,
                "estimated_credits_from_tokens": total_credits,
                "tokens_in": total_tokens_in,
                "tokens_out": total_tokens_out,
                "tokens_total": total_tokens,
            },
        },
        "totals": {
            "episodes": total_episodes,
            "errors": total_errors,
        },
    }

    return numbers


def main() -> None:
    """Generate paper/numbers.json deterministically."""
    repo_root = Path(__file__).resolve().parent.parent
    numbers = generate_numbers(repo_root)
    out_path = repo_root / "paper" / "numbers.json"
    content = json.dumps(numbers, indent=2, sort_keys=True) + "\n"
    out_path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Wrote {out_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
