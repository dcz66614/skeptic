"""Unit tests for fault scheduling and target resolution (S6, S7.3)."""

import statistics

import pytest

from skeptic_agent.faults.schedule import (
    Schedule,
    fault_rng,
    resolve_targets,
    scenario_targets,
    tool_matches,
)

pytestmark = pytest.mark.unit

SCENARIO = {
    "id": "weather.forecast.max-temp.001",
    "fault_targets": {
        "primary": ["get_forecast"],
        "write_tools": ["place_order", "cancel_order"],
        "conflict_pair": ["get_forecast", "get_forecast_v2"],
    },
}


def _sequence(
    seed: int = 1,
    episode: str = "run:weather.forecast.max-temp.001:S04:1",
    fault_id: str = "S04",
    tool: str = "get_forecast",
    *,
    attempts: int = 6,
    call_index: int | tuple[int, ...] | str = "all",
    probability: float = 1.0,
    persistence: str = "permanent",
    n: int = 1,
    p: float = 0.5,
    permanent_p: float = 0.6,
) -> list[bool]:
    """Run one schedule and return its trigger flags.

    Args:
        seed: The run seed.
        episode: The episode id.
        fault_id: The fault id.
        tool: The tool name.
        attempts: How many attempts to simulate.
        call_index: ``when.call_index``.
        probability: ``when.probability``.
        persistence: The persistence mode.
        n: The transient run length.
        p: The intermittent chance.
        permanent_p: The mixed permanent chance.

    Returns:
        One flag per attempt.
    """
    schedule = Schedule(
        call_index=call_index,
        probability=probability,
        persistence=persistence,  # type: ignore[arg-type]
        rng=fault_rng(seed, episode, fault_id, tool),
        n=n,
        p=p,
        permanent_p=permanent_p,
    )
    return [schedule.next_trigger(index) for index in range(1, attempts + 1)]


def test_same_inputs_give_the_same_sequence_a_thousand_times() -> None:
    """The same (seed, episode, fault, tool) always yields the same sequence."""
    kwargs = {
        "attempts": 8,
        "call_index": "all",
        "probability": 0.7,
        "persistence": "mixed",
    }
    first = _sequence(**kwargs)
    for _ in range(1000):
        assert _sequence(**kwargs) == first


def test_each_input_component_changes_the_rng() -> None:
    """A different seed, episode, fault or tool moves the stream."""
    base = _sequence(persistence="intermittent", attempts=10)
    assert _sequence(seed=2, persistence="intermittent", attempts=10) != base
    assert _sequence(episode="other", persistence="intermittent", attempts=10) != base
    assert _sequence(fault_id="S05", persistence="intermittent", attempts=10) != base
    assert _sequence(tool="other", persistence="intermittent", attempts=10) != base


def test_fault_rng_is_the_s7_3_formula() -> None:
    """The RNG is Random(int(sha256(key).hexdigest()[:16], 16))."""
    import hashlib
    import random

    expected = random.Random(int(hashlib.sha256(b"3|ep|S04|get_forecast").hexdigest()[:16], 16))
    actual = fault_rng(3, "ep", "S04", "get_forecast")
    assert [actual.random() for _ in range(5)] == [expected.random() for _ in range(5)]


def test_permanent_fires_from_the_first_trigger_forever() -> None:
    """Permanent fires on every attempt once call_index qualifies."""
    assert _sequence(persistence="permanent") == [True] * 6
    assert _sequence(persistence="permanent", call_index=(2, 6)) == [
        False,
        True,
        False,
        False,
        False,
        True,
    ]


def test_transient_fires_exactly_n_times() -> None:
    """Transient lasts n consecutive attempts from the first firing."""
    assert _sequence(persistence="transient", n=1) == [True] + [False] * 5
    assert _sequence(persistence="transient", n=3) == [True, True, True, False, False, False]


def test_transient_starts_at_the_first_qualifying_index() -> None:
    """Transient waits for call_index and then runs its n firings without a gap."""
    flags = _sequence(persistence="transient", n=2, call_index=(3, 5), attempts=9)
    assert flags == [False, False, True, False, True, False, False, False, False]
    with_gap = _sequence(persistence="transient", n=3, call_index=2, attempts=6)
    assert with_gap == [False, True, False, False, False, False]


def test_intermittent_fires_each_attempt_with_probability_p() -> None:
    """Intermittent keeps firing after the first firing, with chance p."""
    flags = _sequence(persistence="intermittent", p=0.5, attempts=200)
    assert 40 <= sum(flags) <= 140
    never = _sequence(persistence="intermittent", p=0.0, attempts=20)
    assert never == [False] * 20


