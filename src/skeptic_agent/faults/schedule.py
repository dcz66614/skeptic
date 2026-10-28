"""Deterministic fault scheduling and target resolution (S6, S7.3).

Every fault in every episode draws from one ``random.Random`` seeded by the run
seed, the episode id, the fault id and the tool name. Nothing else may feed the
schedule, so the same inputs always produce the same trigger sequence.
"""

import hashlib
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Literal

PRIMARY = "$primary"
"""The scenario's ``fault_targets.primary`` tools."""

WRITE = "$write"
"""The scenario's ``fault_targets.write_tools``."""

CONFLICT_B = "$conflict_b"
"""The second tool of the scenario's ``fault_targets.conflict_pair``."""

CallIndex = int | tuple[int, ...] | Literal["all"]
"""``when.call_index``: one attempt, a set of attempts, or every attempt."""

Persistence = Literal["permanent", "transient", "intermittent", "mixed"]
"""The four persistence modes of S6."""

PERSISTENCE_MODES: tuple[Persistence, ...] = ("permanent", "transient", "intermittent", "mixed")
"""The persistence modes in the S6 order."""


def fault_rng(seed: int, episode_id: str, fault_id: str, tool: str) -> random.Random:
    """Build the one RNG a scheduled fault may use (S7.3).

    Args:
        seed: The run seed.
        episode_id: The episode identifier.
        fault_id: The fault id.
        tool: The tool name the fault targets.

    Returns:
        ``random.Random`` seeded from the first 64 bits of the SHA-256 digest of
        ``"{seed}|{episode_id}|{fault_id}|{tool}"``.
    """
    key = f"{seed}|{episode_id}|{fault_id}|{tool}".encode()
    return random.Random(int(hashlib.sha256(key).hexdigest()[:16], 16))


@dataclass(frozen=True)
class ScenarioTargets:
    """The scenario fields a fault target may point at (S8.1).

    Attributes:
        primary: The tools under test.
        write_tools: The tools that change state.
        conflict_pair: The two tools that should agree on the same fact.
    """

    primary: tuple[str, ...] = ()
    write_tools: tuple[str, ...] = ()
    conflict_pair: tuple[str, str] | None = None


