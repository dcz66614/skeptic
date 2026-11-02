"""Markdown report generator (S12, E49): report.md."""

from __future__ import annotations

from pathlib import Path

from skeptic_agent.faults.catalog import CATALOGUE, CatalogueEntry
from skeptic_agent.report.loader import RunData
from skeptic_agent.runner.matrix import gate_check

# Metadata map for metrics descriptions
METRIC_DESCRIPTIONS: dict[str, str] = {
    "SKS": "综合韧性评分 (Skeptic Score, 0-100)",
    "TSR_clean": "无故障基线成功率 (Tool Success Rate - Clean)",
    "TSR_rec": "可恢复故障成功率 (Tool Success Rate - Recoverable)",
    "RR": "韧性比 (Resilience Ratio = TSR_rec / TSR_clean)",
    "SafeRate": "安全结局率 (Safe Rate = SUCCESS + HONEST_FAILURE)",
    "FSR": "谎报成功率 (False Success Rate)",
    "SCR": "静默污染率 (Silent Corruption Rate)",
    "ICR": "注入服从率 (Injection Compliance Rate)",
    "LoopRate": "死循环率 (Loop Rate)",
    "DetectRate": "问题察觉率 (Problem Detection Rate)",
    "UntriggeredRate": "故障未触发率 (Untriggered Rate)",
    "Cost": "平均单次费用 (Average Cost, USD)",
    "Latency": "平均单次延迟 (Average Latency, seconds)",
}

CATALOGUE_BY_ID: dict[str, CatalogueEntry] = {entry["id"]: entry for entry in CATALOGUE}


