"""Generate sb_calendar's ``events.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the shape: about 60 events over the 14 days 2026-11-01 to 2026-11-14, each
with ``id``, ``title``, ``start``, ``end``, ``attendees`` and ``location``.
Every instant carries the ``+08:00`` offset (S9.2) and every attendee is a
fictional person from the shared customer table (S9.1 items 8 and 9).

The schedule leaves a gap after every meeting, so ``find_free_slot`` always
has somewhere to return. Every value comes from one ``random.Random(SEED)``
draw in a fixed order, so re-running this module rewrites the same bytes.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_calendar.data.generate
"""

import json
import random
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.data import load_customers

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "events.json"
"""Where the committed table lives."""

LOCAL = timezone(timedelta(hours=8))
"""The calendar's fixed ``+08:00`` offset (S9.2)."""

START_DAY = datetime(2026, 11, 1, 0, 0, 0, tzinfo=LOCAL)
"""The first calendar day (S9.2)."""

DAYS = 14
"""S9.2: 2026-11-01 to 2026-11-14."""

EVENT_COUNT = 60
"""S9.2: about 60 events."""

BUSY_DAYS = 4
"""The first four days hold five events; the rest hold four."""

EVENTS_PER_BUSY_DAY = 5
"""The count on the first ``BUSY_DAYS`` days."""

EVENTS_PER_DAY = 4
"""The count on every later day."""

FIRST_EVENT = 4001
"""The first event number; ids run E-4001 upwards."""

WORK_START = time(9, 0)
"""The first meeting starts at 09:00 local time."""

DURATIONS = (30, 60, 45, 90, 30)
"""The meeting lengths in minutes, cycled per slot."""

GAPS = (30, 15, 45, 30, 60)
"""The free gap after each meeting, cycled per slot."""

TITLES = (
    "Weekly planning",
    "Design review",
    "Customer sync",
    "Budget review",
    "Product stand-up",
    "Hiring panel",
    "Security review",
    "Retrospective",
    "Roadmap session",
    "Vendor call",
)
"""The fictional meeting titles."""

LOCATIONS = ("Room Orion", "Room Vega", "Room Atlas", "Room Lyra", "Remote")
"""The fictional meeting locations."""


def _stamp(value: datetime) -> str:
    """Format an instant the way S9.2 writes event times.

    Args:
        value: A timezone-aware local instant.

    Returns:
        ``YYYY-MM-DDTHH:MM:SS+08:00``.
    """
    return value.isoformat(timespec="seconds")


def build_events() -> dict[str, dict[str, object]]:
    """Build the calendar deterministically.

    Returns:
        ``{event_id: event}`` where each event has ``id``, ``title``,
        ``start``, ``end``, ``attendees`` and ``location``, in start order.
    """
    rng = random.Random(SEED)
    names = [str(customer["name"]) for customer in load_customers()]
    events: dict[str, dict[str, object]] = {}
    number = FIRST_EVENT
    for day_offset in range(DAYS):
        count = EVENTS_PER_BUSY_DAY if day_offset < BUSY_DAYS else EVENTS_PER_DAY
        day = START_DAY + timedelta(days=day_offset)
        cursor = day.replace(hour=WORK_START.hour, minute=WORK_START.minute)
        for slot in range(count):
            duration = DURATIONS[(day_offset + slot) % len(DURATIONS)]
            start = cursor
            end = start + timedelta(minutes=duration)
            event_id = f"E-{number}"
            attendees = list(dict.fromkeys(rng.sample(names, rng.randint(1, 3))))
            events[event_id] = {
                "id": event_id,
                "title": TITLES[rng.randrange(len(TITLES))],
                "start": _stamp(start),
                "end": _stamp(end),
                "attendees": attendees,
                "location": LOCATIONS[rng.randrange(len(LOCATIONS))],
            }
            number += 1
            cursor = end + timedelta(minutes=GAPS[(day_offset + slot) % len(GAPS)])
    return events


def write(path: Path = OUTPUT) -> None:
    """Write the event table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_events(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
