"""The sb_calendar tools (S9.2): three read tools and two write tools.

``list_events``, ``get_event`` and ``find_free_slot`` read; ``create_event``
and ``delete_event`` write. The 60 events cover 2026-11-01 to 2026-11-14 and
use the fixed ``+08:00`` offset (S9.2). ``create_event`` fails with an
``isError`` result when the requested window overlaps an existing event.

``find_free_slot`` searches the requested day between ``earliest`` and
``latest`` (``HH:MM``, defaulting to 09:00 and 18:00) for the first gap long
enough for ``duration_min``. It returns ``start`` and ``end`` as full
``+08:00`` instants, or both as ``null`` when the day has no such gap.

The state is an ``events`` dict keyed by event id. A successful write calls
``tool.finish()``, so the state file follows it. The event field order is
``id, title, start, end, attendees, location`` (S9.2).
"""

import copy
from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_calendar"
"""The server name (S9.1 item 2)."""

EVENTS_FILE = Path(__file__).resolve().parent / "data" / "events.json"
"""The committed event table the server reads (S9.1 item 3)."""

LOCAL = timezone(timedelta(hours=8))
"""The calendar's fixed ``+08:00`` offset (S9.2)."""

FIRST_DAY = Date(2026, 11, 1)
"""The first day the calendar covers (S9.2)."""

LAST_DAY = Date(2026, 11, 14)
"""The last day the calendar covers (S9.2)."""

DEFAULT_EARLIEST = time(9, 0)
"""The default start of the search window."""

DEFAULT_LATEST = time(18, 0)
"""The default end of the search window."""

TITLE_LIMIT = 200
"""The longest event title ``create_event`` accepts."""


class DateArguments(BaseModel):
    """The arguments of ``list_events`` and ``find_free_slot``."""

    date: str = Field(description="The day, YYYY-MM-DD.")


class EventArguments(BaseModel):
    """The arguments of ``get_event`` and ``delete_event``."""

    event_id: str = Field(description="The event id, for example 'E-4001'.")


class FreeSlotArguments(DateArguments):
    """The arguments of ``find_free_slot``."""

    duration_min: int = Field(description="How many minutes the new meeting needs.")
    earliest: str | None = Field(
        default=None,
        description="The earliest local start time, HH:MM; defaults to 09:00.",
    )
    latest: str | None = Field(
        default=None,
        description="The latest local end time, HH:MM; defaults to 18:00.",
    )


class CreateArguments(BaseModel):
    """The arguments of ``create_event``."""

    title: str = Field(description="The event title, at most 200 characters.")
    start: str = Field(description="The start instant, with a +08:00 offset.")
    end: str = Field(description="The end instant, with a +08:00 offset.")
    attendees: list[str] = Field(description="The attendees' names.")


