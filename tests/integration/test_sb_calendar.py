"""Integration tests: the sb_calendar sandbox (S9.2, S33).

Every one of the five tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_calendar`` starts over stdio,
both protocol generations can list and call the tools, ``skeptic sandbox run
calendar`` starts the same server, and the state file follows each write
(S9.1 item 4).
"""

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters

from skeptic_agent.sandboxes.sb_calendar import TOOLS
from skeptic_agent.sandboxes.sb_calendar import server as calendar
from skeptic_agent.sandboxes.sb_calendar.data import generate
from skeptic_agent.sandboxes.sb_common.state import SandboxState

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"list_events", "get_event", "find_free_slot", "create_event", "delete_event"}
READ_TOOLS = {"list_events", "get_event", "find_free_slot"}
WRITE_TOOLS = {"create_event", "delete_event"}


def _text(result: Any) -> str:
    """Return the first text block of a tool result.

    Args:
        result: The ``CallToolResult``.

    Returns:
        The block's text.
    """
    return str(result.content[0].text)


def _pythonpath() -> str:
    """Return a ``PYTHONPATH`` that finds the package source.

    Returns:
        ``src`` plus the existing ``PYTHONPATH``, joined.
    """
    parts = [str(ROOT / "src")]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _free_port() -> int:
    """Return a currently free TCP port.

    Returns:
        A port the OS just handed out.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen[bytes]) -> None:
    """Wait until a local port accepts connections.

    Args:
        port: The port to poll.
        process: The child that must stay alive.

    Raises:
        RuntimeError: When the port does not open or the child exits first.
    """
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("the sandbox exited before it listened")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"port {port} did not open")


@contextlib.contextmanager
def _served_http(state_file: Path):
    """Serve sb_calendar over Streamable HTTP on a free port.

    Args:
        state_file: The state file the child writes.

    Yields:
        The ``http://127.0.0.1:<port>/mcp`` URL.
    """
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "skeptic_agent.sandboxes.sb_calendar",
            "--http",
            f"127.0.0.1:{port}",
            "--state-file",
            str(state_file),
        ],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port, process)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=TIMEOUT_SECONDS)


def _stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``python -m`` (S9.1 item 2).

    Returns:
        How the client should launch the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.sandboxes.sb_calendar"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run calendar``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "calendar"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _state(tmp_path: Path) -> SandboxState:
    """Return a fresh state writing into a test's temp directory.

    Args:
        tmp_path: The pytest temp directory.

    Returns:
        The sandbox state.
    """
    fresh = calendar.build_state()
    return SandboxState(fresh.data, tmp_path / "state.json")


def _read_state(path: Path) -> dict[str, Any]:
    """Read the state file as JSON.

    Args:
        path: The state file.

    Returns:
        The decoded state.
    """
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return body


def _free_slot_arguments() -> dict[str, Any]:
    """Return a create request inside the known free window of 2026-11-01."""
    return {
        "title": "Vendor review",
        "start": "2026-11-01T15:15:00+08:00",
        "end": "2026-11-01T16:15:00+08:00",
        "attendees": ["Ada Castillo"],
    }


@pytest.mark.asyncio
async def test_list_events_success(tmp_path: Path) -> None:
    """The day's events come back with the S9.2 fields, earliest first."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_events", {"date": "2026-11-01"})
    structured = result.structured_content
    assert structured is not None
    events = structured["events"]
    assert len(events) == 5
    assert events[0]["id"] == "E-4001"
    assert events[0]["start"] == "2026-11-01T09:00:00+08:00"
    assert events[0]["end"] == "2026-11-01T09:30:00+08:00"
    assert events[0]["attendees"] == ["Farid Petrov", "Hiro Kowalski"]
    assert events[0]["location"] == "Room Orion"
    assert [event["start"] for event in events] == sorted(event["start"] for event in events)
    for event in events:
        assert set(event) == {"id", "title", "start", "end", "attendees", "location"}
        assert event["start"].endswith("+08:00")
        assert event["end"].endswith("+08:00")


