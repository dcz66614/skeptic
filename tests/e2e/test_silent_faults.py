"""End-to-end tests: silent faults S01-S10 through the stdio proxy (F22, F23).

Each test starts the real ``tests/fixtures/echo_server.py`` as the proxy's
upstream child, schedules one fault on a ``FaultEngine``, and drives the proxy
over a scripted stdin/stdout. The echo fixture has one required string argument,
so ``S05`` can swap the entity it echoes and every other fault has data to
rewrite. Results are checked as the client sees them, after JSON serialization.

S10 runs against ``tests/fixtures/counting_echo_server.py``, which writes one
line per upstream tool call to a log file; the S10 tests read that log to prove
the phantom write never reached the server.
"""

import asyncio
import json
import os
import sys
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.proxy.pipeline import new_pipeline
from skeptic_agent.proxy.stdio import StdioProxy

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
COUNTING_ECHO_SERVER = ROOT / "tests" / "fixtures" / "counting_echo_server.py"
TIMEOUT_SECONDS = 60

SCENARIO: dict[str, Any] = {
    "id": "echo.echo.basic.001",
    "fault_targets": {"primary": ["echo"], "entity_arg": "text"},
    "decoys": {"entity": "decoy"},
    "tool_defs": {
        "echo": {
            "name": "echo",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    },
}


def _pythonpath() -> str:
    """Return a PYTHONPATH that also finds the package source.

    Returns:
        ``src``, the fixtures dir and the existing ``PYTHONPATH``, joined.
    """
    parts = [str(ROOT / "src"), str(ECHO_SERVER.parent)]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _spec(fault_id: str, **params: Any) -> FaultSpec:
    """Build a permanent fault spec on the ``echo`` tool.

    Args:
        fault_id: The S6 fault id.
        params: The fault parameters.

    Returns:
        The scheduled fault.
    """
    return FaultSpec(
        fault_id=fault_id,
        tool="$primary",
        call_index="all",
        probability=1.0,
        persistence="permanent",
        params=params or None,
    )


def _engine(fault_id: str, **params: Any) -> FaultEngine:
    """Build an engine with one scheduled fault on the echo tool.

    Args:
        fault_id: The S6 fault id.
        params: The fault parameters.

    Returns:
        The engine.
    """
    return FaultEngine([_spec(fault_id, **params)], scenario=SCENARIO)


def _line(message: dict[str, Any]) -> bytes:
    """Encode one JSON-RPC message as a line.

    Args:
        message: The message object.

    Returns:
        The UTF-8 line, including its newline.
    """
    return (json.dumps(message) + "\n").encode()


HANDSHAKE = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "e2e", "version": "1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
]


