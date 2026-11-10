"""Build the Skeptic leaderboard static site (L72, S16.3).

Reads ``results.jsonl`` (or the smoke placeholder) and ``models.yaml``, ranks
configurations with the S10.4 interval rule, and writes the ``/leaderboard/``
pages plus ``data/results.csv``, ``data/summary.json`` and cassette zip volumes.
CSS and JS are inlined. Nothing is loaded from a CDN.

Run from the repository root::

    uv run python site/build.py
    uv run python site/build.py --results path/to/results.jsonl --out site/out
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from skeptic_agent import __version__
from skeptic_agent.faults.catalog import catalogue
from skeptic_agent.guards.presets import resolve_guards
from skeptic_agent.runner.matrix import compute_worst_scenarios
from skeptic_agent.scoring.bootstrap import compute_bootstrap_ci, rank_configurations
from skeptic_agent.scoring.metrics import compute_point_metrics

log = logging.getLogger("skeptic.site")

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = Path(__file__).resolve().parent / "templates"
DEFAULT_MODELS = REPO_ROOT / "bench" / "leaderboard" / "models.yaml"
DEFAULT_OUT = REPO_ROOT / "site" / "out"
ARCHIVE_MAX_BYTES = 100 * 1024 * 1024
PLACEHOLDER_GENERATED_AT = "2026-11-10T00:00:00Z"
PLACEHOLDER_RUN_ID = "20261110-000000-a17b01"
PLANNED_SEEDS = (1, 2, 3)
BOOTSTRAP_B = 1000
# S16.2 contrasts guards ``none`` with ``recommended``.
_ON_PREFERENCE = ("recommended", "all")
OUTCOMES = (
    "SUCCESS",
    "HONEST_FAILURE",
    "FALSE_SUCCESS",
    "SILENT_CORRUPTION",
    "INJECTED",
    "NO_ANSWER",
    "ERROR",
    "NOT_APPLICABLE",
)
_ZIP_DATE = (2026, 11, 10, 0, 0, 0)
_DELTA_METRICS = ("FSR", "SCR", "SKS")
_SCENARIOS = (
    ("weather.forecast.max-temp.001", "sb_weather"),
    ("fx.convert.spot-rate.002", "sb_fx"),
)
_FAULT_META = {
    "L01": {"id": "L01", "class": "loud", "persistence": "transient"},
    "S04": {"id": "S04", "class": "silent", "persistence": "permanent"},
    "A01": {"id": "A01", "class": "adversarial", "persistence": "permanent"},
}
# (fault id or None, outcome, recoverability). Identical mixes make the
# bootstrap interval a point, so equal scores tie and unequal scores do not.
_STRONG_NONE = (
    (None, "SUCCESS", None),
    ("L01", "SUCCESS", "recoverable"),
    ("S04", "SILENT_CORRUPTION", "unrecoverable"),
    ("A01", "HONEST_FAILURE", "unrecoverable"),
)
_STRONG_ON = (
    (None, "SUCCESS", None),
    ("L01", "SUCCESS", "recoverable"),
    ("S04", "HONEST_FAILURE", "unrecoverable"),
    ("A01", "HONEST_FAILURE", "unrecoverable"),
)
_WEAK_NONE = (
    (None, "SUCCESS", None),
    ("L01", "HONEST_FAILURE", "recoverable"),
    ("S04", "SILENT_CORRUPTION", "unrecoverable"),
    ("A01", "INJECTED", "unrecoverable"),
)
_WEAK_ON = (
    (None, "SUCCESS", None),
    ("L01", "HONEST_FAILURE", "recoverable"),
    ("S04", "HONEST_FAILURE", "unrecoverable"),
    ("A01", "HONEST_FAILURE", "unrecoverable"),
)
_PLACEHOLDER_CONFIGS = (
    ("reference", "compat/gpt-5.6-terra", "none", _STRONG_NONE, 0.02),
    ("reference", "compat/gpt-5.6-terra", "recommended", _STRONG_ON, 0.02),
    ("reference", "compat/deepseek-v4-pro", "none", _STRONG_NONE, 0.004),
    ("reference", "compat/deepseek-v4-pro", "recommended", _STRONG_ON, 0.004),
    ("reference", "openrouter/openai/gpt-4o-mini", "none", _WEAK_NONE, 0.001),
    ("reference", "openrouter/openai/gpt-4o-mini", "recommended", _WEAK_ON, 0.001),
    ("reference", "compat/hy3", "none", _WEAK_NONE, 0.0),
    ("langgraph", "compat/gpt-5.6-terra", "none", _STRONG_NONE, 0.02),
)

CSV_COLUMNS = (
    "episode_id",
    "run_id",
    "config_id",
    "scenario_id",
    "sandbox",
    "seed",
    "fault_id",
    "fault_class",
    "outcome",
    "triggered",
    "adapter",
    "model",
    "prompt_variant",
    "guards",
    "cost_usd",
    "latency_s",
    "cassette",
)


@dataclass(frozen=True)
class ArchivePack:
    """Zip volumes written under ``data/`` and the volume that holds each entry."""

    files: tuple[str, ...]
    location: Mapping[str, str]


def guards_label(guards: Any) -> str:
    """Return ``none``, ``recommended``, ``all``, or a comma-joined name list."""
    if guards is None:
        return "none"
    if isinstance(guards, str):
        text = guards.strip()
        if not text or text in {"none", "all", "recommended"}:
            return text or "none"
        return text
    names = [str(item).strip() for item in guards if str(item).strip()]
    if not names:
        return "none"
    key = tuple(sorted(names))
    for preset in ("none", "recommended", "all"):
        if tuple(sorted(resolve_guards(preset))) == key:
            return preset
    return ",".join(sorted(names))


def guards_enabled(label: str) -> bool:
    """Return True when the guard label is not ``none``."""
    return label != "none"


def config_slug(adapter: str, model: str, prompt_variant: str, label: str) -> str:
    """Filesystem-safe id for one leaderboard configuration."""
    raw = f"{adapter}--{model}--{prompt_variant}--{label}"
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)


def episode_config(episode: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Return ``(adapter, model, prompt_variant, guards label)``."""
    agent = episode.get("agent") or {}
    if not isinstance(agent, Mapping):
        agent = {}
    adapter = str(agent.get("adapter") or "reference")
    model = str(agent.get("model") or "unknown")
    variant = str(agent.get("prompt_variant") or "plain")
    return adapter, model, variant, guards_label(agent.get("guards"))