def test_intermittent_rate_is_close_to_p() -> None:
    """Over many seeds the intermittent rate converges on p."""
    rates = [
        sum(_sequence(seed=seed, persistence="intermittent", p=0.5, attempts=200)) / 200
        for seed in range(200)
    ]
    assert 0.4 < statistics.mean(rates) < 0.6


def test_mixed_chooses_permanent_or_transient_at_the_start() -> None:
    """Mixed is all-permanent or a single transient firing, never anything else."""
    shapes = {
        tuple(_sequence(seed=seed, persistence="mixed", permanent_p=0.6, attempts=6))
        for seed in range(100)
    }
    assert shapes == {(True,) * 6, (True,) + (False,) * 5}
    always_permanent = _sequence(persistence="mixed", permanent_p=1.0)
    assert always_permanent == [True] * 6
    always_transient = _sequence(persistence="mixed", permanent_p=0.0)
    assert always_transient == [True] + [False] * 5


def test_mixed_picks_permanent_about_sixty_percent_of_the_time() -> None:
    """The permanent branch is chosen with probability permanent_p."""
    permanent = sum(
        _sequence(seed=seed, persistence="mixed", permanent_p=0.6, attempts=2)[1]
        for seed in range(300)
    )
    assert 0.5 < permanent / 300 < 0.7


def test_call_index_int_list_and_all() -> None:
    """call_index as an int, a list or "all" selects the right attempts."""
    assert _sequence(call_index=2) == [False, True, False, False, False, False]
    assert _sequence(call_index=(1, 4)) == [True, False, False, True, False, False]
    assert _sequence(call_index="all") == [True] * 6


def test_probability_gates_each_qualifying_attempt() -> None:
    """Probability 0 never fires; probability 1 fires on every qualifying attempt."""
    assert _sequence(probability=0.0) == [False] * 6
    assert _sequence(probability=1.0) == [True] * 6
    half = [_sequence(seed=seed, probability=0.5) for seed in range(200)]
    rate = sum(flag for flags in half for flag in flags) / (200 * 6)
    assert 0.35 < rate < 0.65


def test_call_index_zero_never_fires() -> None:
    """An attempt number of 0 (no counted call) does not qualify."""
    assert _sequence(call_index="all", attempts=1) == [True]
    schedule = Schedule(call_index="all", rng=fault_rng(1, "ep", "S04", "tool"))
    assert schedule.next_trigger(0) is False


def test_unknown_persistence_mode_is_rejected() -> None:
    """An unknown persistence mode raises instead of silently doing nothing."""
    schedule = Schedule(persistence="sometimes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown persistence mode"):
        schedule.next_trigger(1)


def test_resolve_targets_primary_write_conflict_b() -> None:
    """$primary, $write and $conflict_b resolve against the scenario."""
    assert resolve_targets("$primary", SCENARIO) == ("get_forecast",)
    assert resolve_targets("$write", SCENARIO) == ("place_order", "cancel_order")
    assert resolve_targets("$conflict_b", SCENARIO) == ("get_forecast_v2",)
    assert resolve_targets("get_*") == ("get_*",)


def test_resolve_targets_without_scenario() -> None:
    """$primary is * without a scenario; $write and $conflict_b resolve to nothing."""
    assert resolve_targets("$primary") == ("*",)
    assert resolve_targets("$write") == ()
    assert resolve_targets("$conflict_b", None) == ()
    empty = {"id": "s", "fault_targets": {"primary": [], "conflict_pair": None}}
    assert resolve_targets("$primary", empty) == ("*",)
    assert resolve_targets("$conflict_b", empty) == ()


def test_scenario_targets_reads_lists_and_objects() -> None:
    """Targets can be read from a mapping or from attributes."""
    targets = scenario_targets(SCENARIO)
    assert targets is not None
    assert targets.primary == ("get_forecast",)
    assert targets.write_tools == ("place_order", "cancel_order")
    assert targets.conflict_pair == ("get_forecast", "get_forecast_v2")
    assert scenario_targets(None) is None


def test_tool_matches_globs() -> None:
    """Tool names match glob patterns case-sensitively."""
    assert tool_matches("get_forecast", ("*",))
    assert tool_matches("get_forecast", ("get_*",))
    assert not tool_matches("Get_forecast", ("get_*",))
    assert not tool_matches("place_order", ("get_*",))