class Session:
    """One proxy run driven from a list of client messages.

    Attributes:
        lines: The response lines the proxy wrote, as they arrived.
        engine: The fault engine to mount.
    """

    def __init__(
        self,
        messages: list[dict[str, Any]],
        engine: FaultEngine,
        scenario: dict[str, Any] | None = None,
        call_log: Path | None = None,
        server: Path | None = None,
    ) -> None:
        """Queue the client messages.

        Args:
            messages: The messages the client sends, in order.
            engine: The fault engine to mount.
            scenario: The scenario the episode runs, ``SCENARIO`` by default.
            call_log: A file to record upstream calls in, or ``None`` for the
                plain echo server.
            server: The upstream script, ``ECHO_SERVER`` by default.
        """
        self.server = ECHO_SERVER if server is None else server
        self.messages = messages
        self.engine = engine
        self.scenario = SCENARIO if scenario is None else scenario
        self.call_log = call_log
        self.lines: list[bytes] = []
        self.scripted = _ScriptedIn()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        """Run the proxy in a thread with this session's streams."""
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(sys, "stdin", self.scripted)
            patch.setattr(sys, "stdout", _CapturedOut(self.lines))
            if self.call_log is None:
                command = [sys.executable, str(self.server)]
            else:
                command = [sys.executable, str(COUNTING_ECHO_SERVER), "--calls", str(self.call_log)]
            proxy = StdioProxy(
                command,
                new_pipeline(fault=self.engine),
                episode_id="run:echo.echo.basic.001:S:1",
                seed=1,
            )
            proxy.ctx.scenario = self.scenario
            asyncio.run(proxy.run())

    def start(self) -> None:
        """Start the proxy thread and write every client message."""
        self._thread.start()
        self.scripted.feed(b"".join(_line(message) for message in self.messages))

    async def wait_for_id(self, message_id: int | str) -> dict[str, Any]:
        """Wait until the proxy has written a response with this id.

        Args:
            message_id: The response id.

        Returns:
            The decoded response.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + TIMEOUT_SECONDS
        while loop.time() < deadline:
            for line in self.lines:
                text = line.decode()
                if f'"id":{json.dumps(message_id)}' in text:
                    return json.loads(text)
            await asyncio.sleep(0.01)
        raise AssertionError(f"no response for id {message_id!r}: {self.lines!r}")

    async def finish(self) -> list[dict[str, Any]]:
        """Close the client input and wait for the proxy to exit.

        Returns:
            Every decoded response the client saw.
        """
        self.scripted.close()
        await asyncio.to_thread(self._thread.join, TIMEOUT_SECONDS)
        assert not self._thread.is_alive(), "the proxy did not exit"
        return [json.loads(line) for line in self.lines]


class _ScriptedIn:
    """A binary stdin fed through an OS pipe."""

    def __init__(self) -> None:
        """Open the pipe."""
        self._read, self._write = os.pipe()
        self.buffer = self
        self._pending = b""

    def feed(self, data: bytes) -> None:
        """Write bytes the proxy will read as client input.

        Args:
            data: The bytes to feed.
        """
        with suppress(OSError):
            os.write(self._write, data)

    def readline(self) -> bytes:
        """Return exactly one line, buffering whatever else arrived with it.

        Returns:
            One line including its newline, or ``b""`` at EOF.
        """
        while b"\n" not in self._pending:
            chunk = os.read(self._read, 4096)
            if not chunk:
                break
            self._pending += chunk
        if b"\n" not in self._pending:
            line, self._pending = self._pending, b""
            return line
        end = self._pending.index(b"\n") + 1
        line, self._pending = self._pending[:end], self._pending[end:]
        return line

    def close(self) -> None:
        """Close the write end so the proxy sees EOF after the queued lines."""
        with suppress(OSError):
            os.close(self._write)


class _CapturedOut:
    """A binary stdout that keeps every byte written."""

    def __init__(self, lines: list[bytes]) -> None:
        """Wrap the sink.

        Args:
            lines: Where written bytes are appended.
        """
        self.buffer = _Buffer(lines)


class _Buffer:
    """The byte sink behind ``_CapturedOut``."""

    def __init__(self, lines: list[bytes]) -> None:
        """Record the list to append to.

        Args:
            lines: Where written bytes are appended.
        """
        self.lines = lines
        self._partial = b""

    def write(self, data: bytes) -> None:
        """Append bytes, one entry per complete line.

        Args:
            data: The bytes written.
        """
        self._partial += data
        while b"\n" in self._partial:
            end = self._partial.index(b"\n") + 1
            line, self._partial = self._partial[:end], self._partial[end:]
            self.lines.append(line)

    def flush(self) -> None:
        """Flush nothing; the sink is memory."""


async def _run(
    engine: FaultEngine,
    *messages: dict[str, Any],
    wait_ids: bool = True,
    scenario: dict[str, Any] | None = None,
    call_log: Path | None = None,
    server: Path | None = None,
) -> list[dict[str, Any]]:
    """Run one proxy session to completion and return what the client saw.

    Args:
        engine: The fault engine to mount.
        messages: The client messages.
        wait_ids: Whether to wait for every message id before closing stdin.
        scenario: The scenario the episode runs, ``SCENARIO`` by default.
        call_log: A file to record upstream calls in, or ``None`` for the
            plain echo server.
        server: The upstream script, ``ECHO_SERVER`` by default.

    Returns:
        The decoded response lines.
    """
    session = Session(list(messages), engine, scenario, call_log, server)
    session.start()
    if wait_ids:
        for message in messages:
            if "id" in message:
                await session.wait_for_id(message["id"])
    return await session.finish()


async def _call(
    engine: FaultEngine,
    *messages: dict[str, Any],
    scenario: dict[str, Any] | None = None,
    call_log: Path | None = None,
    server: Path | None = None,
) -> list[dict[str, Any]]:
    """Run a handshake plus the given client messages.

    Args:
        engine: The fault engine to mount.
        messages: The extra client messages, after the handshake.
        scenario: The scenario the episode runs, ``SCENARIO`` by default.
        call_log: A file to record upstream calls in, or ``None`` for the
            plain echo server.
        server: The upstream script, ``ECHO_SERVER`` by default.

    Returns:
        The decoded response lines.
    """
    return await _run(
        engine, *HANDSHAKE, *messages, scenario=scenario, call_log=call_log, server=server
    )


def _by_id(responses: list[dict[str, Any]], message_id: int | str) -> dict[str, Any]:
    """Return the response carrying an id.

    Args:
        responses: The decoded responses, in arrival order.
        message_id: The id to look for.

    Returns:
        The matching response.
    """
    for response in responses:
        if response.get("id") == message_id:
            return response
    raise AssertionError(f"no response for id {message_id!r}: {responses!r}")


def _text(response: dict[str, Any]) -> str:
    """Return the text of the first content block of a tool result.

    Args:
        response: The tool-call response.

    Returns:
        The text block's text.
    """
    return response["result"]["content"][0]["text"]


def _call_message(message_id: int, text: str = "hello") -> dict[str, Any]:
    """Build a ``tools/call`` for ``echo``.

    Args:
        message_id: The request id.
        text: The text to echo.

    Returns:
        The request object.
    """
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": text}},
    }


@pytest.mark.asyncio
async def test_s01_empties_the_text() -> None:
    """S01 answers an echo call with an empty string and keeps it a success."""
    responses = await _call(_engine("S01"), _call_message(2, "hello"))
    reply = _by_id(responses, 2)
    assert reply["result"] == {"content": [{"type": "text", "text": ""}], "isError": False}


@pytest.mark.asyncio
async def test_s02_truncates_the_text() -> None:
    """S02 keeps the leading ``floor(len * ratio)`` characters of the echo."""
    responses = await _call(_engine("S02"), _call_message(2, "abcdefghij"))
    reply = _by_id(responses, 2)
    assert _text(reply) == "abc"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_s03_moves_a_date_back() -> None:
    """S03 shifts a date inside the echoed text."""
    responses = await _call(_engine("S03", days=1), _call_message(2, "call me on 2026-11-02"))
    reply = _by_id(responses, 2)
    assert _text(reply) == "call me on 2026-11-01"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_s04_scales_the_first_number() -> None:
    """S04 multiplies the first number of the echoed text by ``factor``."""
    responses = await _call(_engine("S04", factor=10), _call_message(2, "temp 14.5 C"))
    reply = _by_id(responses, 2)
    assert _text(reply) == "temp 145.0 C"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_s04_default_factor() -> None:
    """The default ``factor`` is 10."""
    responses = await _call(_engine("S04"), _call_message(2, "3 items"))
    assert _text(_by_id(responses, 2)) == "30 items"


@pytest.mark.asyncio
async def test_s05_swaps_the_entity_before_upstream() -> None:
    """S05 replaces the argument, so the echo returns the decoy, not the request."""
    responses = await _call(_engine("S05"), _call_message(2, "Paris"))
    reply = _by_id(responses, 2)
    assert _text(reply) == "decoy"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_s05_does_not_touch_the_response() -> None:
    """The response bytes S05 leaves behind are the upstream's own result."""
    responses = await _call(_engine("S05"), _call_message(2, "2026-11-02"))
    reply = _by_id(responses, 2)
    assert reply["result"] == {
        "content": [{"type": "text", "text": "decoy"}],
        "isError": False,
    }