def rank_board(configs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank configs by SKS and merge adjacent overlapping intervals (S10.4).

    The label is ``T-<first place>`` when a group has more than one config,
    otherwise the place number. Overlap is adjacent: A~B and B~C share a group
    even when A does not overlap C.
    """
    return rank_configurations(configs)


def load_models(path: Path) -> dict[str, dict[str, Any]]:
    """Load ``skeptic.models/v1`` into a map keyed by model id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("models"), list):
        raise ValueError(f"models file has no models list: {path}")
    models: dict[str, dict[str, Any]] = {}
    for item in raw["models"]:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError(f"model entry missing id in {path}")
        model_id = str(item["id"])
        models[model_id] = {
            "id": model_id,
            "display": str(item.get("display") or model_id),
            "group": str(item.get("group") or "unknown"),
            "origin": str(item.get("origin") or "unknown"),
            "tier": str(item.get("tier") or "unknown"),
            "price_in_per_mtok": float(item.get("price_in_per_mtok") or 0.0),
            "price_out_per_mtok": float(item.get("price_out_per_mtok") or 0.0),
            "supports_tools": bool(item.get("supports_tools", False)),
            "notes": str(item.get("notes") or ""),
        }
    if not models:
        raise ValueError(f"models file is empty: {path}")
    return models


def load_results(path: Path) -> list[dict[str, Any]]:
    """Load ``results.jsonl`` from a file or a directory that contains one."""
    file = path if path.is_file() else path / "results.jsonl"
    if not file.is_file():
        raise FileNotFoundError(f"results.jsonl not found: {file}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{file}:{number}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{file}:{number}: expected an object")
        rows.append(item)
    return rows


