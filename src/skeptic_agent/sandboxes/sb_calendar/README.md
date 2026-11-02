# sb_calendar

A deterministic MCP sandbox over 60 fictional calendar events from
2026-11-01 to 2026-11-14, used by Skeptic scenarios whose ids start with
`calendar.` (S9.2, S33).

> All people, meeting titles and locations are fictional snapshot data. Every
> event time carries the fixed `+08:00` offset (S9.2).

## Tools

Three read tools, two write tools.

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `list_events` | R | `date` | `events[]` of `id, title, start, end, attendees[], location` |
| `get_event` | R | `event_id` | `id, title, start, end, attendees[], location` |
| `find_free_slot` | R | `date`, `duration_min`, `earliest?`, `latest?` | `date, duration_min, start, end` |
| `create_event` | W | `title`, `start`, `end`, `attendees` | `status ("ok"), event_id, start, end` |
| `delete_event` | W | `event_id` | `status ("ok"), event_id` |

- `start` and `end` are ISO instants with a `+08:00` offset, for example
  `2026-11-01T09:00:00+08:00`.
- `list_events` returns the events that start on the given day, earliest
  first. A day with no event is an empty `events` list, not an error.
- `find_free_slot` searches the day between `earliest` and `latest` (`HH:MM`,
  defaulting to `09:00` and `18:00`) and returns the first gap of at least
  `duration_min` minutes. `start` and `end` are both `null` when the window
  has no such gap.
- `create_event` requires a non-empty title, a start before the end, both
  instants inside the 14-day window, and a window that overlaps no existing
  event. New events get the next id (`E-4061`, ...) and the location
  `"Remote"`, because S9.2's signature has no location argument.
- `delete_event` removes the event. The state is an `events` dict keyed by
  id; both write tools update the state file after they succeed.

## Example calls

```json
{"name": "list_events", "arguments": {"date": "2026-11-01"}}
```

```json
{"events": [{"id": "E-4001", "title": "Weekly planning",
  "start": "2026-11-01T09:00:00+08:00", "end": "2026-11-01T09:30:00+08:00",
  "attendees": ["Farid Petrov", "Hiro Kowalski"], "location": "Room Orion"}]}
```

```json
{"name": "find_free_slot", "arguments": {"date": "2026-11-01", "duration_min": 60}}
```

```json
{"date": "2026-11-01", "duration_min": 60,
 "start": "2026-11-01T15:15:00+08:00", "end": "2026-11-01T16:15:00+08:00"}
```

```json
{"name": "create_event", "arguments": {"title": "Vendor review",
 "start": "2026-11-01T15:15:00+08:00", "end": "2026-11-01T16:15:00+08:00",
 "attendees": ["Ada Castillo"]}}
```

```json
{"status": "ok", "event_id": "E-4061",
 "start": "2026-11-01T15:15:00+08:00", "end": "2026-11-01T16:15:00+08:00"}
```

## Errors

An invalid or out-of-window date, an unknown event id, a non-positive
duration, a malformed search bound, an empty or oversized title, a malformed
or reversed event window, an empty attendee name, and a window that overlaps
an existing event return an `isError` result reading `Error: <reason>`. A
failed write leaves the state unchanged.

## Running

```text
python -m skeptic_agent.sandboxes.sb_calendar
python -m skeptic_agent.sandboxes.sb_calendar --http 127.0.0.1:8771
python -m skeptic_agent.sandboxes.sb_calendar --state-file state.json
```

The events come from `data/events.json`, generated once with seed `20261101`
by `data/generate.py` and committed; the server only reads it. The attendees
are fictional names from the shared customer table.
