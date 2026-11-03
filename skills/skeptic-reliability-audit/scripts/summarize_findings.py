#!/usr/bin/env python3
"""Skeptic Reliability Audit - Step 6: Report (S14.1, S14.2).

Aggregates execution and verification runs, produces audit/findings.json
(validating against schemas/findings.schema.json), audit/skeptic.sarif,
and audit/summary.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skeptic_agent.audit.findings import summarize_findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize audit runs into findings.json, skeptic.sarif, and summary.md."
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("audit/runs/baseline"),
        help="Path to initial run directory (default: audit/runs/baseline).",
    )
    parser.add_argument(
        "--verify",
        type=Path,
        default=None,
        help="Path to verification run directory (e.g. audit/runs/verify).",
    )
    parser.add_argument(
        "--hardened",
        type=Path,
        default=None,
        help="Path to hardened run directory (e.g. audit/runs/hardened).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("audit"),
        help="Directory to output findings.json, skeptic.sarif, and summary.md (default: audit).",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Directory containing findings templates (default: skills templates).",
    )
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Project name for audit reporting.",
    )

    args = parser.parse_args()

    if not args.runs.is_dir():
        # Check if audit/runs exists and has runs
        candidates = list(Path("audit/runs").glob("*")) if Path("audit/runs").is_dir() else []
        if candidates and not args.runs.exists():
            args.runs = candidates[0]
        else:
            sys.stderr.write(
                f"Error: run directory not found: {args.runs}\n"
                "Run Step 3 (skeptic run ...) first.\n"
            )
            return 2

    # Auto-detect verify and hardened directories if not explicitly passed
    verify_dir = args.verify
    if verify_dir is None:
        auto_verify = args.runs.parent / "verify"
        if auto_verify.is_dir():
            verify_dir = auto_verify

    hardened_dir = args.hardened
    if hardened_dir is None:
        auto_hardened = args.runs.parent / "hardened"
        if auto_hardened.is_dir():
            hardened_dir = auto_hardened

    print(f"[Skeptic Skill] Summarizing findings from {args.runs}...")
    try:
        outputs = summarize_findings(
            run_dir=args.runs,
            verify_dir=verify_dir,
            hardened_dir=hardened_dir,
            out_dir=args.out,
            templates_dir=args.templates,
            project_name=args.project,
        )
        print(f"[Skeptic Skill] Generated findings -> {outputs['findings']}")
        print(f"[Skeptic Skill] Generated SARIF report -> {outputs['sarif']}")
        print(f"[Skeptic Skill] Generated summary markdown -> {outputs['summary']}")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error summarizing findings: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
