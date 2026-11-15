"""Fault profile loading and episode expansion (S7.1, S7.4)."""

import hashlib
import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from skeptic_agent.data import get_schema_path
from skeptic_agent.faults.schedule import (
    CONFLICT_B,
    PERSISTENCE_MODES,
    PRIMARY,
    WRITE,
    CallIndex,
)

SCHEMA_PATH = get_schema_path("profile.schema.json")
"""The frozen ``skeptic.profile/v1`` JSON Schema."""


class ProfileError(ValueError):
    """A profile that cannot be loaded or does not match the schema."""


@dataclass(frozen=True)
class FaultEntry:
    """One ``faults`` entry of a profile (S7.1).

    Attributes:
        id: The fault id.
        target: The ``target.tool`` expression.
        call_index: ``when.call_index``.
        probability: ``when.probability``.
        persistence: The persistence mode.
        n: The ``transient`` run length.
        p: The ``intermittent`` chance.
        permanent_p: The ``mixed`` permanent chance.
        params: The fault-specific parameters.
        weight: The sampling weight; only used by ``sampled``.
    """

    id: str
    target: str = PRIMARY
    call_index: CallIndex = 1
    probability: float = 1.0
    persistence: str = "permanent"
    n: int = 1
    p: float = 0.5
    permanent_p: float = 0.6
    params: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0


@dataclass(frozen=True)
class Profile:
    """A loaded ``skeptic.profile/v1`` document (S7.1).

    Attributes:
        id: The profile id.
        description: A human-readable summary.
        expansion: ``per_fault`` or ``sampled``.
        samples_per_scenario: The sampled-mode sample count.
        include_clean: Whether a clean baseline episode is generated per seed.
        faults: The fault entries.
    """

    id: str
    description: str
    expansion: str
    samples_per_scenario: int | None
    include_clean: bool
    faults: tuple[FaultEntry, ...]


def _validator() -> Draft202012Validator:
    """Load the profile schema.

    Returns:
        A validator for ``skeptic.profile/v1``.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _call_index(value: object) -> CallIndex:
    """Normalize ``when.call_index``.

    Args:
        value: An integer, a list of integers, or ``"all"``.

    Returns:
        An integer, a tuple of integers, or ``"all"``.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return "all"
    if isinstance(value, Iterable):
        return tuple(int(item) for item in value)
    raise ProfileError(f"invalid call_index: {value!r}")


def _entry(raw: Mapping[str, Any]) -> FaultEntry:
    """Build a ``FaultEntry`` from one YAML mapping.

    Args:
        raw: A validated ``faults`` item.

    Returns:
        The entry.
    """
    target = raw.get("target") or {}
    when = raw.get("when") or {}
    persistence = raw.get("persistence") or {}
    mode = persistence.get("mode", "permanent")
    if mode not in PERSISTENCE_MODES:
        raise ProfileError(f"{raw['id']}: unknown persistence mode {mode!r}")
    return FaultEntry(
        id=str(raw["id"]),
        target=str(target.get("tool", PRIMARY)),
        call_index=_call_index(when.get("call_index", 1)),
        probability=float(when.get("probability", 1.0)),
        persistence=str(mode),
        n=int(persistence.get("n", 1)),
        p=float(persistence.get("p", 0.5)),
        permanent_p=float(persistence.get("permanent_p", 0.6)),
        params=dict(raw.get("params") or {}),
        weight=float(raw.get("weight", 1.0)),
    )