def generate_md_report(run_data: RunData, out_path: Path) -> Path:
    """Generate Markdown report meeting S12 requirements.

    Args:
        run_data: Loaded run data.
        out_path: File path to write report.md to.

    Returns:
        The written Path.
    """
    summary = run_data.summary
    run_id = run_data.run_id
    time_iso = summary.get("time", "")
    version = summary.get("version", "")
    git_sha = summary.get("git_sha", "")
    command = summary.get("command", "")
    total_cost = summary.get("total_cost_usd", 0.0)

    # Agent metrics
    ag0 = summary.get("agents", [{}])[0]
    metrics = ag0.get("metrics", {})
    sks_obj = metrics.get("SKS", {})
    sks_est = float(sks_obj.get("estimate", 0.0))
    sks_low = float(sks_obj.get("low", 0.0))
    sks_high = float(sks_obj.get("high", 0.0))
    is_partial = bool(sks_obj.get("partial", False))

    # Gate check
    passed_gate, gate_msg = gate_check(run_data.run_dir)
    gate_badge = "✅ PASSED" if passed_gate else "❌ FAILED"

    lines: list[str] = [
        f"# Skeptic 评测报告 (Run: `{run_id}`)",
        "",
        "## 1. 运行概要",
        "",
        f"- **运行编号 (Run ID)**: `{run_id}`",
        f"- **完成时间 (Time UTC)**: `{time_iso}`",
        f"- **版本 (Version)**: `v{version}` (`{git_sha}`)",
        f"- **执行命令 (Command)**: `{command}`" if command else "- **执行命令 (Command)**: *N/A*",
        f"- **总开销 (Total Cost)**: `${total_cost:.4f}`",
        "",
        "## 2. 核心评分与门禁 (SKS & Gate)",
        "",
        f"### SKS: **{sks_est:.1f}** [{sks_low:.1f}, {sks_high:.1f}]"
        + (" *(partial SKS)*" if is_partial else ""),
        "",
        f"### 门禁状态: {gate_badge}",
        "",
        f"> {gate_msg}",
        "",
        "## 3. 指标表 (Metrics Table)",
        "",
        "| 指标 | 点估计 | 95% 置信区间 | 说明 |",
        "|---|---|---|---|",
    ]

    metric_order = [
        "SKS",
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

    for mkey in metric_order:
        m_obj = metrics.get(mkey)
        if not m_obj or not isinstance(m_obj, dict):
            continue
        est = float(m_obj.get("estimate", 0.0))
        low = float(m_obj.get("low", 0.0))
        high = float(m_obj.get("high", 0.0))
        desc = METRIC_DESCRIPTIONS.get(mkey, mkey)

        if mkey == "SKS":
            est_str = f"{est:.1f}"
            ci_str = f"[{low:.1f}, {high:.1f}]"
        elif mkey in ("Cost", "Latency"):
            est_str = f"${est:.4f}" if mkey == "Cost" else f"{est:.2f}s"
            if mkey == "Cost":
                ci_str = f"[${low:.4f}, ${high:.4f}]"
            else:
                ci_str = f"[{low:.2f}s, {high:.2f}s]"
        else:
            est_str = f"{est:.1%}"
            ci_str = f"[{low:.1%}, {high:.1%}]"

        lines.append(f"| `{mkey}` | **{est_str}** | {ci_str} | {desc} |")

    table_header = (
        "| 故障 ID | 名称 | 类别 | 总数 | SUCCESS | "
        "SILENT_CORRUPTION | HONEST_FAILURE | FALSE_SUCCESS | INJECTED | 其他 (ERROR/NA) |"
    )
    lines.extend(
        [
            "",
            "## 4. 按故障分组的结局表 (Outcomes by Fault)",
            "",
            table_header,
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )

    by_fault: dict[str, dict[str, int]] = summary.get("by_fault", {})
    all_fids = sorted(by_fault.keys())
    if not all_fids:
        lines.append("| *无* | - | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 |")
    else:
        for fid in all_fids:
            counts = by_fault[fid]
            cat_entry = CATALOGUE_BY_ID.get(fid)
            fname = str(cat_entry["name"]) if cat_entry else fid
            fclass = str(cat_entry["fault_class"]) if cat_entry else "-"

            n_succ = counts.get("SUCCESS", 0)
            n_sc = counts.get("SILENT_CORRUPTION", 0)
            n_hf = counts.get("HONEST_FAILURE", 0)
            n_fs = counts.get("FALSE_SUCCESS", 0)
            n_inj = counts.get("INJECTED", 0)

            excluded = {
                "SUCCESS",
                "SILENT_CORRUPTION",
                "HONEST_FAILURE",
                "FALSE_SUCCESS",
                "INJECTED",
            }
            n_other = sum(cnt for k, cnt in counts.items() if k not in excluded)
            total = sum(counts.values())

            row_str = (
                f"| `{fid}` | {fname} | {fclass} | {total} | {n_succ} | "
                f"{n_sc} | {n_hf} | {n_fs} | {n_inj} | {n_other} |"
            )
            lines.append(row_str)

    lines.extend(
        [
            "",
            "## 5. 最差 10 个场景 (Worst 10 Scenarios)",
            "",
            "| 序号 | 场景 ID | SafeRate | Cassettes |",
            "|---|---|---|---|",
        ]
    )

    worst_scens = summary.get("worst_scenarios", [])[:10]
    if not worst_scens:
        lines.append("| - | *无场景记录* | - | - |")
    else:
        for idx, sc_item in enumerate(worst_scens, start=1):
            sc_id = sc_item.get("scenario_id", "")
            safe_rate = float(sc_item.get("SafeRate", 0.0))
            cassettes_list = sc_item.get("cassettes", [])
            cassettes_str = ", ".join(f"`{c}`" for c in cassettes_list) if cassettes_list else "-"
            lines.append(f"| {idx} | `{sc_id}` | **{safe_rate:.1%}** | {cassettes_str} |")

    lines.extend(
        [
            "",
            "## 6. 复现命令 (Reproduction Commands)",
            "",
            "```bash",
            "# 重新运行完整套件:",
            command or f"skeptic run --suite smoke --out runs/{run_id}",
        ]
    )

    if worst_scens and worst_scens[0].get("cassettes"):
        worst_c = worst_scens[0]["cassettes"][0]
        lines.extend(
            [
                "",
                "# 重放最差场景 cassette:",
                f"skeptic replay --cassette {worst_c}",
            ]
        )

    lines.extend(["```", ""])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
