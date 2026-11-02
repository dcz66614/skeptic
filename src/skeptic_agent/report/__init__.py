"""Report generation package for Skeptic (S12, E49)."""

from __future__ import annotations

from skeptic_agent.report.badge_report import generate_badge_report
from skeptic_agent.report.engine import VALID_FORMATS, generate_reports, parse_formats
from skeptic_agent.report.html_report import generate_html_report
from skeptic_agent.report.json_report import generate_json_report
from skeptic_agent.report.junit_report import generate_junit_report, is_correct_outcome
from skeptic_agent.report.loader import (
    EpisodeReportDetail,
    RunData,
    ToolCallDiff,
    load_run_data,
    parse_cassette_file,
)
from skeptic_agent.report.md_report import generate_md_report
from skeptic_agent.report.sarif_report import generate_sarif_report

__all__ = [
    "VALID_FORMATS",
    "EpisodeReportDetail",
    "RunData",
    "ToolCallDiff",
    "generate_badge_report",
    "generate_html_report",
    "generate_json_report",
    "generate_junit_report",
    "generate_md_report",
    "generate_reports",
    "generate_sarif_report",
    "is_correct_outcome",
    "load_run_data",
    "parse_cassette_file",
    "parse_formats",
]
