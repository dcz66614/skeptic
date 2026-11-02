"""The frozen clock every sandbox reads instead of the wall clock (S9.1).

Time is the single source of "now". A sandbox must never call
``datetime.now`` itself: scenarios pin ``frozen_now`` and the oracle replays
tool calls later, so the same call must return the same timestamps. The value
comes from ``SKEPTIC_FROZEN_NOW`` and defaults to the S9.1 instant.
"""

import os
from datetime import UTC, datetime

FROZEN_NOW_ENV = "SKEPTIC_FROZEN_NOW"
"""The environment variable holding the frozen instant (S9.1)."""

DEFAULT_FROZEN_NOW = "2026-11-01T09:00:00Z"
"""The default frozen instant (S9.1)."""


def parse_instant(value: str) -> datetime:
    """Parse an ISO 8601 instant and normalise it to UTC.

    A trailing ``Z`` is accepted because every instant in the plan is written
    that way. A value without an offset is read as UTC rather than local time,
    so the result never depends on the machine's time zone.

    Args:
        value: The instant, for example ``2026-11-01T09:00:00Z``.

    Returns:
        A timezone-aware UTC ``datetime``.

    Raises:
        ValueError: When ``value`` is not an ISO 8601 instant.
    """
    text = value.strip().replace("z", "Z").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def now() -> datetime:
    """Return the frozen instant, as configured when this module loaded.

    The environment is read once at import time so that every sandbox in one
    process agrees on "now" even if the variable changes afterwards.

    Returns:
        The frozen instant in UTC.
    """
    return _FROZEN_NOW


def now_iso() -> str:
    """Return the frozen instant in the S9.1 wire form.

    Returns:
        ``YYYY-MM-DDTHH:MM:SSZ``, for example ``2026-11-01T09:00:00Z``.
    """
    return format_iso(_FROZEN_NOW)


def format_iso(value: datetime) -> str:
    """Format an instant the way every sandbox writes it.

    Args:
        value: A timezone-aware instant.

    Returns:
        ``YYYY-MM-DDTHH:MM:SSZ`` with whole seconds, in UTC.
    """
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_CONFIGURED_NOW = os.environ.get(FROZEN_NOW_ENV) or DEFAULT_FROZEN_NOW
_FROZEN_NOW = parse_instant(_CONFIGURED_NOW)