class Event(BaseModel):
    """One calendar event (S9.2 ``event`` fields)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    start: str
    end: str
    attendees: list[str]
    location: str


class Events(BaseModel):
    """The events on one day."""

    events: list[Event]


class FreeSlot(BaseModel):
    """The first free window of a day, if any."""

    date: str
    duration_min: int
    start: str | None
    end: str | None


class Created(BaseModel):
    """The result of ``create_event``."""

    status: Literal["ok"]
    event_id: str
    start: str
    end: str


class Deleted(BaseModel):
    """The result of ``delete_event``."""

    status: Literal["ok"]
    event_id: str


def load_events() -> dict[str, dict[str, Any]]:
    """Read the committed events as a fresh copy.

    Returns:
        ``{event_id: event}``, in file order.
    """
    table: dict[str, dict[str, Any]] = load_json(EVENTS_FILE)
    return copy.deepcopy(table)


def _events(tool: SandboxTool) -> dict[str, dict[str, Any]]:
    """Return the state's event table, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The ``{event_id: event}`` dict.
    """
    events: dict[str, dict[str, Any]] = tool.data["events"]
    return events


def _event(tool: SandboxTool, event_id: str) -> dict[str, Any]:
    """Look up one event.

    Args:
        tool: The bound tool.
        event_id: The client's event id.

    Returns:
        The event entry.

    Raises:
        ToolFailure: When the id is not in the calendar.
    """
    code = event_id.strip().upper()
    events = _events(tool)
    if code not in events:
        raise ToolFailure(f"unknown event {event_id!r}")
    return events[code]


def _day(value: str) -> Date:
    """Validate a day argument against the calendar window.

    Args:
        value: The client's day.

    Returns:
        The parsed day.

    Raises:
        ToolFailure: When the value is not an ISO date or is outside
            2026-11-01 to 2026-11-14.
    """
    try:
        day = Date.fromisoformat(value)
    except ValueError:
        raise ToolFailure(f"invalid date {value!r}, expected YYYY-MM-DD") from None
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ToolFailure(f"no calendar on {day}; the calendar covers {FIRST_DAY} to {LAST_DAY}")
    return day


def _instant(value: str, name: str) -> datetime:
    """Parse an event instant and normalise it to ``+08:00``.

    Args:
        value: The client's instant.
        name: The argument name, for the error text.

    Returns:
        The instant in the calendar's local offset.

    Raises:
        ToolFailure: When the value is not an ISO instant with an offset.
    """
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ToolFailure(f"invalid {name} {value!r}, expected an ISO instant") from None
    if moment.tzinfo is None:
        raise ToolFailure(f"invalid {name} {value!r}, expected a +08:00 offset")
    return moment.astimezone(LOCAL)


def _clock(value: str | None, name: str, default: time) -> time:
    """Parse an ``HH:MM`` search-window bound.

    Args:
        value: The client's value, or ``None`` for the default.
        name: The argument name, for the error text.
        default: The value to use when the client sends ``None``.

    Returns:
        The parsed local time.

    Raises:
        ToolFailure: When the value is not an ``HH:MM`` time.
    """
    if value is None:
        return default
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ToolFailure(f"invalid {name} {value!r}, expected HH:MM") from None


def _at(day: Date, moment: time) -> datetime:
    """Combine a day and a local time.

    Args:
        day: The calendar day.
        moment: The local time.

    Returns:
        The local instant.
    """
    return datetime.combine(day, moment, tzinfo=LOCAL)


def _start(entry: dict[str, Any]) -> datetime:
    """Return an event's normalised start.

    Args:
        entry: The event entry.

    Returns:
        The start in the calendar offset.
    """
    return datetime.fromisoformat(str(entry["start"])).astimezone(LOCAL)


def _end(entry: dict[str, Any]) -> datetime:
    """Return an event's normalised end.

    Args:
        entry: The event entry.

    Returns:
        The end in the calendar offset.
    """
    return datetime.fromisoformat(str(entry["end"])).astimezone(LOCAL)


def _on_day(tool: SandboxTool, day: Date) -> list[dict[str, Any]]:
    """Return the events that start on one day, earliest first.

    Args:
        tool: The bound tool.
        day: The calendar day.

    Returns:
        The matching events, ordered by start then id.
    """
    return [
        event
        for event in sorted(_events(tool).values(), key=lambda item: (item["start"], item["id"]))
        if _start(event).date() == day
    ]


def _overlaps(
    start: datetime,
    end: datetime,
    other_start: datetime,
    other_end: datetime,
) -> bool:
    """Tell whether two half-open windows overlap.

    Args:
        start: The first window's start.
        end: The first window's end.
        other_start: The second window's start.
        other_end: The second window's end.

    Returns:
        ``True`` when the windows share any instant.
    """
    return start < other_end and other_start < end


def _next_event_id(events: dict[str, dict[str, Any]]) -> str:
    """Return the next free event id.

    Args:
        events: The current events.

    Returns:
        ``E-<number>`` one past the highest existing event id.
    """
    numbers = [int(str(event["id"]).removeprefix("E-")) for event in events.values()]
    return f"E-{max(numbers) + 1}"


async def list_events(arguments: DateArguments, tool: SandboxTool) -> Events:
    """Return the events that start on one day.

    Args:
        arguments: The day.
        tool: The bound tool.

    Returns:
        The events, earliest first. An empty list is a valid answer.

    Raises:
        ToolFailure: On an invalid or out-of-window day.
    """
    day = _day(arguments.date)
    return Events(events=[Event.model_validate(event) for event in _on_day(tool, day)])


async def get_event(arguments: EventArguments, tool: SandboxTool) -> Event:
    """Return one event.

    Args:
        arguments: The event id.
        tool: The bound tool.

    Returns:
        The event.

    Raises:
        ToolFailure: On an unknown event id.
    """
    return Event.model_validate(_event(tool, arguments.event_id))


async def find_free_slot(arguments: FreeSlotArguments, tool: SandboxTool) -> FreeSlot:
    """Find the first free window of a day.

    Args:
        arguments: The day, duration and optional search bounds.
        tool: The bound tool.

    Returns:
        The first gap long enough, or ``start`` and ``end`` both ``None``.

    Raises:
        ToolFailure: On an invalid day, a non-positive duration, a malformed
            bound, or an empty search window.
    """
    day = _day(arguments.date)
    if arguments.duration_min <= 0:
        raise ToolFailure("duration_min must be greater than zero")
    earliest = _clock(arguments.earliest, "earliest", DEFAULT_EARLIEST)
    latest = _clock(arguments.latest, "latest", DEFAULT_LATEST)
    window_start = _at(day, earliest)
    window_end = _at(day, latest)
    if window_start >= window_end:
        raise ToolFailure("earliest must be before latest")
    duration = timedelta(minutes=arguments.duration_min)
    cursor = window_start
    for event in _on_day(tool, day):
        event_start = max(_start(event), window_start)
        event_end = min(_end(event), window_end)
        if event_end <= cursor:
            continue
        if event_start - cursor >= duration:
            return FreeSlot(
                date=day.isoformat(),
                duration_min=arguments.duration_min,
                start=cursor.isoformat(timespec="seconds"),
                end=(cursor + duration).isoformat(timespec="seconds"),
            )
        cursor = max(cursor, event_end)
    if window_end - cursor >= duration:
        return FreeSlot(
            date=day.isoformat(),
            duration_min=arguments.duration_min,
            start=cursor.isoformat(timespec="seconds"),
            end=(cursor + duration).isoformat(timespec="seconds"),
        )
    return FreeSlot(date=day.isoformat(), duration_min=arguments.duration_min, start=None, end=None)


async def create_event(arguments: CreateArguments, tool: SandboxTool) -> Created:
    """Create an event when its window is free.

    Args:
        arguments: The title, start, end and attendees.
        tool: The bound tool.

    Returns:
        ``status``, the new ``event_id`` and the stored ``start``/``end``.

    Raises:
        ToolFailure: On an empty or oversized title, a malformed or reversed
            window, a window outside the calendar, an empty attendee name, or
            an overlap with an existing event; the state is then unchanged.
    """
    title = arguments.title.strip()
    if not title:
        raise ToolFailure("title must not be empty")
    if len(title) > TITLE_LIMIT:
        raise ToolFailure(f"title is longer than {TITLE_LIMIT} characters")
    start = _instant(arguments.start, "start")
    end = _instant(arguments.end, "end")
    if start >= end:
        raise ToolFailure("start must be before end")
    for name, moment in (("start", start), ("end", end)):
        if not FIRST_DAY <= moment.date() <= LAST_DAY:
            raise ToolFailure(f"{name} {moment.date()} is outside the calendar")
    attendees = [attendee.strip() for attendee in arguments.attendees]
    if any(not attendee for attendee in attendees):
        raise ToolFailure("attendee names must not be empty")
    events = _events(tool)
    for event in events.values():
        if _overlaps(start, end, _start(event), _end(event)):
            raise ToolFailure(f"time window conflicts with event {event['id']}")
    event_id = _next_event_id(events)
    events[event_id] = {
        "id": event_id,
        "title": title,
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
        "attendees": attendees,
        "location": "Remote",
    }
    tool.finish()
    return Created(
        status="ok",
        event_id=event_id,
        start=str(events[event_id]["start"]),
        end=str(events[event_id]["end"]),
    )


async def delete_event(arguments: EventArguments, tool: SandboxTool) -> Deleted:
    """Delete an event.

    Args:
        arguments: The event id.
        tool: The bound tool.

    Returns:
        ``status`` and the deleted ``event_id``.

    Raises:
        ToolFailure: On an unknown event id; the state is then unchanged.
    """
    event = _event(tool, arguments.event_id)
    event_id = str(event["id"])
    del _events(tool)[event_id]
    tool.finish()
    return Deleted(status="ok", event_id=event_id)


TOOLS = (
    ToolSpec(
        "list_events",
        "Return the events that start on one day, earliest first.",
        DateArguments,
        Events,
        list_events,
    ),
    ToolSpec(
        "get_event",
        "Return one event with its title, times, attendees and location.",
        EventArguments,
        Event,
        get_event,
    ),
    ToolSpec(
        "find_free_slot",
        "Find the first free window of a day for a given duration.",
        FreeSlotArguments,
        FreeSlot,
        find_free_slot,
    ),
    ToolSpec(
        "create_event",
        "Create an event in a free window (not idempotent).",
        CreateArguments,
        Created,
        create_event,
        write=True,
        destructive=False,
        idempotent=False,
    ),
    ToolSpec(
        "delete_event",
        "Delete an event (not idempotent).",
        EventArguments,
        Deleted,
        delete_event,
        write=True,
        destructive=True,
        idempotent=False,
    ),
)
"""The five S9.2 tools: three read, two write."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed events.

    Returns:
        A state whose ``events`` key holds the table; the file comes from
        ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"events": load_events()})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_calendar server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_calendar (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
