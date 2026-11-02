"""Report generation orchestrator (S12, E49)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from skeptic_agent.report.badge_report import generate_badge_report
from skeptic_agent.report.html_report import generate_html_report
from skeptic_agent.report.json_report import generate_json_report
from skeptic_agent.report.junit_report import generate_junit_report
from skeptic_agent.report.loader import load_run_data
from skeptic_agent.report.md_report import generate_md_report
from skeptic_agent.report.sarif_report import generate_sarif_report

VALID_FORMATS = ("html", "md", "json", "junit", "sarif", "badge")


def parse_formats(format_spec: str | Sequence[str]) -> list[str]:
    """Parse format string or list into validated format names.

    Args:
        format_spec: Comma-separated string (e.g. 'html,md' or 'all') or list.

    Returns:
        List of unique valid format strings.

    Raises:
        ValueError: If any requested format is invalid.
    """
    if isinstance(format_spec, str):
        parts = [p.strip().lower() for p in format_spec.split(",") if p.strip()]
    else:
        parts = [str(p).strip().lower() for p in format_spec if str(p).strip()]

    if not parts or "all" in parts:
        return list(VALID_FORMATS)

    resolved: list[str] = []
    for p in parts:
        if p not in VALID_FORMATS:
            raise ValueError(
                f"Invalid report format: {p!r}. Valid options: {', '.join(VALID_FORMATS)} or 'all'."
            )
        if p not in resolved:
            resolved.append(p)

    return resolved


def generate_reports(
    run_dir: str | Path,
    *,
    out_dir: str | Path | None = None,
    formats: str | Sequence[str] = "all",
) -> dict[str, Path]:
    """Generate the requested evaluation reports for a run directory (S12).

    Args:
        run_dir: Path to directory containing results.jsonl and/or summary.json.
        out_dir: Directory where reports will be written (defaults to run_dir).
        formats: Target format(s), e.g. 'html,md,json,junit,sarif,badge' or 'all'.

    Returns:
        Dictionary mapping format name to output Path.
    """
    run_path = Path(run_dir)
    target_dir = (
        Path(out_dir)
        if out_dir is not None
        else (run_path.parent if run_path.is_file() else run_path)
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    format_list = parse_formats(formats)
    run_data = load_run_data(run_path)

    outputs: dict[str, Path] = {}

    if "json" in format_list:
        outputs["json"] = generate_json_report(run_data, target_dir / "report.json")

    if "md" in format_list:
        outputs["md"] = generate_md_report(run_data, target_dir / "report.md")

    if "html" in format_list:
        outputs["html"] = generate_html_report(run_data, target_dir / "report.html")

    if "junit" in format_list:
        outputs["junit"] = generate_junit_report(run_data, target_dir / "junit.xml")

    if "sarif" in format_list:
        outputs["sarif"] = generate_sarif_report(run_data, target_dir / "skeptic.sarif")

    if "badge" in format_list:
        outputs["badge"] = generate_badge_report(run_data, target_dir / "badge.svg")

    return outputs
