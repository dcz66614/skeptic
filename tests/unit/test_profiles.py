"""Unit tests for fault profiles and episode expansion (S7.1, S7.2, S7.4)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine, load_profile_source, spec_from_entry
from skeptic_agent.faults.profiles import (
    FaultEntry,
    Profile,
    ProfileError,
    expand,
    load_profile,
    statically_applicable,
)

pytestmark = pytest.mark.unit

EXAMPLES = Path(__file__).resolve().parents[1] / "schemas" / "examples" / "profile"

RUN_ID = "20261105-142233-a1b2c3"

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

HTTP_WEATHER = {**WEATHER, "transport": "http"}

DRIFTED = {
    **WEATHER,
    "tool_defs": {"get_forecast": {"inputSchema": {"required": ["city", "date"]}}},
}

CROSS_SOURCE = {
    "id": "weather.forecast.max-temp.002",
    "fault_targets": {
        "primary": ["get_forecast"],
        "write_tools": [],
        "conflict_pair": ["get_forecast", "get_forecast_v2"],
    },
}

WRITE = {
    "id": "orders.place-order.001",
    "fault_targets": {"primary": ["place_order"], "write_tools": ["place_order"]},
}


@pytest.fixture
def profile_files(tmp_path: Path) -> Callable[[str], Profile]:
    """Provide a helper that loads a profile from YAML text.

    Args:
        tmp_path: The pytest temporary directory.

    Returns:
        A callable taking the YAML text and returning the profile.
    """
    counter = 0

    def load(text: str) -> Profile:
        nonlocal counter
        counter += 1
        path = tmp_path / f"profile-{counter}.yaml"
        path.write_text(text, encoding="utf-8")
        return load_profile(path)

    return load


def _profile_text(
    faults: str,
    *,
    expansion: str = "per_fault",
    samples: int = 3,
    include_clean: bool = True,
) -> str:
    """Build a profile YAML document.

    Args:
        faults: The ``faults`` list body, already indented.
        expansion: ``per_fault`` or ``sampled``.
        samples: The sampled-mode sample count.
        include_clean: Whether to include the clean baseline.

    Returns:
        The YAML text.
    """
    return (
        "schema: skeptic.profile/v1\n"
        "id: test\n"
        'description: "test profile"\n'
        f"expansion: {expansion}\n"
        f"samples_per_scenario: {samples}\n"
        f"include_clean: {str(include_clean).lower()}\n"
        "faults:\n"
        f"{faults}"
    )


PERMANENT = "  - {id: S04, target: {tool: $primary}, persistence: {mode: permanent}}\n"

WEIGHTED = (
    "  - {id: S04, target: {tool: $primary}, persistence: {mode: mixed}, weight: 1}\n"
    "  - {id: S01, target: {tool: $primary}, persistence: {mode: permanent}, weight: 3}\n"
)


def _entry(fault_id: str) -> FaultEntry:
    """Build a bare fault entry.

    Args:
        fault_id: The fault id.

    Returns:
        The entry.
    """
    return FaultEntry(id=fault_id)


def test_load_profile_reads_every_field(profile_files: Callable[[str], Profile]) -> None:
    """A valid profile loads with defaults filled in."""
    load = profile_files
    text = _profile_text(
        "  - id: S04\n"
        "    target: {tool: $write}\n"
        "    when: {call_index: [1, 2], probability: 0.5}\n"
        "    persistence: {mode: intermittent, p: 0.25}\n"
        "    params: {factor: 10}\n"
        "    weight: 2.5\n"
    )
    profile: Profile = load(text)
    assert profile.id == "test"
    assert profile.expansion == "per_fault"
    assert profile.samples_per_scenario == 3
    assert profile.include_clean is True
    entry = profile.faults[0]
    assert entry.id == "S04"
    assert entry.target == "$write"
    assert entry.call_index == (1, 2)
    assert entry.probability == 0.5
    assert entry.persistence == "intermittent"
    assert entry.p == 0.25
    assert entry.params == {"factor": 10}
    assert entry.weight == 2.5


def test_loaded_profile_accepts_the_schema_example() -> None:
    """The frozen example profile loads and keeps its call_index."""
    profile = load_profile(EXAMPLES / "valid_silent_core.yaml")
    assert profile.id == "silent-core"
    assert profile.faults[0].call_index == 1
    assert profile.faults[0].params == {"factor": 10}


def test_load_profile_rejects_schema_violations(tmp_path: Path) -> None:
    """A bad expansion or a missing file raises ProfileError."""
    with pytest.raises(ProfileError, match="does not match"):
        load_profile(EXAMPLES / "invalid_expansion.yaml")
    with pytest.raises(ProfileError, match="cannot read"):
        load_profile(tmp_path / "missing.yaml")


def test_none_profile_loads_with_no_faults() -> None:
    """A per_fault profile without faults is valid."""
    profile = load_profile(EXAMPLES / "valid_none.yaml")
    assert profile.faults == ()


def test_sampled_profile_needs_samples_and_a_fault(profile_files: Callable[[str], Profile]) -> None:
    """Sampled mode requires samples_per_scenario and at least one fault."""
    load = profile_files
    no_samples = (
        "schema: skeptic.profile/v1\n"
        "id: bad\n"
        'description: "bad"\n'
        "expansion: sampled\n"
        "include_clean: true\n"
        "faults: []\n"
    )
    with pytest.raises(ProfileError, match="does not match"):
        load(no_samples)
    with pytest.raises(ProfileError, match="does not match"):
        load(_profile_text("", expansion="sampled", samples=3))


def test_expand_per_fault_counts(profile_files: Callable[[str], Profile]) -> None:
    """Per seed: one clean episode plus one episode per applicable fault."""
    load = profile_files
    text = _profile_text(
        "  - {id: S04, target: {tool: $primary}}\n"
        "  - {id: S01, target: {tool: $primary}}\n"
        "  - {id: S10, target: {tool: $write}}\n"
    )
    profile: Profile = load(text)
    episodes = expand([WEATHER, WRITE], profile, [1, 2], RUN_ID)
    clean = [ep for ep in episodes if ep.fault is None]
    faults = [ep for ep in episodes if ep.fault is not None]
    assert len(clean) == 2 * 2
    assert len(faults) == 2 * (2 + 3)
    assert [ep.episode_id for ep in episodes[:3]] == [
        f"{RUN_ID}:weather.forecast.max-temp.001:clean:1",
        f"{RUN_ID}:weather.forecast.max-temp.001:S04:1",
        f"{RUN_ID}:weather.forecast.max-temp.001:S01:1",
    ]
    assert episodes[2].scenario is WEATHER
    assert episodes[2].seed == 1


def test_expand_without_clean(profile_files: Callable[[str], Profile]) -> None:
    """include_clean false drops the baseline episodes."""
    load = profile_files
    profile: Profile = load(_profile_text(PERMANENT, include_clean=False))
    episodes = expand([WEATHER], profile, [1], RUN_ID)
    assert [ep.episode_id for ep in episodes] == [f"{RUN_ID}:weather.forecast.max-temp.001:S04:1"]


def test_expand_sampled_draws_the_weighted_fault(profile_files: Callable[[str], Profile]) -> None:
    """Sampled mode adds samples_per_scenario weighted draws per seed and scenario."""
    load = profile_files
    profile: Profile = load(_profile_text(WEIGHTED, expansion="sampled", samples=4))
    episodes = expand([WEATHER], profile, [1], RUN_ID)
    sampled = [ep for ep in episodes if ep.fault is not None]
    assert len(sampled) == 4
    assert {ep.fault.id for ep in sampled if ep.fault} <= {"S04", "S01"}
    assert episodes[0].fault is None
    again = expand([WEATHER], profile, [1], RUN_ID)
    assert [ep.episode_id for ep in again] == [ep.episode_id for ep in episodes]


def test_expand_sampled_favours_the_heavier_weight(profile_files: Callable[[str], Profile]) -> None:
    """A weight of 3 versus 1 shows up across many seeds."""
    load = profile_files
    profile: Profile = load(_profile_text(WEIGHTED, expansion="sampled", samples=1))
    episodes = expand([WEATHER], profile, list(range(200)), RUN_ID)
    drawn = [ep.fault.id for ep in episodes if ep.fault is not None]
    assert drawn.count("S01") > drawn.count("S04")


def test_expand_sampled_rejects_a_zero_weight_profile(
    profile_files: Callable[[str], Profile],
) -> None:
    """Sampled mode without a positive weight raises instead of dividing by zero."""
    load = profile_files
    text = "  - {id: S04, target: {tool: $primary}, weight: 0}\n"
    profile: Profile = load(_profile_text(text, expansion="sampled", samples=1))
    with pytest.raises(ProfileError, match="positive weight"):
        expand([WEATHER], profile, [1], RUN_ID)


def test_static_applicability_l04_needs_http() -> None:
    """L04 is skipped unless the scenario is HTTP."""
    assert statically_applicable(_entry("L04"), WEATHER) is False
    assert statically_applicable(_entry("L04"), HTTP_WEATHER) is True


def test_static_applicability_l07_needs_a_required_param() -> None:
    """L07 is skipped unless the target tool declares a required parameter."""
    assert statically_applicable(_entry("L07"), WEATHER) is False
    assert statically_applicable(_entry("L07"), DRIFTED) is True
    glob = FaultEntry(id="L07", target="get_*")
    assert statically_applicable(glob, DRIFTED) is False


def test_static_applicability_s05_needs_entity_arg_and_decoy() -> None:
    """S05 needs fault_targets.entity_arg and decoys.entity."""
    assert statically_applicable(_entry("S05"), WEATHER) is True
    assert statically_applicable(_entry("S05"), {"id": "x", "fault_targets": {}}) is False
    no_decoy = {**WEATHER, "decoys": {}}
    assert statically_applicable(_entry("S05"), no_decoy) is False


def test_static_applicability_s09_needs_conflict_pair() -> None:
    """S09 needs fault_targets.conflict_pair."""
    assert statically_applicable(_entry("S09"), WEATHER) is False
    assert statically_applicable(_entry("S09"), CROSS_SOURCE) is True


def test_static_applicability_s10_needs_write_tools() -> None:
    """S10 needs fault_targets.write_tools."""
    assert statically_applicable(_entry("S10"), WEATHER) is False
    assert statically_applicable(_entry("S10"), WRITE) is True


def test_static_applicability_other_faults_always_pass() -> None:
    """Faults with no rule of their own are applicable everywhere."""
    assert statically_applicable(_entry("S04"), WEATHER) is True
    assert statically_applicable(FaultEntry(id="S09", target="$write"), WRITE) is False


def test_expand_skips_statically_inapplicable_faults(
    profile_files: Callable[[str], Profile],
) -> None:
    """Skipped faults produce no episode for the scenario that lacks their fields."""
    load = profile_files
    text = _profile_text(
        "  - {id: S09, target: {tool: $conflict_b}}\n"
        "  - {id: S10, target: {tool: $write}}\n"
        "  - {id: S04, target: {tool: $primary}}\n"
    )
    profile: Profile = load(text)
    episodes = expand([WEATHER, CROSS_SOURCE, WRITE], profile, [1], RUN_ID)
    by_scenario: dict[str, set[str]] = {}
    for episode in episodes:
        by_scenario.setdefault(episode.scenario_id, set()).add(
            episode.fault.id if episode.fault else "clean"
        )
    assert by_scenario["weather.forecast.max-temp.001"] == {"clean", "S04"}
    assert by_scenario["weather.forecast.max-temp.002"] == {"clean", "S09", "S04"}
    assert by_scenario["orders.place-order.001"] == {"clean", "S10", "S04"}


def test_spec_from_entry() -> None:
    """A profile entry becomes a FaultSpec with every field carried over."""
    entry = FaultEntry(
        id="S04",
        target="$write",
        call_index=(2, 3),
        probability=0.5,
        persistence="transient",
        n=2,
        p=0.2,
        permanent_p=0.7,
        params={"factor": 10},
    )
    spec = spec_from_entry(entry)
    assert spec == FaultSpec(
        fault_id="S04",
        tool="$write",
        call_index=(2, 3),
        probability=0.5,
        persistence="transient",
        n=2,
        p=0.2,
        permanent_p=0.7,
        params={"factor": 10},
    )


def test_engine_leaves_unregistered_faults_inactive() -> None:
    """A fault with no implementation yet is planned but can never fire."""
    engine = FaultEngine([spec_from_entry(_entry("A01"))], scenario=WEATHER)
    assert engine.specs[0].fault_id == "A01"
    assert engine.planned[0].fault is None
    assert engine.counts_attempts() is False


def test_load_profile_source_reads_a_path(tmp_path: Path, profile_files: object) -> None:
    """load_profile_source loads a YAML path directly and rejects unknown names."""
    load = profile_files
    profile: Profile = load(_profile_text(PERMANENT))
    path = tmp_path / "profile-1.yaml"
    assert load_profile_source(path).id == profile.id
    assert load_profile_source(str(path)).id == profile.id
    with pytest.raises(ProfileError, match="unknown profile"):
        load_profile_source("no-such-profile")