def load_profile(source: str | Path) -> Profile:
    """Load and validate a profile YAML file.

    Args:
        source: A path to a ``skeptic.profile/v1`` YAML document.

    Returns:
        The profile.

    Raises:
        ProfileError: When the file is missing, is not a mapping, or fails the
            schema.
    """
    path = Path(source)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"cannot read profile {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ProfileError(f"profile {path} is not a mapping")
    errors = sorted(_validator().iter_errors(raw), key=lambda err: list(err.absolute_path))
    if errors:
        message = "; ".join(f"{list(err.absolute_path)}: {err.message}" for err in errors)
        raise ProfileError(f"profile {path} does not match skeptic.profile/v1: {message}")
    return Profile(
        id=str(raw["id"]),
        description=str(raw["description"]),
        expansion=str(raw["expansion"]),
        samples_per_scenario=raw.get("samples_per_scenario"),
        include_clean=bool(raw["include_clean"]),
        faults=tuple(_entry(item) for item in raw["faults"]),
    )


@dataclass(frozen=True)
class Episode:
    """One episode of the expansion (S7.4).

    Attributes:
        scenario_id: The scenario the episode runs.
        scenario: The scenario mapping, carried through for the runner.
        fault: The fault to schedule, or ``None`` for the clean baseline.
        seed: The run seed.
        episode_id: ``"{run_id}:{scenario_id}:{fault_id or 'clean'}:{seed}"``.
    """

    scenario_id: str
    scenario: Any
    fault: FaultEntry | None
    seed: int
    episode_id: str


def _field(obj: object, name: str, default: Any = None) -> Any:
    """Read a field from a mapping or from an object's attribute.

    Args:
        obj: A mapping or any object.
        name: The field name.
        default: The value returned when the field is absent.

    Returns:
        The field value.
    """
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _required_params(scenario: object, tool: str) -> list[str]:
    """Return the required parameters of a tool when the scenario declares them.

    The authoritative list is the sandbox ``tools/list`` (S7.4); a scenario may
    carry it in ``tool_defs`` before the sandbox is started.

    Args:
        scenario: The scenario mapping.
        tool: The tool name.

    Returns:
        The required parameter names, or an empty list when unknown.
    """
    tool_defs = _field(scenario, "tool_defs") or {}
    definition = tool_defs.get(tool) if isinstance(tool_defs, Mapping) else None
    if not isinstance(definition, Mapping):
        return []
    input_schema = definition.get("inputSchema") or definition
    required = input_schema.get("required") if isinstance(input_schema, Mapping) else None
    return [str(name) for name in required] if isinstance(required, list) else []


def statically_applicable(entry: FaultEntry, scenario: object) -> bool:
    """Apply the static applicability rules of S7.4.

    ``L04`` needs HTTP, which ``scenario.transport == "http"`` records before
    the scenario is run. ``L07`` needs a required parameter, read from
    ``scenario.tool_defs``. ``S05`` needs ``entity_arg`` and ``decoys.entity``;
    ``S09`` needs ``conflict_pair``; ``S10`` needs ``write_tools``.

    Args:
        entry: The fault entry.
        scenario: The scenario mapping or model.

    Returns:
        ``False`` when the S7.4 rules rule the episode out.
    """
    if entry.id == "L04" and str(_field(scenario, "transport", "stdio")).lower() != "http":
        return False
    if entry.id == "L07":
        tools = _target_names(entry.target, scenario)
        # An empty required list is not "at least one required parameter".
        if not tools or any(not _required_params(scenario, tool) for tool in tools):
            return False
    fault_targets = _field(scenario, "fault_targets") or {}
    decoys = _field(scenario, "decoys") or {}
    if entry.id == "S05":
        return bool(_field(fault_targets, "entity_arg")) and bool(_field(decoys, "entity"))
    if entry.id == "S09":
        pair = _field(fault_targets, "conflict_pair")
        return isinstance(pair, (list, tuple)) and len(pair) >= 2
    if entry.id == "S10":
        write_tools = _field(fault_targets, "write_tools")
        return isinstance(write_tools, (list, tuple)) and len(write_tools) >= 1
    return True


