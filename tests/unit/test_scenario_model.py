"""Unit tests for scenario model and serialization (S8, S36)."""

from pathlib import Path

import pytest

from skeptic_agent.scenario.model import (
    ScenarioError,
    load_scenario,
    save_scenario,
)

pytestmark = pytest.mark.unit

FIXTURE_PATH = Path("tests/fixtures/scenarios/weather.forecast.max-temp.001.yaml")


def test_load_scenario_from_file() -> None:
    """A valid scenario file loads and parses into the Scenario model."""
    scen = load_scenario(FIXTURE_PATH)
    assert scen.id == "weather.forecast.max-temp.001"
    assert scen.schema_ == "skeptic.scenario/v1"
    assert scen.sandbox == "sb_weather"
    assert scen.language == "en"
    assert scen.difficulty == "easy"
    assert scen.kind == "read"
    assert scen.fault_targets.primary == ["get_forecast"]
    assert scen.fault_targets.numeric_path == "$.max_c"
    assert len(scen.expected.checks) >= 1
    assert scen.oracle.final_answer == "14.5"
    assert len(scen.oracle.steps) == 1
    assert "default" in scen.oracle.recovery


def test_load_scenario_from_mapping() -> None:
    """A dictionary mapping is loaded directly into Scenario."""
    data = load_scenario(FIXTURE_PATH).to_dict()
    scen = load_scenario(data)
    assert scen.id == "weather.forecast.max-temp.001"
    assert scen.to_dict()["schema"] == "skeptic.scenario/v1"


def test_load_scenario_missing_file_raises_scenario_error() -> None:
    """A non-existent path raises ScenarioError."""
    with pytest.raises(ScenarioError, match="not found"):
        load_scenario("non_existent_file.yaml")


def test_load_scenario_invalid_yaml_raises_scenario_error(tmp_path: Path) -> None:
    """Malformed YAML raises ScenarioError."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("id: [unclosed", encoding="utf-8")
    with pytest.raises(ScenarioError, match="Failed to read scenario YAML"):
        load_scenario(bad_file)


def test_load_scenario_non_dict_yaml_raises_scenario_error(tmp_path: Path) -> None:
    """A YAML file containing a list instead of a mapping raises ScenarioError."""
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="did not contain a mapping"):
        load_scenario(bad_file)


def test_scenario_serialization_preserves_alias(tmp_path: Path) -> None:
    """save_scenario produces valid YAML with the alias key 'schema'."""
    scen = load_scenario(FIXTURE_PATH)
    out_file = tmp_path / "saved.yaml"
    save_scenario(scen, out_file)
    assert out_file.is_file()

    reloaded = load_scenario(out_file)
    assert reloaded.id == scen.id
    raw = reloaded.to_dict()
    assert "schema" in raw
    assert raw["schema"] == "skeptic.scenario/v1"


def test_scenario_forbids_extra_fields() -> None:
    """Extra unexpected fields on Scenario or nested models trigger ValidationError."""
    scen = load_scenario(FIXTURE_PATH)
    data = scen.to_dict()
    data["unexpected_field"] = "bogus"
    with pytest.raises(ScenarioError):
        load_scenario(data)
