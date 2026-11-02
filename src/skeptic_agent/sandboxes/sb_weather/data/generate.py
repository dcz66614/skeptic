"""Generate the sb_weather forecast table once with the fixed seed (20261101).

The output, ``forecasts.json``, is committed; the server only reads it
(S9.1 item 3). Every value comes from one ``random.Random(SEED)`` draw in a
fixed order, so re-running this module rewrites the same bytes.

S9.2 fixes the shape: 12 real cities (the data is a fictional snapshot,
S9.1 item 8) over 14 days, 2026-11-01 to 2026-11-14. The first
``SOURCE_DAYS`` days also carry two independent model sources, so
``get_forecast_consensus`` can report a third view (S09). ``issued_at`` is
relative to the frozen instant at midnight, not to the wall clock.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_weather.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "forecasts.json"
"""Where the committed table lives."""

CITIES: dict[str, tuple[float, float]] = {
    "Paris": (15.0, 8.0),
    "Lyon": (16.0, 7.0),
    "Berlin": (13.0, 5.0),
    "Munich": (12.0, 3.0),
    "Tokyo": (21.0, 14.0),
    "Osaka": (22.0, 15.0),
    "Beijing": (17.0, 7.0),
    "Shanghai": (22.0, 16.0),
    "Hangzhou": (23.0, 16.0),
    "New York": (16.0, 9.0),
    "Boston": (14.0, 6.0),
    "Sydney": (25.0, 17.0),
}
"""The 12 cities (S9.2) and their (daytime, night-time) base, in Celsius."""

START_DAY = parse_instant("2026-11-01T00:00:00Z")
"""The first forecast day (S9.2)."""

DAYS = 14
"""S9.2: 14 days, 2026-11-01 to 2026-11-14."""

SOURCE_DAYS = 7
"""The first days carry both model sources, so the consensus is a third view."""

CONDITIONS = ("clear", "partly cloudy", "cloudy", "rain", "showers")
"""The condition vocabulary; ``summary`` is its sentence-cased form."""


def _issued(day_offset: int) -> str:
    """Return the issue time of a day's forecast.

    Args:
        day_offset: Days after ``2026-11-01``.

    Returns:
        The frozen day at 06:00 UTC, as the S9.1 ``...Z`` string.
    """
    return format_iso(START_DAY + timedelta(days=day_offset, hours=6))


def build_forecasts() -> dict[str, dict[str, dict[str, object]]]:
    """Build the forecast table deterministically.

    Returns:
        ``{city: {date: entry}}`` where ``date`` is ``YYYY-MM-DD`` and each
        entry has ``city``, ``date``, ``max_c``, ``min_c``, ``condition``,
        ``unit`` and ``issued_at``, plus ``source_a``/``source_b`` on the
        first ``SOURCE_DAYS`` days.
    """
    table: dict[str, dict[str, dict[str, object]]] = {}
    for city, (warm, cold) in CITIES.items():
        days: dict[str, dict[str, object]] = {}
        for offset in range(DAYS):
            day = START_DAY + timedelta(days=offset)
            date = day.strftime("%Y-%m-%d")
            drift = rng_choice(city, offset, -3.0, 3.0)
            max_c = round(warm + drift, 1)
            min_c = round(cold + drift * 0.6, 1)
            entry: dict[str, object] = {
                "city": city,
                "date": date,
                "max_c": max_c,
                "min_c": min_c,
                "condition": CONDITIONS[rng_index(city, offset, len(CONDITIONS))],
                "unit": "C",
                "issued_at": _issued(offset),
            }
            if offset < SOURCE_DAYS:
                entry["source_a"] = max_c
                entry["source_b"] = round(max_c + rng_delta(city, offset, -0.8, 0.8), 1)
            days[date] = entry
        table[city] = days
    return table


def _rng(city: str, offset: int) -> random.Random:
    """Return the per-(city, day) generator.

    Args:
        city: The city, part of the seed so the order of calls never matters.
        offset: The day offset from ``2026-11-01``.

    Returns:
        A generator seeded from ``SEED``, ``city`` and ``offset``.
    """
    return random.Random(f"{SEED}|{city}|{offset}")


def rng_choice(city: str, offset: int, low: float, high: float) -> float:
    """Draw the max-temperature drift of one day.

    Args:
        city: The city.
        offset: The day offset.
        low: The lowest drift, in Celsius.
        high: The highest drift, in Celsius.

    Returns:
        A value in ``[low, high]``.
    """
    return _rng(city, offset).uniform(low, high)


def rng_index(city: str, offset: int, count: int) -> int:
    """Draw the condition index of one day.

    Args:
        city: The city.
        offset: The day offset.
        count: The number of conditions.

    Returns:
        An index in ``range(count)``.
    """
    return _rng(city, offset + 100).randrange(count)


def rng_delta(city: str, offset: int, low: float, high: float) -> float:
    """Draw how far source B is from source A on one day.

    Args:
        city: The city.
        offset: The day offset.
        low: The lowest difference.
        high: The highest difference.

    Returns:
        A value in ``[low, high]``.
    """
    return _rng(city, offset + 200).uniform(low, high)


def write(path: Path = OUTPUT) -> None:
    """Write the table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_forecasts(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
