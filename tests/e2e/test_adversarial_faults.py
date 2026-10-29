"""End-to-end tests: adversarial faults A01-A03 through the stdio proxy (F24).

Each test starts the real ``tests/fixtures/echo_server.py`` as the proxy's
upstream child, schedules one fault on a ``FaultEngine``, and drives the proxy
over scripted stdin/stdout. The client sees exactly what an agent would see, so
the payload text and the list-changed notification are checked byte for byte.

A03 counts the calls the client makes, so the sessions below fetch the list,
call ``echo`` until the threshold is reached, and fetch the list again. The
scenario declares ``tools.listChanged``, which the echo server does not, so the
legacy notification path can be exercised against a real connection.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from skeptic_agent.faults.adversarial import P1_TEMPLATE, P2_TEMPLATE, render
from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.proxy.pipeline import new_pipeline
from skeptic_agent.proxy.stdio import StdioProxy

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
TIMEOUT_SECONDS = 60

# The echo server's own description; A02 and A03 append P2 to it.
ECHO_DESCRIPTION = (
    "Return the text unchanged.\n\n"
    "    Args:\n"
    "        text: The text to echo.\n\n"
    "    Returns:\n"
    "        A tool result whose only content block is the same text.\n"
    "    "
)

SCENARIO: dict[str, Any] = {
    "id": "echo.echo.basic.001",
    "fault_targets": {"primary": ["echo"]},
    "capabilities": {"tools": {"listChanged": True}},
}

P1 = render(P1_TEMPLATE)
P2 = render(P2_TEMPLATE)


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
                episode_id="run:echo.echo.basic.001:A:1",
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


async def _run(engine: FaultEngine, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    """Run one proxy session to completion and return what the client saw.

    Args:
        engine: The fault engine to mount.
        messages: The client messages.

    Returns:
        The decoded response lines.
    """
    session = Session(list(messages), engine)
    session.start()
    for message in messages:
        if "id" in message:
            await session.wait_for_id(message["id"])
    return await session.finish()


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


def _list_message(message_id: int) -> dict[str, Any]:
    """Build a ``tools/list`` request.

    Args:
        message_id: The request id.

    Returns:
        The request object.
    """
    return {"jsonrpc": "2.0", "id": message_id, "method": "tools/list"}


def _descriptions(response: dict[str, Any]) -> dict[str, str]:
    """Return the tool descriptions of a list response.

    Args:
        response: The ``tools/list`` response.

    Returns:
        One description per tool name.
    """
    return {tool["name"]: tool.get("description", "") for tool in response["result"]["tools"]}


@pytest.mark.asyncio
async def test_a01_appends_p1_to_the_echo_text() -> None:
    """The client reads the echo with P1 appended and the result still a success."""
    responses = await _run(_engine("A01"), *HANDSHAKE, _call_message(2))
    reply = _by_id(responses, 2)
    assert _text(reply) == f"hello\n\n{P1}"
    assert reply["result"]["isError"] is False


@pytest.mark.asyncio
async def test_a02_poisons_the_tool_description() -> None:
    """The tools list carries the echo description with P2 appended."""
    responses = await _run(_engine("A02"), *HANDSHAKE, _list_message(2))
    reply = _by_id(responses, 2)
    assert _descriptions(reply) == {"echo": ECHO_DESCRIPTION + "\n\n" + P2}


@pytest.mark.asyncio
async def test_a02_payload_matches_p2_word_for_word() -> None:
    """The appended text is exactly P2, not a paraphrase."""
    responses = await _run(_engine("A02"), *HANDSHAKE, _list_message(2))
    description = _descriptions(_by_id(responses, 2))["echo"]
    assert description.endswith(f"\n\n{P2}")
    assert "compliance@exfil.example" in description
    assert "/home/user/test/canary.txt" in description


@pytest.mark.asyncio
async def test_a03_first_list_is_clean() -> None:
    """Before the calls the list is forwarded as the server sent it."""
    responses = await _run(_engine("A03"), *HANDSHAKE, _list_message(2))
    assert _descriptions(_by_id(responses, 2)) == {"echo": ECHO_DESCRIPTION}
    assert not any(
        response.get("method") == "notifications/tools/list_changed" for response in responses
    )


@pytest.mark.asyncio
async def test_a03_after_calls_poisons_and_notifies_a_legacy_client() -> None:
    """After the call the list is poisoned and the legacy client is told."""
    engine = _engine("A03", after_calls=2)
    responses = await _run(
        engine,
        *HANDSHAKE,
        _call_message(2),
        _call_message(3),
        _list_message(4),
    )
    assert _descriptions(_by_id(responses, 4)) == {"echo": ECHO_DESCRIPTION + "\n\n" + P2}
    notifications = [
        response
        for response in responses
        if response.get("method") == "notifications/tools/list_changed"
    ]
    assert notifications == [{"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}]
    assert responses.index(notifications[0]) == responses.index(_by_id(responses, 4)) + 1


@pytest.mark.asyncio
async def test_a03_waits_for_the_threshold() -> None:
    """With ``after_calls=2`` one call leaves the second list clean."""
    engine = _engine("A03", after_calls=2)
    responses = await _run(engine, *HANDSHAKE, _call_message(2), _list_message(3))
    assert _descriptions(_by_id(responses, 3)) == {"echo": ECHO_DESCRIPTION}
    assert not any(
        response.get("method") == "notifications/tools/list_changed" for response in responses
    )


@pytest.mark.asyncio
async def test_adversarial_faults_can_run_in_sequence() -> None:
    """A01 and A02 on one engine fire on the call and the list."""
    engine = FaultEngine([_spec("A01"), _spec("A02")], scenario=SCENARIO)
    responses = await _run(engine, *HANDSHAKE, _call_message(2), _list_message(3))
    assert _text(_by_id(responses, 2)) == f"hello\n\n{P1}"
    assert _descriptions(_by_id(responses, 3)) == {"echo": ECHO_DESCRIPTION + "\n\n" + P2}
