"""HTML report generator (S12, E49): report.html."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from skeptic_agent.faults.catalog import CATALOGUE, CatalogueEntry
from skeptic_agent.report.loader import RunData
from skeptic_agent.report.md_report import METRIC_DESCRIPTIONS
from skeptic_agent.runner.matrix import gate_check

TEMPLATES_DIR = Path(__file__).parent / "templates"
CATALOGUE_BY_ID: dict[str, CatalogueEntry] = {entry["id"]: entry for entry in CATALOGUE}


def generate_html_report(run_data: RunData, out_path: Path) -> Path:
    """Render single-file report.html conforming to S12.

    Rules from S12 & Acceptance:
    - Single file, CSS and JS all inlined, no CDN.
    - Supports light and dark mode.
    - Top summary cards: SKS big number, Gate verification, metrics grid.
    - Fault x Outcome heatmap table.
    - Client-side scenario list filterable by outcome, fault, sandbox using pure JS.
    - Expandable episode details with conversation history and side-by-side
      tools/call raw vs final comparison highlighting faults and guards.
    - Zero http:// or https:// external resource references.

    Args:
        run_data: Loaded run data.
        out_path: File path to write report.html to.

    Returns:
        The written Path.
    """
    summary = run_data.summary
    run_id = run_data.run_id
    version = str(summary.get("version", "0.1.0"))
    git_sha = str(summary.get("git_sha", ""))
    time_iso = str(summary.get("time", ""))
    total_cost = float(summary.get("total_cost_usd", 0.0))

    ag0 = summary.get("agents", [{}])[0]
    adapter = ag0.get("adapter", "reference")
    model = ag0.get("model", "unknown")
    agent_spec = f"{adapter}:{model}"
    prompt_variant = ag0.get("prompt_variant", "plain")
    guards_raw = ag0.get("guards", [])
    if isinstance(guards_raw, list):
        guards_summary = ", ".join(guards_raw) if guards_raw else "none"
    else:
        guards_summary = str(guards_raw)

    metrics = ag0.get("metrics", {})
    sks_obj = metrics.get("SKS", {})
    sks_est = float(sks_obj.get("estimate", 0.0))
    sks_low = float(sks_obj.get("low", 0.0))
    sks_high = float(sks_obj.get("high", 0.0))
    is_partial = bool(sks_obj.get("partial", False))

    passed_gate, gate_msg = gate_check(run_data.run_dir)

    # Prepare metrics list
    metric_keys = [
        "TSR_clean",
        "TSR_rec",
        "RR",
        "SafeRate",
        "FSR",
        "SCR",
        "ICR",
        "LoopRate",
        "DetectRate",
        "UntriggeredRate",
        "Cost",
        "Latency",
    ]
    metrics_list: list[dict[str, str]] = []
    for mkey in metric_keys:
        m_obj = metrics.get(mkey)
        if not m_obj or not isinstance(m_obj, dict):
            continue
        est = float(m_obj.get("estimate", 0.0))
        low = float(m_obj.get("low", 0.0))
        high = float(m_obj.get("high", 0.0))
        name = METRIC_DESCRIPTIONS.get(mkey, mkey).split("(")[0].strip()

        if mkey in ("Cost", "Latency"):
            est_str = f"${est:.4f}" if mkey == "Cost" else f"{est:.2f}s"
            if mkey == "Cost":
                ci_str = f"[${low:.4f}, ${high:.4f}]"
            else:
                ci_str = f"[{low:.2f}s, {high:.2f}s]"
        else:
            est_str = f"{est:.1%}"
            ci_str = f"[{low:.1%}, {high:.1%}]"

        metrics_list.append(
            {
                "key": mkey,
                "name": name,
                "est_str": est_str,
                "ci_str": ci_str,
            }
        )

    # Prepare heatmap rows
    by_fault: dict[str, dict[str, int]] = summary.get("by_fault", {})
    all_fids = sorted(by_fault.keys())
    heatmap_rows: list[dict[str, Any]] = []
    for fid in all_fids:
        counts = by_fault[fid]
        cat_entry = CATALOGUE_BY_ID.get(fid)
        fname = str(cat_entry["name"]) if cat_entry else fid
        fclass = str(cat_entry["fault_class"]) if cat_entry else "-"

        excluded = {"SUCCESS", "SILENT_CORRUPTION", "HONEST_FAILURE", "FALSE_SUCCESS", "INJECTED"}
        n_other = sum(cnt for k, cnt in counts.items() if k not in excluded)

        heatmap_rows.append(
            {
                "id": fid,
                "name": fname,
                "fault_class": fclass,
                "SUCCESS": counts.get("SUCCESS", 0),
                "SILENT_CORRUPTION": counts.get("SILENT_CORRUPTION", 0),
                "HONEST_FAILURE": counts.get("HONEST_FAILURE", 0),
                "FALSE_SUCCESS": counts.get("FALSE_SUCCESS", 0),
                "INJECTED": counts.get("INJECTED", 0),
                "OTHER": n_other,
            }
        )

    unique_faults = sorted(
        {ep.fault_id for ep in run_data.episodes if ep.fault_id and ep.fault_id != "clean"}
    )
    unique_sandboxes = sorted({ep.sandbox for ep in run_data.episodes if ep.sandbox})

    # Render Jinja2 template
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )
    template = env.get_template("report.html.j2")

    html_content = template.render(
        run_id=run_id,
        version=version,
        git_sha=git_sha,
        time=time_iso,
        total_cost=total_cost,
        agent_spec=agent_spec,
        prompt_variant=prompt_variant,
        guards_summary=guards_summary,
        sks=sks_est,
        sks_ci=(sks_low, sks_high),
        is_partial=is_partial,
        gate_passed=passed_gate,
        gate_msg=gate_msg,
        metrics_list=metrics_list,
        heatmap_rows=heatmap_rows,
        unique_faults=unique_faults,
        unique_sandboxes=unique_sandboxes,
        episodes=run_data.episodes,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")
    return out_path