def _target_names(target: str, scenario: object) -> list[str]:
    """Resolve a target expression to concrete tool names when it can.

    Args:
        target: The ``target.tool`` expression.
        scenario: The scenario mapping.

    Returns:
        The tool names, or an empty list for a glob that needs tool definitions.
    """
    fault_targets = _field(scenario, "fault_targets") or {}
    if target == PRIMARY:
        return [str(name) for name in _field(fault_targets, "primary") or []]
    if target == WRITE:
        return [str(name) for name in _field(fault_targets, "write_tools") or []]
    if target == CONFLICT_B:
        pair = _field(fault_targets, "conflict_pair") or []
        return [str(pair[1])] if len(pair) >= 2 else []
    return [] if any(char in target for char in "*?[") else [target]


def _sampler(seed: int, scenario_id: str, profile_id: str) -> random.Random:
    """Build the one RNG for the sampled draws of one scenario (S7.4).

    S7.4 writes ``Random(sha256(f"{k}|{s.id}|{p.id}"))``. ``random.Random``
    takes an int, so the seed is the first 64 bits of that digest, the same
    width S7.3 uses for a fault RNG. One generator serves every sample, so
    successive draws advance the same stream.

    Args:
        seed: The run seed.
        scenario_id: The scenario id.
        profile_id: The profile id.

    Returns:
        The sampler.
    """
    digest = hashlib.sha256(f"{seed}|{scenario_id}|{profile_id}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _choose(profile: Profile, rng: random.Random) -> FaultEntry:
    """Draw one fault with ``rng``, weighted by ``entry.weight`` (S7.4).

    Args:
        profile: The profile.
        rng: The sampler from ``_sampler``, advanced by this draw.

    Returns:
        The chosen fault entry.

    Raises:
        ProfileError: When the profile has no fault carrying a positive weight.
    """
    weights = [entry.weight for entry in profile.faults]
    if not profile.faults or sum(weights) <= 0:
        raise ProfileError(f"profile {profile.id}: sampled mode needs a positive weight")
    return profile.faults[rng.choices(range(len(weights)), weights=weights, k=1)[0]]


def expand(
    scenarios: Sequence[Any],
    profile: Profile,
    seeds: Iterable[int],
    run_id: str,
) -> list[Episode]:
    """Expand scenarios, a profile and seeds into the episodes to run (S7.4).

    For each seed: a clean baseline episode when ``include_clean`` is set, then
    either one episode per fault (``per_fault``) or ``samples_per_scenario``
    weighted draws (``sampled``). Episodes ruled out by the static
    applicability rules are not generated.

    Args:
        scenarios: Scenario mappings or models, each carrying ``id``.
        profile: The profile.
        seeds: The run seeds.
        run_id: The run id that starts every episode id.

    Returns:
        The episodes, in seed, scenario and fault order.
    """
    episodes: list[Episode] = []
    for seed in seeds:
        for scenario in scenarios:
            scenario_id = str(_field(scenario, "id"))
            if profile.include_clean:
                episodes.append(_episode(scenario, None, seed, run_id))
            if profile.expansion == "per_fault":
                for entry in profile.faults:
                    if statically_applicable(entry, scenario):
                        episodes.append(_episode(scenario, entry, seed, run_id))
            else:
                rng = _sampler(seed, scenario_id, profile.id)
                samples = profile.samples_per_scenario or 1
                for _ in range(samples):
                    entry = _choose(profile, rng)
                    if statically_applicable(entry, scenario):
                        episodes.append(_episode(scenario, entry, seed, run_id))
    return episodes


def _episode(scenario: Any, entry: FaultEntry | None, seed: int, run_id: str) -> Episode:
    """Build one expansion episode with the S7.4 id format.

    Args:
        scenario: The scenario mapping or model.
        entry: The fault, or ``None`` for the clean baseline.
        seed: The run seed.
        run_id: The run id.

    Returns:
        The episode.
    """
    scenario_id = str(_field(scenario, "id"))
    fault_id = entry.id if entry is not None else "clean"
    return Episode(
        scenario_id=scenario_id,
        scenario=scenario,
        fault=entry,
        seed=seed,
        episode_id=f"{run_id}:{scenario_id}:{fault_id}:{seed}",
    )
