"""Integration tests: the sb_weather sandbox (S9.2, S31).

Every one of the four tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_weather`` starts over stdio,
both protocol generations can list and call the tools, and a state file is
written at startup (the sandbox is all-read, so there is no later write).
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

from skeptic_agent.sandboxes.sb_common.state import SandboxState
from skeptic_agent.sandboxes.sb_weather import TOOLS
from skeptic_agent.sandboxes.sb_weather import server as weather
from skeptic_agent.sandboxes.sb_weather.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"list_cities", "get_forecast", "get_forecast_v2", "get_forecast_consensus"}


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
    """Serve sb_weather over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_weather",
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


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run weather``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "weather"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``python -m`` (S9.1 item 2).

    Returns:
        How the client should launch the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.sandboxes.sb_weather"],
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
    return SandboxState({"forecasts": weather.load_forecasts()}, tmp_path / "state.json")


@pytest.mark.asyncio
async def test_list_cities_success(tmp_path: Path) -> None:
    """S9.2: the 12 cities, in the plan's order."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_cities", {})
    assert result.structured_content == {"cities": list(generate.CITIES)}


@pytest.mark.asyncio
async def test_get_forecast_misuse_rejects_a_null_date(tmp_path: Path) -> None:
    """A date argument is typed; ``null`` is refused instead of guessed."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_forecast_consensus", {"city": "Paris", "date": None})
    assert result.is_error
    assert "date" in _text(result)


@pytest.mark.asyncio
async def test_get_forecast_success(tmp_path: Path) -> None:
    """The primary tool returns the S9.2 forecast fields for one day."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_forecast", {"city": "Paris", "date": "2026-11-02"})
    structured = result.structured_content
    expected = generate.build_forecasts()["Paris"]["2026-11-02"]
    assert structured is not None
    assert set(structured) == {"city", "date", "max_c", "min_c", "condition", "unit", "issued_at"}
    assert structured["city"] == "Paris"
    assert structured["date"] == "2026-11-02"
    assert structured["max_c"] == expected["max_c"]
    assert structured["min_c"] == expected["min_c"]
    assert structured["condition"] == expected["condition"]
    assert structured["unit"] == "C"
    assert structured["issued_at"] == "2026-11-02T06:00:00Z"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"city": "Atlantis", "date": "2026-11-02"}, "unknown city"),
        ({"city": "Paris", "date": "2026-13-01"}, "invalid date"),
        ({"city": "Paris", "date": "2026-11-20"}, "no forecast"),
    ],
)
@pytest.mark.asyncio
async def test_get_forecast_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """An unknown city, a bad date and a day outside the table are business errors."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_forecast", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_forecast_v2_success(tmp_path: Path) -> None:
    """The alternate tool returns the same day under the v2 field names."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_forecast_v2", {"location": "Paris", "day": "2026-11-02"}
        )
    structured = result.structured_content
    expected = generate.build_forecasts()["Paris"]["2026-11-02"]
    assert structured is not None
    assert set(structured) == {"location", "day", "max_temp_c", "min_temp_c", "summary", "updated"}
    assert structured["location"] == "Paris"
    assert structured["day"] == "2026-11-02"
    assert structured["max_temp_c"] == expected["max_c"]
    assert structured["min_temp_c"] == expected["min_c"]
    assert structured["summary"] == "Partly cloudy"
    assert structured["updated"] == "2026-11-02T06:00:00Z"


@pytest.mark.asyncio
async def test_get_forecast_v2_misuse_unknown_location(tmp_path: Path) -> None:
    """The v2 tool reports an unknown location as a business error."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_forecast_v2", {"location": "Gotham", "day": "2026-11-02"}
        )
    assert result.is_error
    assert _text(result) == "Error: unknown city 'Gotham'; see list_cities"


@pytest.mark.asyncio
async def test_get_forecast_consensus_success(tmp_path: Path) -> None:
    """A two-source day reports the mean of both sources."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_forecast_consensus", {"city": "Paris", "date": "2026-11-02"}
        )
    structured = result.structured_content
    expected = generate.build_forecasts()["Paris"]["2026-11-02"]
    assert structured is not None
    assert set(structured) == {"city", "date", "max_c", "sources"}
    assert structured["max_c"] == round(
        (float(expected["max_c"]) + float(expected["source_b"])) / 2, 1
    )
    assert structured["sources"] == ["source_a", "source_b"]


@pytest.mark.asyncio
async def test_get_forecast_consensus_single_source_day(tmp_path: Path) -> None:
    """A later day has one model, so the consensus is that source alone."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_forecast_consensus", {"city": "Tokyo", "date": "2026-11-10"}
        )
    assert result.structured_content == {
        "city": "Tokyo",
        "date": "2026-11-10",
        "max_c": generate.build_forecasts()["Tokyo"]["2026-11-10"]["max_c"],
        "sources": ["source_a"],
    }


@pytest.mark.asyncio
async def test_get_forecast_consensus_misuse_missing_date(tmp_path: Path) -> None:
    """The consensus tool needs both arguments; one missing is an error result."""
    async with Client(weather.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_forecast_consensus", {"city": "Paris"})
    assert result.is_error
    assert "date" in _text(result)


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_read_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema and the read-only hints on every tool."""
    async with Client(weather.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
    assert tools["get_forecast"].output_schema is not None
    assert set(tools["get_forecast"].output_schema["required"]) == {
        "city",
        "date",
        "max_c",
        "min_c",
        "condition",
        "unit",
        "issued_at",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the four tools."""
    for mode in ("auto", "legacy"):
        async with Client(weather.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("list_cities", {})
            assert result.structured_content == {"cities": list(generate.CITIES)}


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the full table, stamped."""
    path = tmp_path / "state.json"
    weather.server(SandboxState({"forecasts": weather.load_forecasts()}, path))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert set(body["forecasts"]) == set(generate.CITIES)
    assert body["forecasts"]["Paris"]["2026-11-02"]["max_c"] == 14.5


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_weather`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_forecast", {"city": "Lyon", "date": "2026-11-02"})
        assert result.structured_content is not None
        assert result.structured_content["city"] == "Lyon"


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and writes the ``--state-file`` it was given."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("list_cities", {})
            assert result.structured_content == {"cities": list(generate.CITIES)}
    body = json.loads(path.read_text(encoding="utf-8"))
    assert set(body["forecasts"]) == set(generate.CITIES)


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run weather`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_forecast", {"city": "Paris", "date": "2026-11-02"})
        assert result.structured_content is not None
        assert result.structured_content["max_c"] == 14.5


def test_tool_specs_are_the_four_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools, all read-only."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert all(not spec.write for spec in TOOLS)
