"""The six built-in profiles and the fault catalogue (S7.2, S2, F25)."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.faults.catalog import CATALOGUE, catalogue
from skeptic_agent.faults.engine import (
    PROFILES_DIR,
    FaultEngine,
    load_profile_source,
    spec_from_entry,
)
from skeptic_agent.faults.profiles import Profile, expand, load_profile
from skeptic_agent.faults.registry import FAULT_IDS, REGISTRY

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "profile.schema.json"

PROFILE_IDS = (
    "none",
    "loud-core",
    "silent-core",
    "adversarial-core",
    "cross-source",
    "realistic-2026",
)

REALISTIC_WEIGHTS = {
    "L01": 0.10,
    "L02": 0.05,
    "L03": 0.10,
    "L05": 0.08,
    "L06": 0.04,
    "L07": 0.05,
    "S01": 0.08,
    "S02": 0.08,
    "S03": 0.10,
    "S04": 0.07,
    "S05": 0.05,
    "S06": 0.03,
    "S07": 0.04,
    "S08": 0.03,
    "S10": 0.05,
    "A01": 0.03,
    "A02": 0.01,
    "A03": 0.01,
}
"""The S7.2 weights of ``realistic-2026``."""

WEATHER = {
    "id": "weather.forecast.max-temp.001",
    "fault_targets": {
        "primary": ["get_forecast"],
        "write_tools": [],
        "conflict_pair": None,
        "entity_arg": "city",
    },
    "decoys": {"entity": "Lyon"},
}

WRITE = {
    "id": "orders.place-order.001",
    "fault_targets": {"primary": ["place_order"], "write_tools": ["place_order"]},
}

CROSS_SOURCE = {
    "id": "weather.forecast.max-temp.002",
    "fault_targets": {
        "primary": ["get_forecast"],
        "conflict_pair": ["get_forecast", "get_forecast_v2"],
    },
}

RUN_ID = "20261105-142233-a1b2c3"


def _files() -> list[Path]:
    """Return the built-in profile files.

    Returns:
        The YAML files in ``PROFILES_DIR``.
    """
    return sorted(PROFILES_DIR.glob("*.yaml"))


def test_profiles_dir_holds_exactly_the_six_profiles() -> None:
    """S7.2 names six profiles and nothing else lives in the directory."""
    assert sorted(PROFILE_IDS) == [path.stem for path in _files()]


@pytest.mark.parametrize("path", _files(), ids=lambda path: str(path.stem))
def test_profile_matches_the_schema(path: Path) -> None:
    """Every built-in profile validates against the frozen JSON Schema."""
    validate_document(path)


def validate_document(path: Path) -> None:
    """Validate one profile file against the frozen JSON Schema.

    Args:
        path: The profile file.

    Raises:
        jsonschema.ValidationError: When the document does not match.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("path", _files(), ids=lambda path: str(path.stem))
def test_profile_loads_by_source(path: Path) -> None:
    """Both the file path and the bare id load the same profile."""
    from_file = load_profile(path)
    from_id = load_profile_source(path.stem)
    assert from_file == from_id
    assert from_file.id == path.stem


def test_six_profiles_cover_the_s7_2_membership() -> None:
    """Each profile carries exactly the faults of its S7.2 row."""
    none = load_profile(PROFILES_DIR / "none.yaml")
    assert none.faults == ()
    assert none.include_clean is True

    expected = {
        "loud-core": ["L01", "L02", "L03", "L05", "L06", "L07"],
        "silent-core": ["S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S10"],
        "adversarial-core": ["A01", "A02", "A03"],
        "cross-source": ["S09"],
    }
    for profile_id, fault_ids in expected.items():
        profile: Profile = load_profile(PROFILES_DIR / f"{profile_id}.yaml")
        assert [entry.id for entry in profile.faults] == fault_ids
        assert profile.expansion == "per_fault"


def test_loud_and_silent_core_persistence() -> None:
    """L01, L03 and L05 are transient; S10 targets the write tools."""
    loud = load_profile(PROFILES_DIR / "loud-core.yaml")
    modes = {entry.id: entry.persistence for entry in loud.faults}
    assert modes["L01"] == modes["L03"] == modes["L05"] == "transient"
    assert modes["L02"] == modes["L06"] == modes["L07"] == "permanent"

    silent = load_profile(PROFILES_DIR / "silent-core.yaml")
    targets = {entry.id: entry.target for entry in silent.faults}
    assert targets["S10"] == "$write"
    assert targets["S04"] == "$primary"
    assert load_profile(PROFILES_DIR / "cross-source.yaml").faults[0].target == "$conflict_b"


