#!/usr/bin/env python3
"""Generate L74 paper figures and LaTeX number macros from paper/numbers.json.

Reads only paper/numbers.json. Writes:
  - paper/figures/*.pdf
  - paper/figures/*.png
  - paper/numbers.tex
"""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.patches import Patch

REPO = Path(__file__).resolve().parent
NUMBERS_PATH = REPO / "numbers.json"
FIG_DIR = REPO / "figures"
MACROS_PATH = REPO / "numbers.tex"

# Okabe-Ito-ish, colorblind-friendly
C_NONE = "#0072B2"
C_REC = "#E69F00"
C_SUCCESS = "#009E73"
C_HONEST = "#56B4E9"
C_FALSE = "#D55E00"
C_SILENT = "#CC79A7"
C_INJECTED = "#000000"
C_NOANSWER = "#999999"

OUTCOME_ORDER = [
    "SUCCESS",
    "HONEST_FAILURE",
    "FALSE_SUCCESS",
    "SILENT_CORRUPTION",
    "INJECTED",
    "NO_ANSWER",
]
OUTCOME_LABELS_ZH = {
    "SUCCESS": "SUCCESS",
    "HONEST_FAILURE": "HONEST_FAILURE",
    "FALSE_SUCCESS": "FALSE_SUCCESS",
    "SILENT_CORRUPTION": "SILENT_CORRUPTION",
    "INJECTED": "INJECTED",
    "NO_ANSWER": "NO_ANSWER",
}
OUTCOME_COLORS = {
    "SUCCESS": C_SUCCESS,
    "HONEST_FAILURE": C_HONEST,
    "FALSE_SUCCESS": C_FALSE,
    "SILENT_CORRUPTION": C_SILENT,
    "INJECTED": C_INJECTED,
    "NO_ANSWER": C_NOANSWER,
}

FAULT_ORDER = ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S10"]
FAULT_NAMES = {
    "S01": "empty_ok",
    "S02": "truncated",
    "S03": "stale",
    "S04": "numeric_corruption",
    "S05": "wrong_entity",
    "S06": "redacted",
    "S07": "malformed_ok",
    "S08": "unit_swap",
    "S10": "phantom_write",
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": [
                "Noto Sans CJK SC",
                "Noto Sans",
                "DejaVu Sans",
            ],
            "axes.unicode_minus": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.dpi": 120,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.08,
        }
    )


def load_numbers() -> dict:
    with NUMBERS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def tex_escape(s: object) -> str:
    text = str(s)
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = []
    for ch in text:
        out.append(repl.get(ch, ch))
    return "".join(out)


def fmt_pct_ci(metric: dict) -> str:
    # Raw percent signs; write_macros escapes them for TeX.
    return (
        f"{metric['estimate'] * 100:.2f}% [{metric['low'] * 100:.2f}%, {metric['high'] * 100:.2f}%]"
    )


