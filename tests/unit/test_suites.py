"""Unit tests for benchmark suite model, loading, and resolution (S1, S39)."""

from pathlib import Path

import pytest

from skeptic_agent.scenario.suites import (
    Suite,
    SuiteError,
    list_suites,
    load_suite,
    resolve_suite_scenarios,
    save_suite,
)

pytestmark = pytest.mark.unit


def test_suite_model_serialization() -> None:
    """Suite model serializes to dict as expected."""
    suite = Suite(
        id="test-suite",
        title="Test Suite",
        description="A test suite",
        scenarios=["bench/scenarios/weather/test.yaml"],
    )
    d = suite.to_dict()
    assert d["id"] == "test-suite"
    assert d["title"] == "Test Suite"
    assert d["description"] == "A test suite"
    assert d["scenarios"] == ["bench/scenarios/weather/test.yaml"]


def test_load_suite_from_file(tmp_path: Path) -> None:
    """Suite loads properly from a file path."""
    suite_file = tmp_path / "smoke.yaml"
    suite_file.write_text("id: smoke\ntitle: Smoke\nscenarios:\n  - scen1.yaml\n", encoding="utf-8")

    suite = load_suite(suite_file)
    assert suite.id == "smoke"
    assert suite.title == "Smoke"
    assert suite.scenarios == ["scen1.yaml"]


def test_load_suite_by_name(tmp_path: Path) -> None:
    """Suite loads by name from a specified suites_dir."""
    suite_file = tmp_path / "custom.yaml"
    suite_file.write_text("id: custom\nscenarios: []\n", encoding="utf-8")

    suite = load_suite("custom", suites_dir=tmp_path)
    assert suite.id == "custom"
    assert suite.scenarios == []

    # Also test .yml fallback
    yml_file = tmp_path / "custom_yml.yml"
    yml_file.write_text("id: custom_yml\nscenarios: []\n", encoding="utf-8")
    suite_yml = load_suite("custom_yml", suites_dir=tmp_path)
    assert suite_yml.id == "custom_yml"


def test_load_suite_from_mapping() -> None:
    """Suite loads directly from a mapping."""
    data = {"id": "map-suite", "scenarios": ["a", "b"]}
    suite = load_suite(data)
    assert suite.id == "map-suite"
    assert len(suite.scenarios) == 2

    with pytest.raises(SuiteError, match="Failed to validate suite mapping"):
        load_suite({"invalid": 123})


def test_load_suite_missing_raises(tmp_path: Path) -> None:
    """Missing suite file or name raises SuiteError."""
    with pytest.raises(SuiteError, match="Suite not found"):
        load_suite("nonexistent", suites_dir=tmp_path)


def test_load_suite_invalid_yaml(tmp_path: Path) -> None:
    """Invalid YAML or non-dict contents raise SuiteError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("{ unclosed", encoding="utf-8")
    with pytest.raises(SuiteError, match="Failed to read suite YAML"):
        load_suite(bad_yaml)

    not_dict = tmp_path / "list.yaml"
    not_dict.write_text("- item1\n- item2\n", encoding="utf-8")
    with pytest.raises(SuiteError, match="did not contain a mapping"):
        load_suite(not_dict)

    bad_schema = tmp_path / "bad_schema.yaml"
    bad_schema.write_text("not_id: 123\n", encoding="utf-8")
    with pytest.raises(SuiteError, match="Failed to validate suite from"):
        load_suite(bad_schema)


def test_save_and_reload_suite(tmp_path: Path) -> None:
    """save_suite writes clean YAML readable by load_suite."""
    out_file = tmp_path / "sub" / "saved.yaml"
    suite = Suite(id="saved-v1", title="Saved", scenarios=["s1", "s2"])
    save_suite(suite, out_file)

    assert out_file.is_file()
    reloaded = load_suite(out_file)
    assert reloaded.id == "saved-v1"
    assert reloaded.scenarios == ["s1", "s2"]


def test_list_suites(tmp_path: Path) -> None:
    """list_suites lists suite IDs and their scenario counts."""
    # Test missing dir returns empty dict
    assert list_suites(tmp_path / "missing_dir") == {}

    (tmp_path / "s1.yaml").write_text("id: s1\nscenarios: [a, b, c]\n", encoding="utf-8")
    (tmp_path / "s2.yml").write_text("id: s2\nscenarios: [x]\n", encoding="utf-8")
    (tmp_path / "bad.yaml").write_text("invalid yaml: [", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("not yaml", encoding="utf-8")

    counts = list_suites(tmp_path)
    assert counts == {"s1": 3, "s2": 1}


def test_resolve_suite_scenarios(tmp_path: Path) -> None:
    """resolve_suite_scenarios resolves relative paths and scenario IDs."""
    scen_dir = tmp_path / "scenarios" / "weather"
    scen_dir.mkdir(parents=True)
    scen_file = scen_dir / "weather.forecast.paris-max.001.yaml"

    fixture_scen = Path("tests/fixtures/scenarios/weather.forecast.max-temp.001.yaml").read_text(
        encoding="utf-8"
    )
    scen_file.write_text(fixture_scen, encoding="utf-8")

    suite = Suite(
        id="test-resolve",
        scenarios=[
            str(scen_file),  # Absolute or existing relative path
            "weather.forecast.paris-max.001",  # Scenario ID lookup
        ],
    )

    resolved = resolve_suite_scenarios(suite, scenarios_dir=tmp_path / "scenarios")
    assert len(resolved) == 2
    assert resolved[0].id == "weather.forecast.max-temp.001"
    assert resolved[1].id == "weather.forecast.max-temp.001"

    # Missing scenario raises SuiteError
    bad_suite = Suite(id="bad-suite", scenarios=["nonexistent-scenario"])
    with pytest.raises(SuiteError, match="could not be resolved"):
        resolve_suite_scenarios(bad_suite, scenarios_dir=tmp_path / "scenarios")

    # Corrupt scenario raises SuiteError
    corrupt_file = scen_dir / "corrupt.yaml"
    corrupt_file.write_text("not valid yaml: [", encoding="utf-8")
    corrupt_suite = Suite(id="corrupt-suite", scenarios=[str(corrupt_file)])
    with pytest.raises(SuiteError, match="Failed to load scenario"):
        resolve_suite_scenarios(corrupt_suite, scenarios_dir=tmp_path / "scenarios")


def test_resolve_suite_scenarios_relative_to_root() -> None:
    """resolve_suite_scenarios resolves relative path from ROOT_DIR."""
    suite = Suite(
        id="test-root-rel",
        scenarios=["bench/scenarios/weather/weather.forecast.paris-max.001.yaml"],
    )
    res = resolve_suite_scenarios(suite)
    assert len(res) == 1
    assert res[0].id == "weather.forecast.paris-max.001"
