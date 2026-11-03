#!/usr/bin/env python3
"""Skeptic Reliability Audit - Step 2: Plan (S14.1, S14.2).

Generates skeptic scenario drafts (2 per read tool, 1 per write tool)
based on audit/discovery.json, creates audit/profile.yaml, and validates scenarios.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skeptic_agent.audit.scenarios import generate_scenarios


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate skeptic scenarios and fixed audit profile from discovery data."
    )
    parser.add_argument(
        "--discovery",
        type=Path,
        default=Path("audit/discovery.json"),
        help="Path to discovery JSON file (default: audit/discovery.json).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("audit/scenarios"),
        help="Directory to write generated scenarios (default: audit/scenarios).",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        help="Directory containing scenario templates (default: skills templates).",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=None,
        help="Path to output combined audit profile (default: audit/profile.yaml).",
    )

    args = parser.parse_args()

    if not args.discovery.is_file():
        sys.stderr.write(
            f"Error: discovery file not found: {args.discovery}\n"
            "Run Step 1 (scripts/discover.sh or scripts/discover.ps1) first.\n"
        )
        return 2

    try:
        discovery_data = json.loads(args.discovery.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error parsing {args.discovery}: {exc}\n")
        return 2

    profile_target = args.profile or (args.out.parent / "profile.yaml")

    print(f"[Skeptic Skill] Generating scenarios from {args.discovery}...")
    try:
        scenarios = generate_scenarios(
            discovery_data=discovery_data,
            out_dir=args.out,
            templates_dir=args.templates,
            profile_out=profile_target,
        )
        print(
            f"[Skeptic Skill] Successfully generated and validated {len(scenarios)} "
            f"scenario(s) in {args.out}"
        )
        print(f"[Skeptic Skill] Generated audit profile -> {profile_target}")
        return 0
    except Exception as exc:
        sys.stderr.write(f"Error generating scenarios: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