def write_macros(data: dict) -> None:
    none = data["configs"]["none"]
    rec = data["configs"]["recommended"]
    fmt = data["formatted"]
    rnd = data["rounded"]
    prov = data["provenance"]
    tokens = data["tokens"]
    totals = data["totals"]
    deltas = data["deltas"]["recommended_minus_none"]

    macros: list[tuple[str, str]] = []

    def add(name: str, value: object, escape: bool = True) -> None:
        name = name.replace("_", "")
        text = tex_escape(value) if escape else str(value)
        # formatted metric strings from numbers.json contain raw % characters
        if not escape:
            text = text.replace("%", r"\%")
        macros.append((name, text))

    add("ProvTask", prov["document_labels"]["task"])
    add("ProvTaskReduced", prov["document_labels"]["task_reduced"])
    add("ProvOfficialRef", prov["document_labels"]["official_matrix_reference"])
    add("ProvNote", prov["note"])
    add("ProvDate", prov["experiment_date"])
    add("ProvGitSha", prov["git_sha"])
    add("ProvMatrix", prov["matrix_id"])
    add("ProvModel", prov["model_id"])
    add("ProvProfile", prov["profile"])
    add("ProvSuite", prov["suite"])
    add("ProvSeed", prov["seed"])
    add("ProvScenarios", prov["scenarios"])
    add("ProvHardCap", prov["hard_cap_credits"])
    add("NoneRunId", prov["run_ids"]["none"])
    add("RecRunId", prov["run_ids"]["recommended"])

    add("NoneEpisodes", none["episodes"])
    add("RecEpisodes", rec["episodes"])
    add("TotalEpisodes", totals["episodes"])
    add("NoneErrors", none["errors"])
    add("RecErrors", rec["errors"])
    add("TotalErrors", totals["errors"])

    for cfg_name, cfg, prefix in (
        ("none", none, "None"),
        ("recommended", rec, "Rec"),
    ):
        for metric in ("SKS", "FSR", "SCR", "SafeRate", "DetectRate"):
            add(f"{prefix}{metric}Fmt", fmt["configs"][cfg_name][metric], escape=False)
            add(f"{prefix}{metric}Est", f"{rnd['configs'][cfg_name][metric]['estimate']}")
            add(f"{prefix}{metric}Low", f"{rnd['configs'][cfg_name][metric]['low']}")
            add(f"{prefix}{metric}High", f"{rnd['configs'][cfg_name][metric]['high']}")
        # LoopRate / ICR are in numbers.json but not pre-formatted
        add(f"{prefix}LoopRateFmt", fmt_pct_ci(cfg["metrics"]["LoopRate"]), escape=False)
        add(f"{prefix}ICRFmt", fmt_pct_ci(cfg["metrics"]["ICR"]), escape=False)
        add(f"{prefix}LoopRateEstRaw", f"{cfg['metrics']['LoopRate']['estimate']}")
        add(f"{prefix}ICREstRaw", f"{cfg['metrics']['ICR']['estimate']}")
        sks_partial = "true" if cfg["metrics"]["SKS"].get("partial") else "false"
        add(f"{prefix}SKSPartial", sks_partial)
        add(f"{prefix}CostUsd", f"{cfg['total_cost_usd']}")
        for oc in OUTCOME_ORDER:
            add(f"{prefix}Out{oc}", cfg["outcomes"].get(oc, 0))
        fault_macro = {
            "S01": "Sone",
            "S02": "Stwo",
            "S03": "Sthree",
            "S04": "Sfour",
            "S05": "Sfive",
            "S06": "Ssix",
            "S07": "Sseven",
            "S08": "Seight",
            "S10": "Sten",
        }
        for fault in FAULT_ORDER:
            dist = cfg["by_fault"].get(fault, {})
            total = sum(int(v) for v in dist.values())
            tag = fault_macro[fault]
            add(f"{prefix}Fault{tag}N", total)
            for oc in OUTCOME_ORDER:
                add(f"{prefix}Fault{tag}{oc}", dist.get(oc, 0))

    add("DeltaDetectFmt", fmt["deltas"]["DetectRate"], escape=False)
    add("DeltaFSRFmt", fmt["deltas"]["FSR"], escape=False)
    add("DeltaSCRFmt", fmt["deltas"]["SCR"], escape=False)
    add("DeltaSKSFmt", fmt["deltas"]["SKS"], escape=False)
    add("DeltaSafeFmt", fmt["deltas"]["SafeRate"], escape=False)
    add("DeltaDetectEst", f"{rnd['deltas']['DetectRate']}")
    add("DeltaFSREst", f"{rnd['deltas']['FSR']}")
    add("DeltaSCREst", f"{rnd['deltas']['SCR']}")
    add("DeltaSKSEst", f"{rnd['deltas']['SKS']}")
    add("DeltaSafeEst", f"{rnd['deltas']['SafeRate']}")
    # raw (proportion) deltas also available
    add("DeltaDetectRaw", f"{deltas['DetectRate']}")
    add("DeltaFSRRaw", f"{deltas['FSR']}")
    add("DeltaSCRRaw", f"{deltas['SCR']}")
    add("DeltaSKSRaw", f"{deltas['SKS']}")
    add("DeltaSafeRaw", f"{deltas['SafeRate']}")

    none_tok = tokens["by_run"][prov["run_ids"]["none"]]
    rec_tok = tokens["by_run"][prov["run_ids"]["recommended"]]
    tot = tokens["total"]
    add("NoneTokIn", none_tok["tokens_in"])
    add("NoneTokOut", none_tok["tokens_out"])
    add("NoneTokTotal", none_tok["tokens_total"])
    add("RecTokIn", rec_tok["tokens_in"])
    add("RecTokOut", rec_tok["tokens_out"])
    add("RecTokTotal", rec_tok["tokens_total"])
    add("TotalTokIn", tot["tokens_in"])
    add("TotalTokOut", tot["tokens_out"])
    add("TotalTokTotal", tot["tokens_total"])
    add("NoneCreditsFmt", fmt["credits"]["none"])
    add("RecCreditsFmt", fmt["credits"]["recommended"])
    add("TotalCreditsFmt", fmt["credits"]["total"])
    add("NoneCredits", f"{rnd['credits']['none']}")
    add("RecCredits", f"{rnd['credits']['recommended']}")
    add("TotalCredits", f"{rnd['credits']['total']}")
    add("RateIn", tokens["credit_rates_per_mtok"]["off_peak_in"])
    add("RateOut", tokens["credit_rates_per_mtok"]["off_peak_out"])
    add("CreditFormula", tokens["credit_rates_per_mtok"]["formula"])
    add("CreditNotes", tokens["credit_rates_per_mtok"]["notes"])
    add("CostUsdNote", tokens["cost_usd_note"])
    add("TotalCostUsd", f"{tot['cost_usd']}")

    # Guard action maps are empty in this numbers.json
    none_ga = none.get("guard_actions") or {}
    rec_ga = rec.get("guard_actions") or {}
    add("NoneGuardActionKeys", len(none_ga))
    add("RecGuardActionKeys", len(rec_ga))

    lines = [
        "% Auto-generated by paper/make_figures.py from paper/numbers.json.",
        "% Do not edit by hand.",
        r"\makeatletter",
    ]
    for name, value in macros:
        lines.append(rf"\newcommand{{\Lxx{name}}}{{{value}}}")
    lines.append(r"\makeatother")
    lines.append("")
    MACROS_PATH.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def savefig(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.pdf")
    fig.savefig(FIG_DIR / f"{stem}.png")
    plt.close(fig)


def fig_metrics(data: dict) -> None:
    rnd = data["rounded"]["configs"]

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.6), gridspec_kw={"width_ratios": [1, 2.2]})

    # Panel A: SKS (0-100)
    ax = axes[0]
    xs = np.array([0, 1])
    est = [rnd["none"]["SKS"]["estimate"], rnd["recommended"]["SKS"]["estimate"]]
    lo = [rnd["none"]["SKS"]["low"], rnd["recommended"]["SKS"]["low"]]
    hi = [rnd["none"]["SKS"]["high"], rnd["recommended"]["SKS"]["high"]]
    yerr = np.array([[est[i] - lo[i], hi[i] - est[i]] for i in range(2)]).T
    ax.bar(xs, est, color=[C_NONE, C_REC], width=0.62, zorder=2)
    ax.errorbar(xs, est, yerr=yerr, fmt="none", ecolor="black", capsize=4, lw=1.1, zorder=3)
    ax.set_xticks(xs, ["none", "recommended"])
    ax.set_ylabel("SKS（0–100，partial）")
    ax.set_ylim(90, 100)
    ax.set_title("(a) Skeptic Score")
    ax.axhline(100, color="#dddddd", lw=0.8, zorder=1)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))
    for x, v in zip(xs, est, strict=True):
        ax.text(x, v + 0.35, f"{v:.2f}", ha="center", va="bottom", fontsize=8)

    # Panel B: rates in percent
    ax = axes[1]
    metric_keys = ["SafeRate", "FSR", "SCR", "DetectRate"]
    metric_labels = ["SafeRate", "FSR", "SCR", "DetectRate"]
    x = np.arange(len(metric_keys))
    width = 0.36
    none_est = [rnd["none"][k]["estimate"] for k in metric_keys]
    rec_est = [rnd["recommended"][k]["estimate"] for k in metric_keys]
    none_err = np.array(
        [
            [
                rnd["none"][k]["estimate"] - rnd["none"][k]["low"],
                rnd["none"][k]["high"] - rnd["none"][k]["estimate"],
            ]
            for k in metric_keys
        ]
    ).T
    rec_err = np.array(
        [
            [
                rnd["recommended"][k]["estimate"] - rnd["recommended"][k]["low"],
                rnd["recommended"][k]["high"] - rnd["recommended"][k]["estimate"],
            ]
            for k in metric_keys
        ]
    ).T
    ax.bar(x - width / 2, none_est, width, color=C_NONE, label="none", zorder=2)
    ax.bar(x + width / 2, rec_est, width, color=C_REC, label="recommended", zorder=2)
    ax.errorbar(
        x - width / 2,
        none_est,
        yerr=none_err,
        fmt="none",
        ecolor="black",
        capsize=3,
        lw=1,
        zorder=3,
    )
    ax.errorbar(
        x + width / 2,
        rec_est,
        yerr=rec_err,
        fmt="none",
        ecolor="black",
        capsize=3,
        lw=1,
        zorder=3,
    )
    ax.set_xticks(x, metric_labels)
    ax.set_ylabel("百分比（%）")
    ax.set_ylim(0, 110)
    ax.set_title("(b) 主要比率指标（95% 置信区间）")
    ax.legend(frameon=False, loc="upper right")

    fig.suptitle(
        "缩减范围实验：none vs recommended（误差线为场景整群 Bootstrap 95% CI）",
        fontsize=11,
        y=1.02,
    )
    fig.tight_layout()
    savefig(fig, "fig_metrics_ci")