def placeholder_episodes() -> list[dict[str, Any]]:
    """Smoke-shaped episodes so the site can be built before the L71 run.

    Scores are constructed. They are not measurements of any model.
    """
    episodes: list[dict[str, Any]] = []
    for adapter, model, label, pattern, cost in _PLACEHOLDER_CONFIGS:
        slug = config_slug(adapter, model, "plain", label)
        guard_names = resolve_guards(label)
        for scenario_id, sandbox in _SCENARIOS:
            for fault_id, outcome, recoverability in pattern:
                token = fault_id or "clean"
                episode_id = f"{PLACEHOLDER_RUN_ID}:{scenario_id}:{token}:1"
                fault = None if fault_id is None else dict(_FAULT_META[fault_id])
                episodes.append(
                    {
                        "schema": "skeptic.result/v1",
                        "run_id": PLACEHOLDER_RUN_ID,
                        "episode_id": episode_id,
                        "scenario_id": scenario_id,
                        "sandbox": sandbox,
                        "language": "en",
                        "kind": "read",
                        "fault": fault,
                        "recoverability": recoverability,
                        "agent": {
                            "adapter": adapter,
                            "model": model,
                            "prompt_variant": "plain",
                            "guards": guard_names,
                        },
                        "seed": 1,
                        "outcome": outcome,
                        "flags": {
                            "triggered": fault_id is not None,
                            "detected": outcome == "HONEST_FAILURE",
                            "loop": False,
                            "injection_complied": outcome == "INJECTED",
                            "timed_out": False,
                        },
                        "usage": {
                            "tokens_in": 100,
                            "tokens_out": 20,
                            "cost_usd": cost,
                            "latency_s": 1.0,
                            "steps": 2,
                            "tool_calls": 1,
                        },
                        "cassette": f"cassettes/{slug}__{scenario_id}__{token}__1.jsonl",
                        "error": None,
                    }
                )
    return episodes


def _model_info(models: Mapping[str, Mapping[str, Any]], model_id: str) -> Mapping[str, Any]:
    found = models.get(model_id)
    if found is not None:
        return found
    return {
        "id": model_id,
        "display": model_id,
        "group": "unknown",
        "origin": "unknown",
        "tier": "unknown",
        "price_in_per_mtok": 0.0,
        "price_out_per_mtok": 0.0,
        "supports_tools": False,
        "notes": "",
    }


def _fault_of(episode: Mapping[str, Any]) -> tuple[str, str]:
    fault = episode.get("fault")
    if not isinstance(fault, Mapping):
        return "", ""
    return str(fault.get("id") or ""), str(fault.get("class") or "")


def _outcome_counts(episodes: Sequence[Mapping[str, Any]], fault_id: str) -> dict[str, int]:
    counts = dict.fromkeys(OUTCOMES, 0)
    for episode in episodes:
        fid, _class_name = _fault_of(episode)
        if fid != fault_id:
            continue
        outcome = str(episode.get("outcome") or "")
        if outcome in counts:
            counts[outcome] += 1
    return counts


def _heat_class(outcome: str, count: int) -> str:
    if count <= 0:
        return "heat-cell-0"
    if outcome == "SUCCESS":
        return "heat-cell-succ"
    if outcome == "HONEST_FAILURE":
        return "heat-cell-warn"
    if outcome in {"FALSE_SUCCESS", "SILENT_CORRUPTION", "INJECTED"}:
        return "heat-cell-danger"
    return ""


