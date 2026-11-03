"""Integration test for report generation on real run output (E48, E49)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator, Draft202012Validator
from junitparser import JUnitXml
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.runner.matrix import REPORT_SCHEMA_PATH, _get_schema_registry, execute_run
from skeptic_agent.scenario.suites import resolve_suite_scenarios

runner = CliRunner()
SARIF_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sarif-schema-2.1.0.json"


@pytest.mark.asyncio
async def test_report_generation_from_real_run(tmp_path: Path) -> None:
    """Execute a real run with fake LLM and generate all 6 report formats."""
    scenarios = resolve_suite_scenarios("smoke")[:2]
    out_dir = tmp_path / "smoke_run"

    summary = await execute_run(
        scenarios=scenarios,
        agent="reference:fake/oracle_follower",
        profile="silent-core",
        seeds=[1],
        concurrency=2,
        out_dir=out_dir,
        ledger_path=tmp_path / "ledger.csv",
    )

    assert (out_dir / "results.jsonl").is_file()
    assert (out_dir / "summary.json").is_file()
    assert (tmp_path / "ledger.csv").is_file()
    assert summary["schema"] == "skeptic.report/v1"

    # Now generate reports using CLI
    cli_result = runner.invoke(app, ["report", str(out_dir)])
    assert cli_result.exit_code == 0, cli_result.output

    # 1. report.json
    json_path = out_dir / "report.json"
    assert json_path.is_file()
    report_doc = json.loads(json_path.read_text(encoding="utf-8"))
    report_schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    reg = _get_schema_registry()
    Draft202012Validator(report_schema, registry=reg).validate(report_doc)

    # 2. junit.xml
    junit_path = out_dir / "junit.xml"
    assert junit_path.is_file()
    xml = JUnitXml.fromfile(str(junit_path))
    testcase_count = sum(len(list(suite)) for suite in xml)
    assert testcase_count > 0

    # 3. skeptic.sarif
    sarif_path = out_dir / "skeptic.sarif"
    assert sarif_path.is_file()
    sarif_doc = json.loads(sarif_path.read_text(encoding="utf-8"))
    sarif_schema = json.loads(SARIF_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft7Validator(sarif_schema).validate(sarif_doc)

    # 4. badge.svg
    badge_path = out_dir / "badge.svg"
    assert badge_path.is_file()
    badge_svg = badge_path.read_text(encoding="utf-8")
    assert "skeptic" in badge_svg
    assert "SKS" in badge_svg

    # 5. report.md
    md_path = out_dir / "report.md"
    assert md_path.is_file()
    md_content = md_path.read_text(encoding="utf-8")
    assert "# Skeptic 评测报告" in md_content
    assert "指标表" in md_content

    # 6. report.html
    html_path = out_dir / "report.html"
    assert html_path.is_file()
    html_content = html_path.read_text(encoding="utf-8")
    assert "http://" not in html_content
    assert "https://" not in html_content
    assert "Skeptic Reliability Report" in html_content
