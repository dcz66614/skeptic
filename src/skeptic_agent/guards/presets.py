"""Guard presets and guard name resolution (S11).

Defines the 8 guards from S11 and the presets:
- ``none``: No guards enabled.
- ``all``: G01-G08 enabled.
- ``recommended``: G02-G08 (tentative before G53 AB experimentation, excluding G01).
"""

from collections.abc import Sequence

ALL_GUARDS: tuple[str, ...] = (
    "evidence_contract",  # G01
    "schema_guard",  # G02
    "staleness_guard",  # G03
    "emptiness_guard",  # G04
    "retry_guard",  # G05
    "loop_breaker",  # G06
    "injection_shield",  # G07
    "drift_lock",  # G08
)
"""All 8 guards defined in S11, in standard canonical order."""

PRESETS: dict[str, list[str]] = {
    "none": [],
    "all": list(ALL_GUARDS),
    "recommended": [
        "schema_guard",
        "staleness_guard",
        "emptiness_guard",
        "retry_guard",
        "loop_breaker",
        "injection_shield",
        "drift_lock",
    ],
}
"""Standard presets from S11."""


def resolve_guards(guards: str | Sequence[str] | None) -> list[str]:
    """Resolve a guards specification into a list of valid guard names.

    Args:
        guards: Preset name ("none", "all", "recommended"), comma-separated
            guard names, sequence of guard names, or None.

    Returns:
        List of resolved guard names.

    Raises:
        ValueError: If an unknown guard name or preset is specified.
    """
    if guards is None:
        return []

    if isinstance(guards, str):
        key = guards.strip().lower()
        if key in PRESETS:
            return list(PRESETS[key])
        names = [g.strip() for g in guards.split(",") if g.strip()]
    else:
        names = [str(g).strip() for g in guards if str(g).strip()]

    # Validate names
    all_set = set(ALL_GUARDS)
    for name in names:
        if name not in all_set:
            raise ValueError(f"unknown guard: {name!r} (must be one of {ALL_GUARDS} or preset)")

    return names