def _heat_rows(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    known = {str(entry["id"]) for entry in catalogue()}
    extra = sorted(
        {fid for episode in episodes if (fid := _fault_of(episode)[0]) and fid not in known}
    )
    ordered = [str(entry["id"]) for entry in catalogue()] + extra
    names = {str(entry["id"]): str(entry["name"]) for entry in catalogue()}
    for fault_id in ordered:
        counts = _outcome_counts(episodes, fault_id)
        rows.append(
            {
                "id": fault_id,
                "name": names.get(fault_id, fault_id),
                "total": sum(counts.values()),
                "cells": [
                    {
                        "outcome": outcome,
                        "count": counts[outcome],
                        "css": _heat_class(outcome, counts[outcome]),
                    }
                    for outcome in OUTCOMES
                ],
            }
        )
    return rows


def _sks_band(estimate: float) -> str:
    if estimate >= 80:
        return "high"
    if estimate >= 60:
        return "mid"
    return "low"


def _format_rate_ci(ci: Mapping[str, Any]) -> str:
    return (
        f"{float(ci['estimate']) * 100:.1f}% "
        f"[{float(ci['low']) * 100:.1f}%, {float(ci['high']) * 100:.1f}%]"
    )


def _format_sks_ci(ci: Mapping[str, Any]) -> str:
    text = f"{float(ci['estimate']):.2f} [{float(ci['low']):.2f}, {float(ci['high']):.2f}]"
    if ci.get("partial"):
        text += " partial"
    return text


def _format_cost_ci(ci: Mapping[str, Any]) -> str:
    return f"${float(ci['estimate']):.4f} [${float(ci['low']):.4f}, ${float(ci['high']):.4f}]"


def _format_delta_rate(ci: Mapping[str, Any]) -> str:
    return (
        f"{float(ci['estimate']) * 100:+.1f} pp "
        f"[{float(ci['low']) * 100:+.1f}, {float(ci['high']) * 100:+.1f}]"
    )


def _format_delta_sks(ci: Mapping[str, Any]) -> str:
    return f"{float(ci['estimate']):+.2f} [{float(ci['low']):+.2f}, {float(ci['high']):+.2f}]"


def guard_delta(
    off: Sequence[Mapping[str, Any]],
    on: Sequence[Mapping[str, Any]],
    *,
    b: int = BOOTSTRAP_B,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, dict[str, float]]:
    """Paired scenario-cluster CI for guards-on minus guards-off.

    Matches ``compare_runs``: union of scenario ids, ``default_rng(seed)``,
    percentiles ``alpha/2`` and ``1 - alpha/2``. The point is the full-sample
    difference. Delta intervals are not clamped, because a difference may be
    negative.
    """
    point_off = compute_point_metrics(off)
    point_on = compute_point_metrics(on)
    by_off: dict[str, list[Mapping[str, Any]]] = {}
    by_on: dict[str, list[Mapping[str, Any]]] = {}
    for episode in off:
        by_off.setdefault(str(episode.get("scenario_id") or ""), []).append(episode)
    for episode in on:
        by_on.setdefault(str(episode.get("scenario_id") or ""), []).append(episode)
    scenario_ids = sorted(set(by_off) | set(by_on))

    def _finish(samples: Mapping[str, np.ndarray] | None) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for name in _DELTA_METRICS:
            estimate = float(getattr(point_on, name) - getattr(point_off, name))
            if samples is None:
                low = high = estimate
            else:
                low = float(np.percentile(samples[name], 100.0 * (alpha / 2.0)))
                high = float(np.percentile(samples[name], 100.0 * (1.0 - alpha / 2.0)))
            out[name] = {"estimate": estimate, "low": low, "high": high}
        return out

    if len(scenario_ids) <= 1 or b <= 0:
        return _finish(None)

    rng = np.random.default_rng(seed)
    draws = rng.choice(len(scenario_ids), size=(b, len(scenario_ids)), replace=True)
    samples = {name: np.empty(b, dtype=float) for name in _DELTA_METRICS}
    for index in range(b):
        chosen = [scenario_ids[int(draw)] for draw in draws[index]]
        batch_off = [ep for sid in chosen for ep in by_off.get(sid, [])]
        batch_on = [ep for sid in chosen for ep in by_on.get(sid, [])]
        metrics_off = compute_point_metrics(batch_off) if batch_off else point_off
        metrics_on = compute_point_metrics(batch_on) if batch_on else point_on
        for name in _DELTA_METRICS:
            samples[name][index] = float(getattr(metrics_on, name) - getattr(metrics_off, name))
    return _finish(samples)


def _public_catalogue() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in catalogue():
        rows.append(
            {
                "id": str(entry["id"]),
                "name": str(entry["name"]),
                "fault_class": str(entry["class"]),
                "persistence": str(entry["persistence"]),
                "correct_behavior": str(entry["correct_behavior"]),
            }
        )
    return rows


def assemble(
    episodes: Sequence[dict[str, Any]],
    models: Mapping[str, Mapping[str, Any]],
    *,
    b: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Group episodes, score them, and rank the board."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for episode in episodes:
        grouped.setdefault(episode_config(episode), []).append(episode)

    pending: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: config_slug(*item)):
        adapter, model, variant, label = key
        info = _model_info(models, model)
        bucket = grouped[key]
        metrics = compute_bootstrap_ci(bucket, b=b, seed=0)
        metrics_dict = metrics.to_dict()
        total_cost = sum(float((ep.get("usage") or {}).get("cost_usd") or 0.0) for ep in bucket)
        slug = config_slug(adapter, model, variant, label)
        pending.append(
            {
                "id": slug,
                "adapter": adapter,
                "model": model,
                "display": str(info["display"]),
                "group": str(info["group"]),
                "origin": str(info["origin"]),
                "tier": str(info["tier"]),
                "prompt_variant": variant,
                "guards": label,
                "guards_on": guards_enabled(label),
                "metrics": metrics_dict,
                "sks_text": _format_sks_ci(metrics_dict["SKS"]),
                "sks_band": _sks_band(float(metrics_dict["SKS"]["estimate"])),
                "rr_text": _format_rate_ci(metrics_dict["RR"]),
                "safe_text": _format_rate_ci(metrics_dict["SafeRate"]),
                "fsr_text": _format_rate_ci(metrics_dict["FSR"]),
                "scr_text": _format_rate_ci(metrics_dict["SCR"]),
                "icr_text": _format_rate_ci(metrics_dict["ICR"]),
                "loop_text": _format_rate_ci(metrics_dict["LoopRate"]),
                "detect_text": _format_rate_ci(metrics_dict["DetectRate"]),
                "tsr_clean_text": _format_rate_ci(metrics_dict["TSR_clean"]),
                "tsr_rec_text": _format_rate_ci(metrics_dict["TSR_rec"]),
                "untriggered_text": _format_rate_ci(metrics_dict["UntriggeredRate"]),
                "cost_text": _format_cost_ci(metrics_dict["Cost"]),
                "latency_text": (
                    f"{float(metrics_dict['Latency']['estimate']):.2f}s "
                    f"[{float(metrics_dict['Latency']['low']):.2f}s, "
                    f"{float(metrics_dict['Latency']['high']):.2f}s]"
                ),
                "total_cost": round(total_cost, 6),
                "episode_count": len(bucket),
                "heat": _heat_rows(bucket),
                "worst": compute_worst_scenarios(bucket),
                "episodes": bucket,
            }
        )

    ranked = rank_board(pending)
    by_base: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
    for row in ranked:
        base = (str(row["adapter"]), str(row["model"]), str(row["prompt_variant"]))
        by_base.setdefault(base, {})[str(row["guards"])] = row

    deltas: list[dict[str, Any]] = []
    for base in sorted(by_base):
        labeled = by_base[base]
        if "none" not in labeled:
            continue
        on_labels = [name for name in _ON_PREFERENCE if name in labeled]
        on_labels.extend(sorted(name for name in labeled if name not in {"none", *on_labels}))
        for on_label in on_labels:
            diff = guard_delta(labeled["none"]["episodes"], labeled[on_label]["episodes"], b=b)
            adapter, model, variant = base
            deltas.append(
                {
                    "adapter": adapter,
                    "model": model,
                    "display": labeled["none"]["display"],
                    "prompt_variant": variant,
                    "off_guards": "none",
                    "on_guards": on_label,
                    "off_id": labeled["none"]["id"],
                    "on_id": labeled[on_label]["id"],
                    "delta_fsr": diff["FSR"],
                    "delta_scr": diff["SCR"],
                    "delta_sks": diff["SKS"],
                    "fsr_text": _format_delta_rate(diff["FSR"]),
                    "scr_text": _format_delta_rate(diff["SCR"]),
                    "sks_text": _format_delta_sks(diff["SKS"]),
                }
            )

    seeds = sorted({int(ep["seed"]) for ep in episodes if ep.get("seed") is not None})
    run_ids = sorted({str(ep.get("run_id") or "") for ep in episodes if ep.get("run_id")})
    return {
        "configs": ranked,
        "deltas": deltas,
        "catalogue": _public_catalogue(),
        "seeds": seeds,
        "run_ids": run_ids,
    }


def safe_arcname(rel: str) -> str:
    """Return a zip-internal path that cannot leave the archive root."""
    text = rel.replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ValueError(f"unsafe cassette path: {rel}")
    parts = [part for part in text.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"unsafe cassette path: {rel}")
    return "/".join(parts)


def _unique_arcname(name: str, seen: set[str]) -> str:
    if name not in seen:
        seen.add(name)
        return name
    path = Path(name)
    index = 2
    while True:
        candidate = str(path.with_name(f"{path.stem}__{index}{path.suffix}")).replace("\\", "/")
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        index += 1


def _read_cassette(
    rel: str,
    results_path: Path | None,
    cassettes_dir: Path | None,
) -> bytes | None:
    candidates: list[Path] = []
    if cassettes_dir is not None:
        candidates.append(cassettes_dir / rel)
    if results_path is not None:
        parent = results_path if results_path.is_dir() else results_path.parent
        candidates.append(parent / rel)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_bytes()
    return None


def _placeholder_cassette(episode: Mapping[str, Any]) -> bytes:
    body = {
        "placeholder": True,
        "episode_id": episode.get("episode_id"),
        "note": "Smoke placeholder. Not a recorded tool transcript.",
    }
    return (json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def collect_cassettes(
    episodes: Sequence[Mapping[str, Any]],
    *,
    placeholder: bool,
    results_path: Path | None,
    cassettes_dir: Path | None,
) -> list[tuple[str, bytes]]:
    """Pair archive names with cassette bytes. Missing real files are listed."""
    entries: list[tuple[str, bytes]] = []
    missing: list[str] = []
    seen: set[str] = set()
    for episode in episodes:
        rel = str(episode.get("cassette") or "")
        if not rel:
            continue
        name = _unique_arcname(safe_arcname(rel), seen)
        data = _read_cassette(rel, results_path, cassettes_dir)
        if data is None:
            if placeholder:
                data = _placeholder_cassette(episode)
            else:
                missing.append(name)
                continue
        entries.append((name, data))
    if placeholder:
        note = b"Smoke placeholder cassette bodies. Not a recorded L71 run.\n"
        entries.append((_unique_arcname("PLACEHOLDER.txt", seen), note))
    if missing:
        text = "Missing cassette files:\n" + "\n".join(missing) + "\n"
        entries.append((_unique_arcname("MISSING.txt", seen), text.encode("utf-8")))
    return entries


def _zip_blob(entries: Sequence[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buf.getvalue()


def _fit_entry(name: str, data: bytes, max_bytes: int) -> list[tuple[str, bytes]]:
    if len(_zip_blob([(name, data)])) <= max_bytes:
        return [(name, data)]
    step = max(1, min(len(data), max_bytes))
    while step > 1 and len(_zip_blob([(f"{name}.part001", data[:step])])) > max_bytes:
        step //= 2
    probe = data[:step] if data else b""
    if len(_zip_blob([(f"{name}.part001", probe)])) > max_bytes:
        raise ValueError(f"archive limit {max_bytes} bytes cannot hold one zip entry")
    parts: list[tuple[str, bytes]] = []
    offset = 0
    index = 1
    while offset < len(data):
        parts.append((f"{name}.part{index:03d}", data[offset : offset + step]))
        offset += step
        index += 1
    return parts


def pack_archives(
    entries: Sequence[tuple[str, bytes]],
    dest_dir: Path,
    *,
    max_bytes: int = ARCHIVE_MAX_BYTES,
) -> ArchivePack:
    """Write one or more zip volumes, each at most ``max_bytes``.

    A single cassette that does not fit is split into ``.partNNN`` members.
    One volume is named ``cassettes.zip``; further volumes are
    ``cassettes-002.zip`` and so on. S16.3 caps a volume at 100 MB.
    """
    if max_bytes < 64:
        raise ValueError("max_bytes must be at least 64")
    pieces: list[tuple[str, bytes]] = []
    first_piece: dict[str, str] = {}
    for name, data in entries:
        fitted = _fit_entry(name, data, max_bytes)
        if fitted:
            first_piece[name] = fitted[0][0]
        pieces.extend(fitted)
    if not pieces:
        pieces = [("README.txt", b"No cassette files were available for this build.\n")]
        first_piece["README.txt"] = "README.txt"

    volumes: list[list[tuple[str, bytes]]] = []
    current: list[tuple[str, bytes]] = []
    for piece in pieces:
        trial = [*current, piece]
        if current and len(_zip_blob(trial)) > max_bytes:
            volumes.append(current)
            current = [piece]
        else:
            current = trial
    if current:
        volumes.append(current)

    dest_dir.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    location: dict[str, str] = {}
    for index, volume in enumerate(volumes, start=1):
        filename = "cassettes.zip" if len(volumes) == 1 else f"cassettes-{index:03d}.zip"
        (dest_dir / filename).write_bytes(_zip_blob(volume))
        names.append(filename)
        for arcname, _data in volume:
            location[arcname] = filename
    for original, piece_name in first_piece.items():
        if piece_name in location:
            location[original] = location[piece_name]
    return ArchivePack(files=tuple(names), location=location)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_csv(path: Path, episodes: Sequence[Mapping[str, Any]]) -> None:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for episode in episodes:
        adapter, model, variant, label = episode_config(episode)
        fault_id, fault_class = _fault_of(episode)
        usage = episode.get("usage") or {}
        flags = episode.get("flags") or {}
        writer.writerow(
            {
                "episode_id": episode.get("episode_id") or "",
                "run_id": episode.get("run_id") or "",
                "config_id": config_slug(adapter, model, variant, label),
                "scenario_id": episode.get("scenario_id") or "",
                "sandbox": episode.get("sandbox") or "",
                "seed": episode.get("seed") if episode.get("seed") is not None else "",
                "fault_id": fault_id,
                "fault_class": fault_class,
                "outcome": episode.get("outcome") or "",
                "triggered": "true" if flags.get("triggered") else "false",
                "adapter": adapter,
                "model": model,
                "prompt_variant": variant,
                "guards": label,
                "cost_usd": usage.get("cost_usd", 0),
                "latency_s": usage.get("latency_s", 0),
                "cassette": episode.get("cassette") or "",
            }
        )
    _write_text(path, buf.getvalue())


def _summary_config(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "rank_group": row["rank_group"],
        "adapter": row["adapter"],
        "model": row["model"],
        "display": row["display"],
        "group": row["group"],
        "origin": row["origin"],
        "tier": row["tier"],
        "prompt_variant": row["prompt_variant"],
        "guards": row["guards"],
        "guards_on": row["guards_on"],
        "metrics": row["metrics"],
        "episode_count": row["episode_count"],
        "total_cost_usd": row["total_cost"],
        "worst_scenarios": row["worst"],
    }


def _summary_delta(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "adapter": row["adapter"],
        "model": row["model"],
        "display": row["display"],
        "prompt_variant": row["prompt_variant"],
        "off_guards": row["off_guards"],
        "on_guards": row["on_guards"],
        "off_id": row["off_id"],
        "on_id": row["on_id"],
        "delta_fsr": row["delta_fsr"],
        "delta_scr": row["delta_scr"],
        "delta_sks": row["delta_sks"],
    }


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _reset_generated(dest: Path) -> None:
    for folder, pattern in (
        ("config", "*.html"),
        ("fault", "*.html"),
        ("data", "cassettes*.zip"),
    ):
        path = dest / folder
        if not path.is_dir():
            continue
        for child in path.glob(pattern):
            child.unlink()


def _filter_values(configs: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return sorted({str(row[key]) for row in configs})


def _stamp_archives(configs: Sequence[dict[str, Any]], location: Mapping[str, str]) -> None:
    fallback = next(iter(location.values()), "")
    for row in configs:
        for item in row["worst"]:
            names = []
            for cassette in item.get("cassettes") or []:
                try:
                    arc = safe_arcname(str(cassette))
                except ValueError:
                    arc = ""
                names.append(location.get(arc, fallback))
            item["volumes"] = names


def _render_to(env: Environment, name: str, path: Path, **context: Any) -> None:
    _write_text(path, env.get_template(name).render(**context))


def _fault_page_rows(
    configs: Sequence[Mapping[str, Any]],
    fault_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in configs:
        counts = _outcome_counts(row["episodes"], fault_id)
        rows.append(
            {
                "id": row["id"],
                "rank_group": row["rank_group"],
                "label": f"{row['display']} · {row['adapter']} · {row['guards']}",
                "total": sum(counts.values()),
                "cells": [
                    {
                        "outcome": outcome,
                        "count": counts[outcome],
                        "css": _heat_class(outcome, counts[outcome]),
                    }
                    for outcome in OUTCOMES
                ],
            }
        )
    return rows


def _render_pages(
    *,
    dest: Path,
    board: Mapping[str, Any],
    models: Mapping[str, Mapping[str, Any]],
    archives: Sequence[str],
    placeholder: bool,
    generated_at: str,
    source: str,
) -> None:
    env = _env()
    configs = list(board["configs"])
    shared = {
        "placeholder": placeholder,
        "generated_at": generated_at,
        "version": __version__,
        "archives": list(archives),
        "outcomes": OUTCOMES,
    }
    title = "Placeholder sample" if placeholder else "Agent Skepticism Leaderboard"
    _render_to(
        env,
        "index.html.j2",
        dest / "index.html",
        **shared,
        root="",
        title=title,
        configs=configs,
        groups=_filter_values(configs, "group"),
        origins=_filter_values(configs, "origin"),
        frameworks=_filter_values(configs, "adapter"),
    )
    for row in configs:
        _render_to(
            env,
            "config.html.j2",
            dest / "config" / f"{row['id']}.html",
            **shared,
            root="../",
            title=str(row["display"]),
            config=row,
        )

    catalogue_rows = list(board["catalogue"])
    known_ids = {str(row["id"]) for row in catalogue_rows}
    for row in configs:
        for episode in row["episodes"]:
            fault_id, _fault_class = _fault_of(episode)
            if fault_id and fault_id not in known_ids:
                catalogue_rows.append(
                    {
                        "id": fault_id,
                        "name": fault_id,
                        "fault_class": _fault_class,
                        "persistence": "",
                        "correct_behavior": "",
                    }
                )
                known_ids.add(fault_id)
    for entry in catalogue_rows:
        _render_to(
            env,
            "fault.html.j2",
            dest / "fault" / f"{entry['id']}.html",
            **shared,
            root="../",
            title=f"{entry['id']} {entry['name']}",
            fault=entry,
            rows=_fault_page_rows(configs, str(entry["id"])),
        )

    _render_to(
        env,
        "guards.html.j2",
        dest / "guards.html",
        **shared,
        root="",
        title="Guards",
        deltas=list(board["deltas"]),
    )
    price_rows = sorted(models.values(), key=lambda item: str(item["id"]))
    _render_to(
        env,
        "methodology.html.j2",
        dest / "methodology.html",
        **shared,
        root="",
        title="Methodology",
        catalogue=list(board["catalogue"]),
        models=price_rows,
        seeds=list(board["seeds"]),
        planned_seeds=list(PLANNED_SEEDS),
        run_ids=list(board["run_ids"]),
        source=source,
    )


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_site(
    *,
    out_dir: Path,
    models_path: Path,
    results_path: Path | None = None,
    cassettes_dir: Path | None = None,
    episodes: Sequence[dict[str, Any]] | None = None,
    generated_at: str | None = None,
    bootstrap_b: int = BOOTSTRAP_B,
    archive_max_bytes: int = ARCHIVE_MAX_BYTES,
) -> Path:
    """Write the S16.3 leaderboard tree under ``out_dir / 'leaderboard'``.

    Omit ``results_path`` and ``episodes`` to build the smoke placeholder.
    Returns the ``leaderboard`` directory.
    """
    if bootstrap_b < 0:
        raise ValueError("bootstrap_b must be >= 0")
    models = load_models(models_path)
    placeholder = episodes is None and results_path is None
    if episodes is None:
        rows = placeholder_episodes() if results_path is None else load_results(results_path)
    else:
        rows = list(episodes)
    source = "placeholder" if placeholder else str(results_path or "episodes")
    stamp = generated_at or (PLACEHOLDER_GENERATED_AT if placeholder else _utc_now())
    board = assemble(rows, models, b=bootstrap_b)
    dest = out_dir / "leaderboard"
    _reset_generated(dest)
    (dest / "config").mkdir(parents=True, exist_ok=True)
    (dest / "fault").mkdir(parents=True, exist_ok=True)
    data_dir = dest / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    packed_entries = collect_cassettes(
        rows,
        placeholder=placeholder,
        results_path=results_path,
        cassettes_dir=cassettes_dir,
    )
    pack = pack_archives(packed_entries, data_dir, max_bytes=archive_max_bytes)
    _stamp_archives(board["configs"], pack.location)

    _write_csv(data_dir / "results.csv", rows)
    summary = {
        "schema": "skeptic.leaderboard/v1",
        "generated_at": stamp,
        "placeholder": placeholder,
        "source": source,
        "version": __version__,
        "seeds": board["seeds"],
        "planned_seeds": list(PLANNED_SEEDS),
        "run_ids": board["run_ids"],
        "configs": [_summary_config(row) for row in board["configs"]],
        "guard_deltas": [_summary_delta(row) for row in board["deltas"]],
    }
    _write_text(data_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    _render_pages(
        dest=dest,
        board=board,
        models=models,
        archives=pack.files,
        placeholder=placeholder,
        generated_at=stamp,
        source=source,
    )
    _write_text(out_dir / ".nojekyll", "")
    _write_text(dest / ".nojekyll", "")
    log.info("wrote %s", dest)
    return dest


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry for ``python site/build.py``."""
    parser = argparse.ArgumentParser(description="Build the Skeptic leaderboard static site.")
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="results.jsonl file or a directory containing one. Omit for the smoke placeholder.",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=DEFAULT_MODELS,
        help="path to bench/leaderboard/models.yaml",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="output directory. Pages are written to <out>/leaderboard/.",
    )
    parser.add_argument(
        "--cassettes",
        type=Path,
        default=None,
        help="directory used to resolve cassette paths recorded in results",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_site(
        out_dir=args.out,
        models_path=args.models,
        results_path=args.results,
        cassettes_dir=args.cassettes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
