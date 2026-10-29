"""End-to-end tests: loud faults L01-L07 through the stdio proxy (F21).

Each test starts the real ``tests/fixtures/echo_server.py`` as the proxy's
upstream child, schedules one fault on a ``FaultEngine``, and drives the proxy
over a scripted stdin/stdout. A helper thread answers from the client side, so a
test can read exactly the bytes the client would receive.
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
from skeptic_agent.faults.loud import L03_TEXT, L05_RETRY_AFTER_S
from skeptic_agent.proxy.pipeline import new_pipeline
from skeptic_agent.proxy.stdio import StdioProxy

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
TIMEOUT_SECONDS = 60

SCENARIO = {
    "id": "echo.echo.basic.001",
    "fault_targets": {"primary": ["echo"]},
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

    def __init__(self, messages: list[dict[str, Any]], engine: FaultEngine) -> None:
        """Queue the client messages.

        Args:
            messages: The messages the client sends, in order.
            engine: The fault engine to mount.
        """
        self.messages = messages
        self.engine = engine
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
                episode_id="run:echo.echo.basic.001:L:1",
                seed=1,
            )
            proxy.ctx.scenario = SCENARIO
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
    """A binary stdin fed through an OS pipe.

    The proxy closes its upstream as soon as the client stdin hits EOF, so the
    test keeps the write end open until every reply it expects has arrived.
    """

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
    engine: FaultEngine, *messages: dict[str, Any], wait_ids: bool = True
) -> list[dict[str, Any]]:
    """Run one proxy session to completion and return what the client saw.

    The upstream is a real subprocess, so this is the same path a user takes.

    Args:
        engine: The fault engine to mount.
        messages: The client messages.

    Returns:
        The decoded response lines.
    """
    session = Session(list(messages), engine)
    session.start()
    if wait_ids:
        for message in messages:
            if "id" in message:
                await session.wait_for_id(message["id"])
    return await session.finish()


async def _call(engine: FaultEngine, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    """Run a handshake plus the given client messages.

    Args:
        engine: The fault engine to mount.
        messages: The extra client messages, after the handshake.

    Returns:
        The decoded response lines.
    """
    return await _run(engine, *HANDSHAKE, *messages)


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
async def test_no_fault_is_a_plain_echo() -> None:
    """The harness itself works: without a fault the echo result comes back."""
    responses = await _call(FaultEngine(scenario=SCENARIO), _call_message(2, "plain"))
    reply = _by_id(responses, 2)
    assert reply["result"]["content"][0]["text"] == "plain"
    assert reply["result"].get("isError") is False


@pytest.mark.asyncio
async def test_l01_times_out_the_call() -> None:
    """L01 answers the call with the S6 timeout error after its hold."""
    responses = await _call(_engine("L01", hold_ms=10), _call_message(2))
    assert _by_id(responses, 2) == {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32001, "message": "Request timed out", "data": None},
    }


@pytest.mark.asyncio
async def test_l01_cancellation_drops_the_reply() -> None:
    """Cancelling during the hold means the client never gets a reply for the call."""
    engine = _engine("L01", hold_ms=5000)
    session = Session(
        [
            *HANDSHAKE,
            _call_message(2),
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 2, "reason": "client gave up"},
            },
        ],
        engine,
    )
    session.start()
    await session.wait_for_id(1)
    responses = await session.finish()
    assert [response.get("id") for response in responses] == [1]
    assert all("error" not in response for response in responses)


@pytest.mark.asyncio
async def test_l01_hold_ends_early_on_cancel() -> None:
    """The cancelled hold does not keep the proxy alive for the full ``hold_ms``."""
    engine = _engine("L01", hold_ms=30000)
    session = Session(
        [
            *HANDSHAKE,
            _call_message(2),
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 2},
            },
        ],
        engine,
    )
    loop = asyncio.get_running_loop()
    started = loop.time()
    session.start()
    responses = await session.finish()
    assert loop.time() - started < 15
    assert [response.get("id") for response in responses] == [1]


@pytest.mark.asyncio
async def test_l02_returns_a_jsonrpc_error() -> None:
    """L02 replaces the tool result with code -32603."""
    responses = await _call(_engine("L02"), _call_message(2))
    assert _by_id(responses, 2) == {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {"code": -32603, "message": "Internal error", "data": None},
    }


@pytest.mark.asyncio
async def test_l03_returns_the_upstream_error_text() -> None:
    """L03 turns the echo result into the S6 503 tool error."""
    responses = await _call(_engine("L03"), _call_message(2))
    assert _by_id(responses, 2)["result"] == {
        "content": [{"type": "text", "text": L03_TEXT}],
        "isError": True,
    }


@pytest.mark.asyncio
async def test_l05_returns_the_rate_limit_text() -> None:
    """L05 turns the echo result into the S6 429 tool error."""
    responses = await _call(_engine("L05"), _call_message(2))
    assert _by_id(responses, 2)["result"] == {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Error 429: rate limit exceeded. Retry after {L05_RETRY_AFTER_S} seconds."
                ),
            }
        ],
        "isError": True,
    }


@pytest.mark.asyncio
async def test_l06_removes_the_tool_and_rejects_its_calls() -> None:
    """L06 hides ``echo`` in ``tools/list`` and answers calls with -32602."""
    responses = await _call(
        _engine("L06"),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _call_message(3),
    )
    listing = _by_id(responses, 2)
    assert listing["result"]["tools"] == []
    assert _by_id(responses, 3) == {
        "jsonrpc": "2.0",
        "id": 3,
        "error": {"code": -32602, "message": "Unknown tool: echo", "data": None},
    }


@pytest.mark.asyncio
async def test_l07_drifts_the_schema_and_translates_the_call() -> None:
    """L07 renames ``text`` to ``text_v2`` and still reaches the upstream with ``text``."""
    responses = await _call(
        _engine("L07"),
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text_v2": "drifted"}},
        },
    )
    schema = _by_id(responses, 2)["result"]["tools"][0]["inputSchema"]
    assert schema["properties"] == {"text_v2": {"title": "Text", "type": "string"}}
    assert schema["required"] == ["text_v2"]
    reply = _by_id(responses, 3)
    assert _text(reply) == "drifted"
    assert reply["result"].get("isError") is False


@pytest.mark.asyncio
async def test_l07_rejects_the_old_parameter() -> None:
    """A call that still sends ``text`` is answered without reaching upstream."""
    responses = await _call(_engine("L07"), _call_message(2))
    assert _by_id(responses, 2) == {
        "jsonrpc": "2.0",
        "id": 2,
        "error": {
            "code": -32602,
            "message": "Invalid arguments: missing required property 'text_v2'",
            "data": None,
        },
    }
