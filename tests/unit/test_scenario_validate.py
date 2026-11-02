"""Unit tests for scenario validator and S8.4 semantic rules (S8, S36)."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.scenario.model import load_scenario
from skeptic_agent.scenario.validate import (
    extract_numbers,
    validate_paths,
    validate_scenario_data,
)

pytestmark = pytest.mark.unit

WEATHER_FIXTURE = Path("tests/fixtures/scenarios/weather.forecast.max-temp.001.yaml")


@pytest.fixture
def base_scenario_dict() -> dict[str, Any]:
    """Return a pristine valid scenario mapping."""
    return load_scenario(WEATHER_FIXTURE).to_dict()


def test_valid_scenario_passes_validation(base_scenario_dict: dict[str, Any]) -> None:
    """A clean scenario has 0 validation errors."""
    errors = validate_scenario_data(base_scenario_dict)
    assert errors == []


def test_rule_1_invalid_id_regex(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 1: malformed scenario ID fails regex check."""
    base_scenario_dict["id"] = "weather.forecast.invalid"
    errors = validate_scenario_data(base_scenario_dict)
    rule_1_errors = [e for e in errors if e.rule == 1 or e.rule == "schema"]
    assert any("id" in e.message.lower() for e in rule_1_errors)


def test_rule_1_prefix_mismatch(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 1: scenario ID prefix must correspond to sandbox name."""
    base_scenario_dict["id"] = "crm.forecast.max-temp.001"
    errors = validate_scenario_data(base_scenario_dict)
    rule_1_errors = [e for e in errors if e.rule == 1]
    assert len(rule_1_errors) >= 1
    assert "prefix" in rule_1_errors[0].message
    assert "1" in str(rule_1_errors[0].rule)


def test_rule_1_duplicate_id_in_batch(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 1: duplicate scenario IDs in a batch are rejected with Rule 1."""
    known_ids: set[str] = set()
    errors1 = validate_scenario_data(base_scenario_dict, known_ids=known_ids)
    assert errors1 == []

    errors2 = validate_scenario_data(base_scenario_dict, known_ids=known_ids)
    rule_1_errors = [e for e in errors2 if e.rule == 1]
    assert len(rule_1_errors) == 1
    assert "duplicate" in rule_1_errors[0].message.lower()


def test_rule_2_tool_not_in_sandbox(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 2: primary tool must exist in sandbox."""
    base_scenario_dict["fault_targets"]["primary"] = ["non_existent_tool"]
    errors = validate_scenario_data(base_scenario_dict)
    rule_2_errors = [e for e in errors if e.rule == 2]
    assert len(rule_2_errors) == 1
    assert "non_existent_tool" in rule_2_errors[0].message
    assert "Rule 2" in rule_2_errors[0].message


def test_rule_2_unknown_sandbox(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 2: unknown sandbox triggers Rule 2 error."""
    base_scenario_dict["id"] = "unknown.task.name.001"
    base_scenario_dict["sandbox"] = "sb_unknown"
    errors = validate_scenario_data(base_scenario_dict)
    rule_2_errors = [e for e in errors if e.rule == 2]
    assert len(rule_2_errors) == 1
    assert "unknown" in rule_2_errors[0].message.lower()


def test_rule_2_entity_arg_not_in_tool_schema(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 2: entity_arg must exist in primary tool's inputSchema."""
    base_scenario_dict["fault_targets"]["entity_arg"] = "nonexistent_parameter"
    errors = validate_scenario_data(base_scenario_dict)
    rule_2_errors = [e for e in errors if e.rule == 2]
    assert len(rule_2_errors) == 1
    assert "Rule 2" in rule_2_errors[0].message
    assert "entity_arg" in rule_2_errors[0].message
    assert "nonexistent_parameter" in rule_2_errors[0].message
    assert "inputSchema" in rule_2_errors[0].message


def test_rule_3_write_missing_write_tools(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 3: kind=write requires write_tools and state_checks."""
    base_scenario_dict["kind"] = "write"
    base_scenario_dict["fault_targets"]["write_tools"] = []
    base_scenario_dict["expected"]["state_checks"] = [
        {"type": "state_equals", "path": "$.status", "value": "updated"}
    ]
    errors = validate_scenario_data(base_scenario_dict)
    rule_3_errors = [e for e in errors if e.rule == 3]
    assert any("write_tools" in e.message for e in rule_3_errors)


def test_rule_3_write_missing_state_checks(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 3: kind=write with empty state_checks fails Rule 3."""
    base_scenario_dict["kind"] = "write"
    base_scenario_dict["fault_targets"]["write_tools"] = ["get_forecast"]
    base_scenario_dict["expected"]["state_checks"] = []
    errors = validate_scenario_data(base_scenario_dict)
    rule_3_errors = [e for e in errors if e.rule == 3]
    assert any("state_checks" in e.message for e in rule_3_errors)


def test_rule_3_cross_source_missing_conflict_pair(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 3: kind=cross_source requires conflict_pair."""
    base_scenario_dict["kind"] = "cross_source"
    base_scenario_dict["fault_targets"]["conflict_pair"] = None
    errors = validate_scenario_data(base_scenario_dict)
    rule_3_errors = [e for e in errors if e.rule == 3]
    assert any("conflict_pair" in e.message for e in rule_3_errors)


def test_rule_4_empty_checks(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 4: expected.checks must have at least 1 check."""
    base_scenario_dict["expected"]["checks"] = []
    errors = validate_scenario_data(base_scenario_dict)
    assert any(e.rule in (4, "schema") for e in errors)


def test_rule_4_read_missing_forbid_and_numeric_path(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 4: read scenario must specify forbid or numeric_path."""
    base_scenario_dict["fault_targets"].pop("numeric_path", None)
    base_scenario_dict["expected"]["forbid"] = []
    errors = validate_scenario_data(base_scenario_dict)
    rule_4_errors = [e for e in errors if e.rule == 4]
    assert len(rule_4_errors) >= 1
    assert "Rule 4" in rule_4_errors[0].message


def test_rule_5_final_answer_mismatch(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 5: Oracle final_answer must satisfy expected.checks."""
    base_scenario_dict["oracle"]["final_answer"] = "99.9"
    errors = validate_scenario_data(base_scenario_dict)
    rule_5_errors = [e for e in errors if e.rule == 5]
    assert len(rule_5_errors) >= 1
    assert "Rule 5" in rule_5_errors[0].message


def test_rule_6_prompt_leaks_numeric_answer(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 6: prompt must not leak the number_close value as a string."""
    base_scenario_dict["prompt"] = "The expected value is 14.5 degrees."
    errors = validate_scenario_data(base_scenario_dict)
    rule_6_errors = [e for e in errors if e.rule == 6]
    assert len(rule_6_errors) >= 1
    assert "Rule 6" in rule_6_errors[0].message
    assert "leaks" in rule_6_errors[0].message


def test_rule_6_prompt_leaks_integer_equivalent(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 6: integer representation leakage triggers Rule 6."""
    base_scenario_dict["expected"]["checks"] = [{"type": "number_close", "value": 14.0, "tol": 0.5}]
    base_scenario_dict["oracle"]["final_answer"] = "14.0"
    base_scenario_dict["prompt"] = "Is the answer 14 or something else?"
    errors = validate_scenario_data(base_scenario_dict)
    rule_6_errors = [e for e in errors if e.rule == 6]
    assert len(rule_6_errors) >= 1


def test_rule_7_zh_prompt_insufficient_chinese(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 7: language=zh requires at least 30% Chinese characters."""
    base_scenario_dict["language"] = "zh"
    base_scenario_dict["prompt"] = "What will the maximum temperature be in Paris?"
    errors = validate_scenario_data(base_scenario_dict)
    rule_7_errors = [e for e in errors if e.rule == 7]
    assert len(rule_7_errors) >= 1
    assert "Rule 7" in rule_7_errors[0].message


def test_rule_7_zh_prompt_sufficient_chinese(base_scenario_dict: dict[str, Any]) -> None:
    """Rule 7: language=zh with >= 30% Chinese characters passes."""
    base_scenario_dict["language"] = "zh"
    base_scenario_dict["prompt"] = "巴黎2026年11月2日的最高气温是多少?"
    errors = validate_scenario_data(base_scenario_dict)
    rule_7_errors = [e for e in errors if e.rule == 7]
    assert rule_7_errors == []


def test_extract_numbers_note_n1() -> None:
    """Note N1: numbers with thousands separators and decimals are properly parsed."""
    text = "Totals: 1,234,567.89 USD, -42.5°C and 100 items."
    extracted = extract_numbers(text)
    assert 1234567.89 in extracted
    assert -42.5 in extracted
    assert 100.0 in extracted


def test_validate_paths_report(tmp_path: Path) -> None:
    """validate_paths validates multiple files and collects errors."""
    valid_file = tmp_path / "weather.forecast.valid.001.yaml"
    valid_file.write_text(WEATHER_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    report = validate_paths([valid_file])
    assert report.valid is True
    assert report.scenario_count == 1
    assert report.errors == []


def test_cli_validate_success() -> None:
    """CLI scenario validate succeeds on valid scenarios."""
    runner = CliRunner()
    result = runner.invoke(app, ["scenario", "validate", str(WEATHER_FIXTURE)])
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_cli_validate_json_output() -> None:
    """CLI scenario validate --json outputs parseable JSON report."""
    runner = CliRunner()
    result = runner.invoke(app, ["scenario", "validate", "--json", str(WEATHER_FIXTURE)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["valid"] is True
    assert data["scenario_count"] == 1
    assert data["errors"] == []


def test_cli_validate_failure(tmp_path: Path) -> None:
    """CLI scenario validate fails with code 3 on semantic errors."""
    bad_file = tmp_path / "weather.forecast.bad.001.yaml"
    data = load_scenario(WEATHER_FIXTURE).to_dict()
    data["language"] = "zh"
    data["prompt"] = "English only prompt"
    import yaml

    bad_file.write_text(yaml.safe_dump(data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["scenario", "validate", str(bad_file)])
    assert result.exit_code == 3
    assert "Rule 7" in result.output