@pytest.mark.asyncio
async def test_silent_faults_can_run_in_sequence() -> None:
    """Two permanent silent faults fire on both calls without breaking the session."""
    engine = FaultEngine([_spec("S02"), _spec("S04")], scenario=SCENARIO)
    responses = await _call(engine, _call_message(2, "abcdefghij"), _call_message(3, "abcdefghij"))
    assert _text(_by_id(responses, 2)) == "abc"


@pytest.mark.asyncio
async def test_not_applicable_s05_leaves_the_call_alone() -> None:
    """Without the scenario fields S05 is not applicable and the echo is clean."""
    scenario = {"fault_targets": {"primary": ["echo"]}}
    engine = FaultEngine([_spec("S05")], scenario=scenario)
    responses = await _call(engine, _call_message(2, "Paris"), scenario=scenario)
    assert _text(_by_id(responses, 2)) == "Paris"


WRITE_SCENARIO: dict[str, Any] = {
    "id": "orders.place-order.001",
    "fault_targets": {"primary": ["place_order"], "write_tools": ["place_order"]},
    "tool_defs": {
        "place_order": {
            "name": "place_order",
            "inputSchema": {
                "type": "object",
                "properties": {"item": {"type": "string"}},
                "required": ["item"],
            },
        }
    },
}
"""A write scenario for S10, whose target is ``$write``."""


def _read_log(path: Path) -> list[str]:
    """Return the tool names the upstream recorded, in order.

    Args:
        path: The call log file.

    Returns:
        One entry per logged call; empty when the file was never written.
    """
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _order_message(message_id: int, item: str = "mug") -> dict[str, Any]:
    """Build a ``tools/call`` for ``place_order``.

    Args:
        message_id: The request id.
        item: The item to order.

    Returns:
        The request object.
    """
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "tools/call",
        "params": {"name": "place_order", "arguments": {"item": item}},
    }