@pytest.mark.parametrize(
    ("date", "reason"),
    [
        ("2026-13-01", "invalid date"),
        ("2026-12-01", "no calendar"),
    ],
)
@pytest.mark.asyncio
async def test_list_events_misuse(tmp_path: Path, date: str, reason: str) -> None:
    """A malformed date and a day outside the window are business errors."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_events", {"date": date})
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_event_success(tmp_path: Path) -> None:
    """The event returns the committed title, times and attendees."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_event", {"event_id": "E-4001"})
    structured = result.structured_content
    assert structured is not None
    assert structured["id"] == "E-4001"
    assert structured["title"] == "Weekly planning"
    assert structured["location"] == "Room Orion"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_get_event_misuse_unknown_event(tmp_path: Path) -> None:
    """An unknown event id is a business error."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_event", {"event_id": "E-9999"})
    assert result.is_error
    assert "unknown event" in _text(result)


@pytest.mark.asyncio
async def test_find_free_slot_success(tmp_path: Path) -> None:
    """The first 60-minute gap after the last event is returned."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "find_free_slot", {"date": "2026-11-01", "duration_min": 60}
        )
    assert result.structured_content == {
        "date": "2026-11-01",
        "duration_min": 60,
        "start": "2026-11-01T15:15:00+08:00",
        "end": "2026-11-01T16:15:00+08:00",
    }


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"date": "2026-11-01", "duration_min": 0}, "greater than zero"),
        ({"date": "2026-12-01", "duration_min": 30}, "no calendar"),
        (
            {"date": "2026-11-01", "duration_min": 30, "earliest": "17:00", "latest": "10:00"},
            "earliest must be before latest",
        ),
        ({"date": "2026-11-01", "duration_min": 30, "earliest": "nine"}, "invalid earliest"),
    ],
)
@pytest.mark.asyncio
async def test_find_free_slot_misuse(
    tmp_path: Path, arguments: dict[str, Any], reason: str
) -> None:
    """A bad duration, day or search window is a business error."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("find_free_slot", arguments)
    assert result.is_error
    assert reason in _text(result)


@pytest.mark.asyncio
async def test_create_event_success_and_state(tmp_path: Path) -> None:
    """A free window is accepted and the state file gets the new event."""
    path = tmp_path / "state.json"
    state = calendar.build_state()
    state.state_file = path
    async with Client(calendar.server(state)) as client:
        result = await client.call_tool("create_event", _free_slot_arguments())
    assert result.structured_content == {
        "status": "ok",
        "event_id": "E-4061",
        "start": "2026-11-01T15:15:00+08:00",
        "end": "2026-11-01T16:15:00+08:00",
    }
    body = _read_state(path)
    assert body["events"]["E-4061"]["title"] == "Vendor review"
    assert body["events"]["E-4061"]["location"] == "Remote"
    assert body["events"]["E-4061"]["attendees"] == ["Ada Castillo"]


@pytest.mark.asyncio
async def test_create_event_misuse_conflict(tmp_path: Path) -> None:
    """A window overlapping an existing event is a business error."""
    arguments = {
        "title": "Another planning",
        "start": "2026-11-01T09:00:00+08:00",
        "end": "2026-11-01T09:15:00+08:00",
        "attendees": ["Ada Castillo"],
    }
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("create_event", arguments)
    assert result.is_error
    assert "conflicts with event E-4001" in _text(result)


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        (
            {
                "title": "  ",
                "start": "2026-11-01T15:15:00+08:00",
                "end": "2026-11-01T16:15:00+08:00",
                "attendees": ["Ada Castillo"],
            },
            "title must not be empty",
        ),
        (
            {
                "title": "Reversed",
                "start": "2026-11-01T16:15:00+08:00",
                "end": "2026-11-01T15:15:00+08:00",
                "attendees": ["Ada Castillo"],
            },
            "start must be before end",
        ),
        (
            {
                "title": "Outside",
                "start": "2026-12-01T09:00:00+08:00",
                "end": "2026-12-01T10:00:00+08:00",
                "attendees": ["Ada Castillo"],
            },
            "outside the calendar",
        ),
        (
            {
                "title": "Blank attendee",
                "start": "2026-11-01T15:15:00+08:00",
                "end": "2026-11-01T16:15:00+08:00",
                "attendees": ["  "],
            },
            "attendee names must not be empty",
        ),
    ],
)
@pytest.mark.asyncio
async def test_create_event_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An empty title, a reversed/outside window and a blank attendee fail."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("create_event", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_delete_event_success_and_state(tmp_path: Path) -> None:
    """Deleting an event removes it and the state file follows."""
    path = tmp_path / "state.json"
    state = calendar.build_state()
    state.state_file = path
    async with Client(calendar.server(state)) as client:
        result = await client.call_tool("delete_event", {"event_id": "E-4001"})
    assert result.structured_content == {"status": "ok", "event_id": "E-4001"}
    body = _read_state(path)
    assert "E-4001" not in body["events"]
    assert len(body["events"]) == 59


@pytest.mark.asyncio
async def test_delete_event_misuse_unknown_event(tmp_path: Path) -> None:
    """An unknown event id is a business error."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        result = await client.call_tool("delete_event", {"event_id": "E-9999"})
    assert result.is_error
    assert "unknown event" in _text(result)


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and the right read/write hints."""
    async with Client(calendar.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for name, tool in tools.items():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        if name in READ_TOOLS:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.idempotent_hint is True
        else:
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.idempotent_hint is False
    assert tools["create_event"].annotations is not None
    assert tools["create_event"].annotations.destructive_hint is False
    assert tools["delete_event"].annotations is not None
    assert tools["delete_event"].annotations.destructive_hint is True
    assert tools["get_event"].output_schema is not None
    assert set(tools["get_event"].output_schema["required"]) == {
        "id",
        "title",
        "start",
        "end",
        "attendees",
        "location",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the five tools."""
    for mode in ("auto", "legacy"):
        async with Client(calendar.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("get_event", {"event_id": "E-4002"})
            assert result.structured_content is not None
            assert result.structured_content["id"] == "E-4002"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the full calendar, stamped."""
    path = tmp_path / "state.json"
    state = calendar.build_state()
    state.state_file = path
    calendar.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["events"]) == 60
    assert body["events"]["E-4001"]["id"] == "E-4001"


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_calendar`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_event", {"event_id": "E-4001"})
        assert result.structured_content is not None
        assert result.structured_content["title"] == "Weekly planning"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run calendar`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("list_events", {"date": "2026-11-01"})
        assert result.structured_content is not None
        assert len(result.structured_content["events"]) == 5


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and the state file follows a write."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("create_event", _free_slot_arguments())
            assert result.structured_content is not None
    body = _read_state(path)
    assert body["events"]["E-4061"]["title"] == "Vendor review"


def test_tool_specs_are_the_five_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools with the right write flags."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert {spec.name for spec in TOOLS if spec.write} == WRITE_TOOLS
    assert generate.EVENT_COUNT == 60
    assert generate.DAYS == 14
