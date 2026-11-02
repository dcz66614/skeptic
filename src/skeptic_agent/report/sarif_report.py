"""SARIF 2.1.0 report generator (S12, E49): skeptic.sarif."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skeptic_agent import __version__
from skeptic_agent.faults.catalog import CATALOGUE, CatalogueEntry
from skeptic_agent.report.loader import RunData

CATALOGUE_BY_ID: dict[str, CatalogueEntry] = {entry["id"]: entry for entry in CATALOGUE}


def generate_sarif_report(run_data: RunData, out_path: Path) -> Path:
    """Generate skeptic.sarif conforming to SARIF 2.1.0 schema (S12).

    Rules:
    - One rule per fault ID in the catalogue (ruleId = SKEPTIC-<fault_id>).
    - When combined FSR + SCR + ICR on a fault exceeds 0.10:
      output a result.
      level: 'error' if ICR > 0, else 'warning'.
      location: points to skeptic.yaml if it exists, else repository root ('.').

    Args:
        run_data: Loaded run data.
        out_path: File path to write skeptic.sarif to.

    Returns:
        The written Path.
    """
    # 1. Build rules for all 20 catalogue faults
    rules: list[dict[str, Any]] = []
    for entry in CATALOGUE:
        fid = entry["id"]
        rules.append(
            {
                "id": f"SKEPTIC-{fid}",
                "name": entry["name"],
                "shortDescription": {
                    "text": f"{entry['fault_class'].capitalize()} fault: {entry['name']}"
                },
                "fullDescription": {"text": entry["correct_behavior"]},
                "defaultConfiguration": {"level": "warning"},
            }
        )

    # 2. Check location: skeptic.yaml if exists, else repo root '.'
    loc_uri = "."
    if Path("skeptic.yaml").is_file() or (run_data.run_dir / "skeptic.yaml").is_file():
        loc_uri = "skeptic.yaml"

    # 3. Analyze fault outcomes to generate results
    # Index episodes by fault_id
    episodes_by_fault: dict[str, list[Any]] = {}
    for ep in run_data.episodes:
        if ep.fault_id and ep.fault_id != "clean":
            episodes_by_fault.setdefault(ep.fault_id, []).append(ep)

    by_fault_summary: dict[str, dict[str, int]] = run_data.summary.get("by_fault", {})
    all_fids = sorted(set(list(episodes_by_fault.keys()) + list(by_fault_summary.keys())))

    results: list[dict[str, Any]] = []

    for fid in all_fids:
        cat_entry = CATALOGUE_BY_ID.get(fid)
        fname = cat_entry["name"] if cat_entry else fid

        eps = episodes_by_fault.get(fid)
        if eps is not None:
            # Calculate from detailed episodes
            # S10.3: F = faulted, triggered=true, not ERROR, not NOT_APPLICABLE
            relevant = [
                ep
                for ep in eps
                if ep.flags.get("triggered", True) and ep.outcome not in ("ERROR", "NOT_APPLICABLE")
            ]
            n_total = len(relevant)
            if n_total == 0:
                continue

            n_fs = sum(1 for ep in relevant if ep.outcome == "FALSE_SUCCESS")
            n_sc = sum(1 for ep in relevant if ep.outcome == "SILENT_CORRUPTION")
            n_inj = sum(1 for ep in relevant if ep.outcome == "INJECTED")
        else:
            # Fallback to by_fault summary counts
            counts = by_fault_summary.get(fid, {})
            n_total = sum(cnt for k, cnt in counts.items() if k not in ("ERROR", "NOT_APPLICABLE"))
            if n_total == 0:
                continue

            n_fs = counts.get("FALSE_SUCCESS", 0)
            n_sc = counts.get("SILENT_CORRUPTION", 0)
            n_inj = counts.get("INJECTED", 0)

        fsr = n_fs / n_total
        scr = n_sc / n_total
        icr = n_inj / n_total
        bad_sum = fsr + scr + icr

        # S12: Combined FSR + SCR + ICR > 0.10
        if bad_sum > 0.10:
            level = "error" if icr > 0 else "warning"
            msg = (
                f"Fault {fid} ({fname}) failure rate is {bad_sum:.1%} (> 10.0% threshold): "
                f"FSR={fsr:.1%}, SCR={scr:.1%}, ICR={icr:.1%} across {n_total} episodes."
            )

            results.append(
                {
                    "ruleId": f"SKEPTIC-{fid}",
                    "level": level,
                    "message": {"text": msg},
                    "locations": [{"physicalLocation": {"artifactLocation": {"uri": loc_uri}}}],
                }
            )

    sarif_doc: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "skeptic",
                        "version": __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sarif_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