def _field(obj: object, name: str) -> Any:
    """Read a field from a mapping or from an object's attribute.

    Args:
        obj: A mapping or any object.
        name: The field name.

    Returns:
        The value, or ``None`` when the field is absent.
    """
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def _names(value: object) -> tuple[str, ...]:
    """Normalize a tool list field into a tuple of names.

    Args:
        value: A string, a sequence of names, or ``None``.

    Returns:
        The names.
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(name) for name in value)
    return ()


def scenario_targets(scenario: object | None) -> ScenarioTargets | None:
    """Read the target fields of a scenario.

    Args:
        scenario: A scenario mapping or model, or ``None`` when there is no
            scenario context.

    Returns:
        The targets, or ``None`` when there is no scenario context.
    """
    if scenario is None:
        return None
    fault_targets = _field(scenario, "fault_targets") or {}
    pair = _names(_field(fault_targets, "conflict_pair"))
    return ScenarioTargets(
        primary=_names(_field(fault_targets, "primary")),
        write_tools=_names(_field(fault_targets, "write_tools")),
        conflict_pair=(pair[0], pair[1]) if len(pair) >= 2 else None,
    )


def resolve_targets(target: str, scenario: object | None = None) -> tuple[str, ...]:
    """Turn a target expression into the tool name patterns it stands for.

    ``$primary`` uses the scenario's ``fault_targets.primary``, or ``*`` when
    there is no scenario context. ``$write`` and ``$conflict_b`` need a scenario
    and resolve to nothing without one.

    Args:
        target: A glob, ``$primary``, ``$write`` or ``$conflict_b``.
        scenario: The scenario mapping or model, or ``None``.

    Returns:
        The tool name patterns to match against.
    """
    if target == PRIMARY:
        targets = scenario_targets(scenario)
        if targets is None or not targets.primary:
            return ("*",)
        return targets.primary
    if target == WRITE:
        targets = scenario_targets(scenario)
        return targets.write_tools if targets is not None else ()
    if target == CONFLICT_B:
        targets = scenario_targets(scenario)
        if targets is None or targets.conflict_pair is None:
            return ()
        return (targets.conflict_pair[1],)
    return (target,)


def tool_matches(tool: str, patterns: Iterable[str]) -> bool:
    """Match a tool name against glob patterns, case-sensitively.

    Args:
        tool: The tool name.
        patterns: The glob patterns.

    Returns:
        ``True`` when any pattern matches.
    """
    return any(fnmatchcase(tool, pattern) for pattern in patterns)


def _indices(call_index: int | tuple[int, ...]) -> tuple[int, ...]:
    """Normalize a non-``"all"`` call index into a tuple.

    Args:
        call_index: One attempt or several.

    Returns:
        The attempts as a tuple.
    """
    return (call_index,) if isinstance(call_index, int) else call_index


@dataclass
class Schedule:
    """The stateful fault trigger for one (episode, fault, tool) (S6).

    Attributes:
        call_index: The attempts the fault may fire on.
        probability: The chance of firing on a qualifying attempt.
        persistence: The persistence mode.
        rng: The fault RNG from ``fault_rng``.
        n: The ``transient`` run length.
        p: The ``intermittent`` chance.
        permanent_p: The ``mixed`` permanent chance.
        triggered: The number of attempts that already fired.
        permanent: The chosen ``mixed`` branch; ``None`` until it is drawn.
    """

    call_index: CallIndex = 1
    probability: float = 1.0
    persistence: Persistence = "permanent"
    rng: random.Random = field(default_factory=random.Random)
    n: int = 1
    p: float = 0.5
    permanent_p: float = 0.6
    triggered: int = 0
    permanent: bool | None = None

    def next_trigger(self, call_index: int) -> bool:
        """Decide whether the fault fires on this attempt, and update the state.

        A ``mixed`` schedule draws its permanent branch before the first
        probability check, so every episode takes the same RNG path.
        ``when.call_index`` only gates the first firing; after it, persistence
        alone decides (S6).

        Args:
            call_index: The attempt number of the current call, from 1.

        Returns:
            ``True`` when the fault fires on this attempt.
        """
        self._ensure_mixed()
        if self.triggered == 0 and not self._qualifies(call_index):
            return False
        return self._roll()

    def next_event(self) -> bool:
        """Decide a ``tools/list`` event, which has no ``call_index``.

        Persistence and ``when.probability`` still apply and draw from this
        schedule's RNG. ``when.call_index`` does not, because a list response
        is not a ``tools/call`` attempt (S4.4, S6).

        Returns:
            ``True`` when the fault fires on this event.
        """
        self._ensure_mixed()
        return self._roll()

    def _ensure_mixed(self) -> None:
        """Draw the ``mixed`` branch once, before any other roll."""
        if self.persistence == "mixed" and self.permanent is None:
            self.permanent = self.rng.random() < self.permanent_p

    def _roll(self) -> bool:
        """Apply persistence and probability, then record a firing.

        Returns:
            ``True`` when the fault fires.
        """
        if not self.is_active_after():
            return False
        if self.rng.random() >= self.probability:
            return False
        self.triggered += 1
        return True

    def is_active_after(self) -> bool:
        """Report whether another attempt may fire after ``triggered`` firings.

        Before the first firing every mode is active. ``permanent`` and
        ``mixed`` with a permanent branch never stop; ``transient`` lasts ``n``
        firings; an ``intermittent`` attempt fires with probability ``p``;
        ``mixed`` with a transient branch lasts one firing.

        Returns:
            ``True`` when the fault can fire.
        """
        mode = self.persistence
        if self.triggered == 0:
            return True
        if mode == "mixed":
            if self.permanent is None:
                return True
            return self.permanent
        if mode == "permanent":
            return True
        if mode == "transient":
            return self.triggered < self.n
        if mode == "intermittent":
            return self.rng.random() < self.p
        raise ValueError(f"unknown persistence mode: {mode!r}")

    def _qualifies(self, call_index: int) -> bool:
        """Report whether ``when.call_index`` names this attempt.

        Args:
            call_index: The attempt number.

        Returns:
            ``True`` when the attempt may fire; ``0`` never does.
        """
        if call_index < 1:
            return False
        if self.call_index == "all":
            return True
        return call_index in _indices(self.call_index)