def test_realistic_weights_and_persistence() -> None:
    """realistic-2026 is sampled three times, every fault mixed at 0.6."""
    profile = load_profile(PROFILES_DIR / "realistic-2026.yaml")
    assert profile.expansion == "sampled"
    assert profile.samples_per_scenario == 3
    assert {entry.id: entry.weight for entry in profile.faults} == REALISTIC_WEIGHTS
    assert sum(REALISTIC_WEIGHTS.values()) == pytest.approx(1.0)
    for entry in profile.faults:
        assert entry.persistence == "mixed"
        assert entry.permanent_p == 0.6


def test_every_profile_fault_is_a_registered_fault() -> None:
    """A profile never names an id outside S6 or an unregistered fault."""
    for path in _files():
        for entry in load_profile(path).faults:
            assert entry.id in FAULT_IDS
            assert entry.id in REGISTRY


def test_every_builtin_profile_engine_plans_its_faults() -> None:
    """Each profile expands and its engine resolves every scheduled fault."""
    for path in _files():
        profile = load_profile(path)
        episodes = expand([WEATHER, WRITE, CROSS_SOURCE], profile, [1], RUN_ID)
        planned = [spec_from_entry(episode.fault) for episode in episodes if episode.fault]
        engine = FaultEngine(planned, scenario=WEATHER)
        if path.stem == "none":
            assert engine.planned == []
        else:
            assert engine.planned
            assert all(item.fault is not None for item in engine.planned)


def test_realistic_expansion_is_deterministic() -> None:
    """Every seed draws the same faults and the same number of episodes."""
    profile = load_profile(PROFILES_DIR / "realistic-2026.yaml")
    scenario = {**WEATHER, "id": "weather.forecast.max-temp.003"}
    first = expand([scenario], profile, [1, 2, 3], RUN_ID)
    second = expand([scenario], profile, [1, 2, 3], RUN_ID)
    assert [episode.episode_id for episode in first] == [episode.episode_id for episode in second]
    assert all(episode.fault is not None for episode in first)


def test_catalogue_has_all_twenty_faults_in_order() -> None:
    """The catalogue lists the 20 S6 faults in catalogue order."""
    entries = catalogue()
    assert [entry["id"] for entry in entries] == list(FAULT_IDS)
    assert len(CATALOGUE) == 20
    for entry in entries:
        assert entry["class"] in {"loud", "silent", "adversarial"}
        assert entry["citations"]


def test_catalogue_filter_by_class() -> None:
    """Filtering keeps the S6 order inside one class."""
    loud = catalogue("loud")
    assert [entry["id"] for entry in loud] == ["L01", "L02", "L03", "L04", "L05", "L06", "L07"]
    assert [entry["id"] for entry in catalogue("adversarial")] == ["A01", "A02", "A03"]
    assert catalogue("silent") == [entry for entry in catalogue() if entry["class"] == "silent"]


def test_catalogue_classes_match_the_registry() -> None:
    """Every registered fault reports the class its prefix and the catalogue give."""
    for fault_id, fault_cls in REGISTRY.items():
        entry = next(item for item in catalogue() if item["id"] == fault_id)
        assert entry["class"] == fault_cls.cls


def test_cli_faults_list_json_lists_twenty() -> None:
    """``skeptic faults list --json`` prints the 20 faults as one JSON array."""
    result = CliRunner().invoke(app, ["faults", "list", "--json"])
    assert result.exit_code == 0
    entries = json.loads(result.stdout)
    assert [entry["id"] for entry in entries] == list(FAULT_IDS)


def test_cli_faults_list_json_filters_by_class() -> None:
    """``--class`` filters both the JSON and the table output."""
    result = CliRunner().invoke(app, ["faults", "list", "--json", "--class", "silent"])
    entries = json.loads(result.stdout)
    assert len(entries) == 10
    assert {entry["class"] for entry in entries} == {"silent"}


def test_cli_faults_list_table_and_bad_class() -> None:
    """The table lists every fault; an unknown class is a usage error."""
    result = CliRunner().invoke(app, ["faults", "list"])
    assert result.exit_code == 0
    assert result.stdout.count("\n") == 20
    assert "S04" in result.stdout

    bad = CliRunner().invoke(app, ["faults", "list", "--class", "bogus"])
    assert bad.exit_code == 2
    assert "unknown fault class" in bad.stdout + bad.output
