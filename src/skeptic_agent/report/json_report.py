"""JSON report generator (S12, E49): report.json (skeptic.report/v1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skeptic_agent.report.loader import RunData
from skeptic_agent.runner.matrix import validate_summary_doc


def generate_json_report(run_data: RunData, out_path: Path) -> Path:
    """Generate report.json conforming to skeptic.report/v1 with episode briefs.

    Args:
        run_data: Loaded run data.
        out_path: File path to write report.json to.

    Returns:
        The written Path.
    """
    doc: dict[str, Any] = dict(run_data.summary)

    # Ensure episodes brief list is present
    if "episodes" not in doc or not doc["episodes"]:
        ep_briefs: list[dict[str, Any]] = []
        for ep in run_data.episodes:
            ep_briefs.append(
                {
                    "episode_id": ep.episode_id,
                    "scenario_id": ep.scenario_id,
                    "sandbox": ep.sandbox,
                    "seed": ep.seed,
                    "outcome": ep.outcome,
                    "fault_id": ep.fault_id,
                    "cassette": ep.cassette_path,
                }
            )
        doc["episodes"] = ep_briefs

    # Validate against schemas/report.schema.json
    validate_summary_doc(doc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