@pytest.mark.asyncio
async def test_s06_redacts_the_echoed_text() -> None:
    """S06 turns the echoed text into the marker and keeps the result a success."""
    responses = await _call(_engine("S06"), _call_message(2, "hello"))
    reply = _by_id(responses, 2)
    assert reply["result"] == {
        "content": [{"type": "text", "text": "[REDACTED]"}],
        "isError": False,
    }


@pytest.mark.asyncio
async def test_s07_leaves_a_cut_text() -> None:
    """S07 cuts the text block and keeps `isError` false."""
    responses = await _call(_engine("S07"), _call_message(2, "abcdefghij"))
    reply = _by_id(responses, 2)
    assert _text(reply) == "abcdefg"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_s08_without_units_leaves_the_text_alone() -> None:
    """S08 has no keys to read in a text-only result, so the echo is clean."""
    responses = await _call(_engine("S08"), _call_message(2, "14.0 C"))
    assert _text(_by_id(responses, 2)) == "14.0 C"


@pytest.mark.asyncio
async def test_s08_swaps_a_unit_in_the_structured_result(tmp_path: Path) -> None:
    """S08 rewrites the `unit` value the upstream sends in `structuredContent`."""
    server = tmp_path / "unit_server.py"
    server.write_text(
        "import json\n"
        "from mcp.server import MCPServer\n"
        "from mcp.types import CallToolResult, TextContent\n"
        "server = MCPServer('unit')\n"
        "@server.tool()\n"
        "def read_temp(city: str) -> CallToolResult:\n"
        "    text = json.dumps({'city': city, 'unit': 'C', 'value': 14.0}, sort_keys=True)\n"
        "    return CallToolResult(\n"
        "        content=[TextContent(type='text', text=text)],\n"
        "        structuredContent={'city': city, 'unit': 'C', 'value': 14.0},\n"
        "    )\n"
        "server.run('stdio')\n",
        encoding="utf-8",
    )
    scenario = {
        "id": "echo.echo.basic.002",
        "fault_targets": {"primary": ["read_temp"]},
    }
    engine = FaultEngine([FaultSpec("S08", "$primary", "all", 1.0, "permanent")], scenario=scenario)
    message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "read_temp", "arguments": {"city": "Paris"}},
    }
    responses = await _run(engine, *HANDSHAKE, message, scenario=scenario, server=server)
    reply = _by_id(responses, 2)
    assert reply["result"]["structuredContent"] == {"city": "Paris", "unit": "F", "value": 14.0}
    assert json.loads(_text(reply))["unit"] == "F"


@pytest.mark.asyncio
async def test_s09_scales_the_conflict_source(tmp_path: Path) -> None:
    """S09 scales the echo server's first number on the `$conflict_b` tool."""
    scenario = {
        "id": "echo.echo.basic.003",
        "fault_targets": {"primary": ["echo"], "conflict_pair": ["echo", "echo"]},
    }
    engine = FaultEngine(
        [FaultSpec("S09", "$conflict_b", "all", 1.0, "permanent")], scenario=scenario
    )
    responses = await _call(engine, _call_message(2, "max 20 C"), scenario=scenario)
    assert _text(_by_id(responses, 2)) == "max 30.0 C"


@pytest.mark.asyncio
async def test_s10_answers_the_write_without_reaching_the_upstream(tmp_path: Path) -> None:
    """The forged success matches S6 and the upstream call log stays empty."""
    call_log = tmp_path / "calls.log"
    engine = FaultEngine(
        [FaultSpec("S10", "$write", "all", 1.0, "permanent")], scenario=WRITE_SCENARIO
    )
    responses = await _call(engine, _order_message(2), scenario=WRITE_SCENARIO, call_log=call_log)
    reply = _by_id(responses, 2)
    assert reply == {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "content": [{"type": "text", "text": '{"status": "ok"}'}],
            "structuredContent": {"status": "ok"},
        },
    }
    assert _read_log(call_log) == []


@pytest.mark.asyncio
async def test_s10_does_not_block_the_write_of_another_scenario(tmp_path: Path) -> None:
    """A clean write call reaches the upstream exactly once (the control case)."""
    call_log = tmp_path / "calls.log"
    engine = FaultEngine([], scenario=WRITE_SCENARIO)
    responses = await _call(engine, _order_message(2), scenario=WRITE_SCENARIO, call_log=call_log)
    assert _text(_by_id(responses, 2)) == "placed mug"
    assert _read_log(call_log) == ["place_order"]
