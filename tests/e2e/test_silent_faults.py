"""End-to-end tests: silent faults S01-S05 through the stdio proxy (F22).

Each test starts the real ``tests/fixtures/echo_server.py`` as the proxy's
upstream child, schedules one fault on a ``FaultEngine``, and drives the proxy
over a scripted stdin/stdout. The echo fixture has one required string argument,
so ``S05`` can swap the entity it echoes and every other fault has data to
rewrite. Results are checked as the client sees them, after JSON serialization.
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
    ) -> None:
        """Queue the client messages.

        Args:
            messages: The messages the client sends, in order.
            engine: The fault engine to mount.
            scenario: The scenario the episode runs, ``SCENARIO`` by default.
        """
        self.messages = messages
        self.engine = engine
        self.scenario = SCENARIO if scenario is None else scenario
        self.lines: list[bytes] = []
        self.scripted = _ScriptedIn()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        """Run the proxy in a thread with this session's streams."""
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(sys, "stdin", self.scripted)
            patch.setattr(sys, "stdout", _CapturedOut(self.lines))
            proxy = StdioProxy(
                [sys.executable, str(ECHO_SERVER)],
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
) -> list[dict[str, Any]]:
    """Run one proxy session to completion and return what the client saw.

    Args:
        engine: The fault engine to mount.
        messages: The client messages.
        wait_ids: Whether to wait for every message id before closing stdin.
        scenario: The scenario the episode runs, ``SCENARIO`` by default.

    Returns:
        The decoded response lines.
    """
    session = Session(list(messages), engine, scenario)
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
) -> list[dict[str, Any]]:
    """Run a handshake plus the given client messages.

    Args:
        engine: The fault engine to mount.
        messages: The extra client messages, after the handshake.
        scenario: The scenario the episode runs, ``SCENARIO`` by default.

    Returns:
        The decoded response lines.
    """
    return await _run(engine, *HANDSHAKE, *messages, scenario=scenario)


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