def fig_outcomes(data: dict) -> None:
    none = data["configs"]["none"]["outcomes"]
    rec = data["configs"]["recommended"]["outcomes"]
    labels = OUTCOME_ORDER
    none_v = [none.get(k, 0) for k in labels]
    rec_v = [rec.get(k, 0) for k in labels]
    x = np.arange(len(labels))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8.6, 3.6))
    ax.bar(x - width / 2, none_v, width, color=C_NONE, label="none")
    ax.bar(x + width / 2, rec_v, width, color=C_REC, label="recommended")
    ax.set_xticks(x, labels, rotation=18, ha="right")
    ax.set_ylabel("episode 数")
    ax.set_title("结局计数对照（各配置 446 条 episode）")
    ax.legend(frameon=False)
    ymax = max(none_v + rec_v)
    ax.set_ylim(0, ymax * 1.15 if ymax else 1)
    for dx, vals in ((-width / 2, none_v), (width / 2, rec_v)):
        for i, v in enumerate(vals):
            if v:
                ax.text(x[i] + dx, v + ymax * 0.02, str(v), ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    savefig(fig, "fig_outcomes")


def fig_by_fault(data: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.4), sharey=True)
    for ax, cfg_key, title in (
        (axes[0], "none", "none"),
        (axes[1], "recommended", "recommended"),
    ):
        by_fault = data["configs"][cfg_key]["by_fault"]
        bottoms = np.zeros(len(FAULT_ORDER))
        y = np.arange(len(FAULT_ORDER))
        for oc in OUTCOME_ORDER:
            vals = np.array([by_fault.get(f, {}).get(oc, 0) for f in FAULT_ORDER], dtype=float)
            if vals.sum() == 0:
                continue
            ax.barh(y, vals, left=bottoms, color=OUTCOME_COLORS[oc], height=0.72, label=oc)
            bottoms += vals
        ax.set_yticks(y, [f"{f}\n{FAULT_NAMES[f]}" for f in FAULT_ORDER])
        ax.set_xlabel("episode 数")
        ax.set_title(title)
        ax.set_xlim(0, 60)
        # annotate totals
        for i, f in enumerate(FAULT_ORDER):
            total = sum(by_fault.get(f, {}).values())
            ax.text(total + 0.6, i, str(total), va="center", fontsize=8, color="#333333")
    handles = [Patch(facecolor=OUTCOME_COLORS[oc], label=oc) for oc in OUTCOME_ORDER]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle("按故障代码的结局分布（右侧数字为该故障 episode 合计）", fontsize=11)
    fig.tight_layout(rect=(0, 0.10, 1, 0.96))
    savefig(fig, "fig_by_fault")


def main() -> None:
    setup_style()
    data = load_numbers()
    write_macros(data)
    fig_metrics(data)
    fig_outcomes(data)
    fig_by_fault(data)
    print(f"Wrote macros {MACROS_PATH}")
    for p in sorted(FIG_DIR.glob("fig_*")):
        print(f"  {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
