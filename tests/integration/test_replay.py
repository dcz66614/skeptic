"""Integration tests: record an episode, then replay it to the same client (P16).

The first client calls ``tests/fixtures/echo_server.py`` through the proxy with a
cassette recorder mounted; then ``skeptic replay`` serves that cassette to a
second client. Both are real MCP SDK ``ClientSession`` objects and both see the
same tool results, value for value.

The server side runs in this process behind a child that only bridges the SDK's
stdio pipes to a loopback socket. That keeps the recorder's ``atexit`` and
signal hooks in the main thread where they belong, while the client still drives
the server over a real stdio transport.

``--on-miss error`` and ``--on-miss live`` are covered on one recording: a call
the cassette knows is replayed from the file, then a call it never saw is made
and its outcome shows which branch answered.
"""

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol

import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.jsonrpc import Request, parse_line
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.pipeline import new_pipeline
from skeptic_agent.proxy.stdio import StdioProxy
from skeptic_agent.record.cassette import (
    SCHEMA_ID,
    CassetteRecorder,
    Recorder,
    cassette_path,
)
from skeptic_agent.record.replay import (
    EXIT_INVALID,
    EXIT_USAGE,
    HANDSHAKE_METHODS,
    MISS_CODE,
    ON_MISS_ERROR,
    ON_MISS_LIVE,
    Cassette,
    ReplayError,
    ReplayServer,
    miss_error,
    read_cassette,
    recorded_initialize,
    request_key,
)

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
TIMEOUT_SECONDS = 60
EPISODE_ID = "20261105-142233-a1b2c3:echo.echo.basic.001:clean:1"
SCENARIO_ID = "echo.echo.basic.001"
ERA = Era(kind="MODERN", version="2026-07-28")

CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("echo", {"text": "first"}),
    ("echo", {"text": "second"}),
)
"""The two calls the recorded episode makes."""

UNRECORDED: tuple[str, dict[str, Any]] = ("echo", {"text": "never recorded"})
"""A call no cassette reply matches."""

BRIDGE = """
import socket
import sys
import threading

channel = socket.create_connection(("127.0.0.1", int(sys.argv[1])))


def to_server():
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            channel.shutdown(socket.SHUT_WR)
            return
        channel.sendall(line)


threading.Thread(target=to_server, daemon=True).start()
buffer = b""
while True:
    chunk = channel.recv(65536)
    if not chunk:
        break
    buffer += chunk
    while b"\\n" in buffer:
        line, buffer = buffer.split(b"\\n", 1)
        sys.stdout.buffer.write(line + b"\\n")
        sys.stdout.buffer.flush()
"""
"""Wire the SDK's stdio pipes to a loopback socket (run as ``python -c``)."""


class SocketServer(Protocol):
    """A server the harness drives over one loopback socket connection."""

    async def serve(self, reader: Any, writer: Any) -> None:
        """Serve the client until the connection closes.

        Args:
            reader: The connection's ``StreamReader``.
            writer: The connection's ``StreamWriter``.
        """
        ...


def _env() -> dict[str, str]:
    """Return the environment the bridge child gets.

    Returns:
        A copy of ``os.environ`` with ``src`` on ``PYTHONPATH``.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH")]))
    return env


class _Capture:
    """A binary stdout that hands every written line to a reader."""

    def __init__(self, to_client: Any) -> None:
        """Start with no buffered bytes.

        Args:
            to_client: The connection's ``StreamWriter``.
        """
        self.to_client = to_client
        self.pending = b""

    def write(self, data: bytes) -> None:
        """Buffer bytes and forward every complete line.

        Args:
            data: The bytes written.
        """
        self.pending += data
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            self.to_client.write(line + b"\n")

    async def drain(self) -> None:
        """Flush the connection."""
        await self.to_client.drain()


class _Replay(SocketServer):
    """``ReplayServer.run`` mounted on a loopback connection (S2)."""

    def __init__(self, server: ReplayServer) -> None:
        """Mount a loaded replayer.

        Args:
            server: The replayer.
        """
        self.server = server

    async def serve(self, reader: Any, writer: Any) -> None:
        """Serve the client until it disconnects.

        Args:
            reader: The connection's ``StreamReader``.
            writer: The connection's ``StreamWriter``.
        """
        with contextlib.suppress(ConnectionError):
            await self.server.run(stdin=_Lines(reader), stdout=_Capture(writer))


class _Lines:
    """A binary line source over an ``asyncio`` reader."""

    def __init__(self, reader: Any) -> None:
        """Wrap the connection's reader.

        Args:
            reader: The connection's ``StreamReader``.
        """
        self.reader = reader

    def readline(self) -> bytes:
        """Read one line.

        Used from a worker thread by ``ReplayServer.run``.

        Returns:
            The line, or ``b""`` at EOF.
        """
        return asyncio.run_coroutine_threadsafe(self.reader.readline(), _LOOP[0]).result()


class _Recording(SocketServer):
    """The stdio proxy with a recorder, mounted on a loopback connection."""

    def __init__(self, recorder: Recorder) -> None:
        """Start a proxy in front of the echo server.

        Args:
            recorder: The open cassette recorder.
        """
        self.proxy = StdioProxy(
            [sys.executable, str(ECHO_SERVER)],
            new_pipeline(recorder=CassetteRecorder(recorder)),
            episode_id=EPISODE_ID,
            seed=1,
        )
        self.proxy.ctx.era = ERA

    async def serve(self, reader: Any, writer: Any) -> None:
        """Relay the client to the echo server until either side leaves.

        Args:
            reader: The connection's ``StreamReader``.
            writer: The connection's ``StreamWriter``.
        """
        with contextlib.suppress(ConnectionError):
            await self.proxy.serve(reader=reader, writer=writer)


_LOOP: list[asyncio.AbstractEventLoop] = []
_CONNECTIONS: list["asyncio.Task[None]"] = []


async def _connect(server: SocketServer, reader: Any, writer: Any) -> None:
    """Run one server for the accepted connection.

    Args:
        server: The server.
        reader: The connection's ``StreamReader``.
        writer: The connection's ``StreamWriter``.
    """
    _CONNECTIONS.append(asyncio.current_task())  # type: ignore[arg-type]
    try:
        await server.serve(reader, writer)
    finally:
        writer.close()


@contextlib.asynccontextmanager
async def _client(server: SocketServer) -> AsyncIterator[ClientSession]:
    """Serve ``server`` to an MCP client over a stdio transport.

    Args:
        server: The server to mount.

    Yields:
        The initialized client session.
    """
    _LOOP.append(asyncio.get_running_loop())

    async def accept(reader: Any, writer: Any) -> None:
        """Hand one accepted connection to the server.

        Args:
            reader: The connection's ``StreamReader``.
            writer: The connection's ``StreamWriter``.
        """
        await _connect(server, reader, writer)

    listener = await asyncio.start_server(accept, "127.0.0.1", 0, family=socket.AF_INET)
    port = listener.sockets[0].getsockname()[1]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", BRIDGE, str(port)],
        env=_env(),
        cwd=str(ROOT),
    )
    try:
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session
    finally:
        for task in _CONNECTIONS:
            task.cancel()
        _CONNECTIONS.clear()
        listener.close()
        await listener.wait_closed()
        _LOOP.clear()


async def _record(tmp_path: Path) -> list[dict[str, Any]]:
    """Record ``CALLS`` through the proxy and return what the client saw.

    Args:
        tmp_path: The record directory.

    Returns:
        One tool result per call, in order.
    """
    recorder = Recorder.open(
        tmp_path,
        episode_id=EPISODE_ID,
        transport="stdio",
        upstream=[sys.executable, str(ECHO_SERVER)],
        era=ERA,
        seed=1,
        profile="none",
        scenario_id=SCENARIO_ID,
    )
    results: list[dict[str, Any]] = []
    try:
        async with _client(_Recording(recorder)) as session:
            for name, arguments in CALLS:
                result = await session.call_tool(name, arguments)
                results.append(json.loads(result.model_dump_json(by_alias=True)))
    finally:
        recorder.finish()
    return results


def _result(text: str) -> dict[str, Any]:
    """Return the SDK's JSON form of an ``echo`` result.

    Args:
        text: The echoed text.

    Returns:
        The expected ``CallToolResult`` object.
    """
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        isError=False,
    ).model_dump(mode="json", by_alias=True)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_replay_returns_the_recorded_results(tmp_path: Path) -> None:
    """S2 acceptance: the replayed results equal the recorded ones."""
    recorded = await _record(tmp_path)
    assert recorded == [_result("first"), _result("second")]

    cassette = Cassette.load(cassette_path(tmp_path, EPISODE_ID))
    async with _client(_Replay(ReplayServer(cassette))) as session:
        replayed = [
            json.loads((await session.call_tool(name, arguments)).model_dump_json(by_alias=True))
            for name, arguments in CALLS
        ]
    assert replayed == recorded


@pytest.mark.asyncio
@pytest.mark.integration
async def test_replay_answers_the_handshake_from_the_cassette(tmp_path: Path) -> None:
    """``initialize`` and ``tools/list`` come from the recording; the queue is untouched."""
    await _record(tmp_path)
    cassette = Cassette.load(cassette_path(tmp_path, EPISODE_ID))
    assert cassette.pending() == len(CALLS)
    async with _client(_Replay(ReplayServer(cassette))) as session:
        tools = await session.list_tools()
    assert [tool.name for tool in tools.tools] == ["echo"]
    assert cassette.pending() == len(CALLS)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_replay_answers_a_miss_with_an_error(tmp_path: Path) -> None:
    """An unrecorded call under ``--on-miss error`` fails with a JSON-RPC error."""
    await _record(tmp_path)
    cassette = Cassette.load(cassette_path(tmp_path, EPISODE_ID))

    server = ReplayServer(cassette, on_miss=ON_MISS_ERROR)
    async with _client(_Replay(server)) as session:
        with pytest.raises(MCPError) as raised:
            await session.call_tool(*UNRECORDED)
    assert raised.value.error.code == MISS_CODE
    assert "no recorded reply" in raised.value.error.message


@pytest.mark.asyncio
@pytest.mark.integration
async def test_replay_live_sends_a_miss_to_the_upstream(tmp_path: Path) -> None:
    """An unrecorded call under ``--on-miss live`` is answered by the live server."""
    await _record(tmp_path)
    cassette = Cassette.load(cassette_path(tmp_path, EPISODE_ID))
    server = ReplayServer(
        cassette,
        on_miss=ON_MISS_LIVE,
        live_command=[sys.executable, str(ECHO_SERVER)],
    )
    async with _client(_Replay(server)) as session:
        result = await session.call_tool(*UNRECORDED)
    assert json.loads(result.model_dump_json(by_alias=True)) == _result(UNRECORDED[1]["text"])


# --- unit tests: no processes, no network -------------------------------------


EPISODE_ID = "20261105-142233-a1b2c3:echo.echo.basic.001:clean:1"
SCENARIO_ID = "echo.echo.basic.001"
ROOT = Path(__file__).resolve().parents[2]


def _header() -> dict[str, Any]:
    """Build a minimal valid header (S5).

    Returns:
        The header object.
    """
    return {
        "type": "header",
        "schema": SCHEMA_ID,
        "episode_id": EPISODE_ID,
        "created_at": "2026-11-05T14:22:33Z",
        "skeptic_version": "0.0.0",
        "transport": "stdio",
        "upstream": {"command": ["python"]},
        "era": "2026-07-28",
        "seed": 1,
        "profile": "none",
        "fault_plan": [],
        "guards": [],
        "scenario_id": SCENARIO_ID,
    }


def _msg(
    direction: str, raw: dict[str, Any], final: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    """Build one ``msg`` record (S5).

    Args:
        direction: ``c2s`` or ``s2c``.
        raw: The message as received.
        final: The message as sent, or ``None``.
        extra: Extra record fields.

    Returns:
        The record.
    """
    record: dict[str, Any] = {
        "type": "msg",
        "seq": extra.pop("seq", 0),
        "t_ms": 0,
        "dir": direction,
        "raw": raw,
        "final": final,
        "fault": None,
        "guards": [],
        "dropped": False,
        "internal": False,
    }
    record.update(extra)
    return record


def _response(ident: int, text: str) -> dict[str, Any]:
    """Build a tool-call response object.

    Args:
        ident: The response id.
        text: The echoed text.

    Returns:
        The response object.
    """
    return {"jsonrpc": "2.0", "id": ident, "result": {"content": [{"type": "text", "text": text}]}}


def _call(ident: int, text: str, tool: str = "echo") -> dict[str, Any]:
    """Build a ``tools/call`` request object.

    Args:
        ident: The request id.
        text: The text argument.
        tool: The tool name.

    Returns:
        The request object.
    """
    return {
        "jsonrpc": "2.0",
        "id": ident,
        "method": "tools/call",
        "params": {"name": tool, "arguments": {"text": text}},
    }


def _write(path: Path, records: list[dict[str, Any]]) -> Path:
    """Write records as a cassette file.

    Args:
        path: The destination.
        records: The records.

    Returns:
        The destination.
    """
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def _cassette(tmp_path: Path, records: list[dict[str, Any]]) -> Cassette:
    """Write and load a cassette.

    Args:
        tmp_path: The directory.
        records: The records.

    Returns:
        The loaded cassette.
    """
    return Cassette.load(_write(tmp_path / "c.jsonl", records))


def _request(payload: dict[str, Any]) -> Request:
    """Parse a request object.

    Args:
        payload: The request.

    Returns:
        The parsed request.
    """
    parsed = parse_line(json.dumps(payload).encode())
    assert isinstance(parsed, Request)
    return parsed


def test_request_key_ignores_member_order() -> None:
    """The key hashes method, tool and arguments, not their spelling."""
    assert request_key("tools/call", "echo", {"a": 1, "b": 2}) == request_key(
        "tools/call", "echo", {"b": 2, "a": 1}
    )
    assert request_key("tools/call", "echo", {"a": 1}) != request_key(
        "tools/call", "other", {"a": 1}
    )
    assert request_key("tools/list", None, None) != request_key("tools/call", None, None)


def test_load_queues_replies_by_key_in_order(tmp_path: Path) -> None:
    """Two calls with equal keys queue two replies in recorded order."""
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("c2s", _call(1, "same"), seq=0),
            _msg("s2c", _response(1, "a"), seq=1),
            _msg("c2s", _call(2, "same"), seq=2),
            _msg("s2c", _response(2, "b"), seq=3),
            {"type": "footer", "ended_at": "2026-11-05T14:23:10Z", "stats": {}},
        ],
    )
    assert cassette.pending() == 2
    first = cassette.match(_request(_call(9, "same")))
    second = cassette.match(_request(_call(9, "same")))
    assert first is not None
    assert second is not None
    assert first["result"]["content"][0]["text"] == "a"
    assert second["result"]["content"][0]["text"] == "b"
    assert cassette.match(_request(_call(9, "same"))) is None


def test_load_prefers_final_over_raw(tmp_path: Path) -> None:
    """S5's ``final`` is what the client saw, so it is what replay returns."""
    final = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "final"}]}}
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("c2s", _call(1, "x")),
            _msg("s2c", _response(1, "raw"), final=final),
        ],
    )
    taken = cassette.match(_request(_call(7, "x")))
    assert taken == final


def test_load_uses_the_fault_target_as_the_tool_name(tmp_path: Path) -> None:
    """A rewritten request keeps its key through ``fault.target.tool``.

    A fault record only names the tool it applies to (S5), so it also supplies
    the tool name when the recorded request no longer carries a plain one.
    """
    recorded = _call(1, "x")
    recorded["params"]["name"] = "$primary"
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("c2s", recorded, fault={"id": "S05", "target": {"tool": "echo"}}),
            _msg("s2c", _response(1, "ok")),
        ],
    )
    assert cassette.match(_request(_call(7, "x", tool="echo"))) is not None


def test_load_caches_the_handshake_and_the_list(tmp_path: Path) -> None:
    """``initialize`` and ``tools/list`` are kept once and never queued away."""
    initialize = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}
    tools = {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "echo"}]}}
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("c2s", {"jsonrpc": "2.0", "id": 1, "method": "initialize"}, seq=0),
            _msg("s2c", initialize, seq=1),
            _msg("c2s", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, seq=2),
            _msg("s2c", tools, seq=3),
        ],
    )
    assert set(cassette.methods) == {"initialize", "tools/list"}
    assert cassette.pending() == 0
    assert cassette.match(_request({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})) == tools
    assert (
        cassette.match(_request({"jsonrpc": "2.0", "id": 9, "method": "initialize"})) == initialize
    )


def test_load_skips_internal_and_notification_records(tmp_path: Path) -> None:
    """Internal replies and notifications are not replay material."""
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("s2c", _response("skeptic-1", "internal"), internal=True),
            _msg("s2c", {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}),
            _msg("c2s", _call(1, "x")),
            _msg("s2c", _response(1, "x")),
        ],
    )
    assert cassette.pending() == 1
    assert set(cassette.methods) == set()


def test_load_rejects_a_response_without_a_result(tmp_path: Path) -> None:
    """An object that is neither a result nor an error is not a reply."""
    path = _write(
        tmp_path / "c.jsonl",
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", {"jsonrpc": "2.0", "id": 1})],
    )
    with pytest.raises(ReplayError, match="is not a response"):
        Cassette.load(path)


def test_load_rejects_a_missing_reply(tmp_path: Path) -> None:
    """A call without an answer cannot be replayed."""
    path = _write(tmp_path / "c.jsonl", [_header(), _msg("c2s", _call(1, "x"))])
    with pytest.raises(ReplayError, match="no recorded reply"):
        Cassette.load(path)


def test_load_rejects_a_redacted_reply_on_load(tmp_path: Path) -> None:
    """Redaction is detected while loading, not while serving."""
    path = _write(
        tmp_path / "c.jsonl",
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", _response(1, "token ***"))],
    )
    with pytest.raises(ReplayError, match="redacted"):
        Cassette.load(path)


def test_read_cassette_rejects_a_missing_file(tmp_path: Path) -> None:
    """An unreadable path is a replay error, not a crash."""
    with pytest.raises(ReplayError, match="cannot read"):
        read_cassette(tmp_path / "nope.jsonl")


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        (["{"], "invalid JSON"),
        (["[]"], "must be a JSON object"),
        (["{}"], "not a header"),
        ([json.dumps({**_header(), "schema": "other"})], "schema is not"),
    ],
)
def test_read_cassette_rejects_bad_files(tmp_path: Path, lines: list[str], message: str) -> None:
    """A bad cassette is rejected with a reason."""
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ReplayError, match=message):
        read_cassette(path)


def test_read_cassette_rejects_a_non_object_raw(tmp_path: Path) -> None:
    """Every ``msg`` must carry an object in ``raw``."""
    path = _write(tmp_path / "c.jsonl", [_header(), _msg("c2s", [1, 2])])  # type: ignore[arg-type]
    with pytest.raises(ReplayError, match="raw is not an object"):
        Cassette.load(path)


def test_recorded_initialize_prefers_initialize(tmp_path: Path) -> None:
    """Either handshake name reaches the one recorded handshake."""
    cassette = _cassette(tmp_path, [_header()])
    assert recorded_initialize(cassette) is None
    cassette.methods["server/discover"] = {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert recorded_initialize(cassette) == {"jsonrpc": "2.0", "id": 1, "result": {}}
    cassette.methods["initialize"] = {"jsonrpc": "2.0", "id": 2, "result": {"x": 1}}
    assert recorded_initialize(cassette) == {"jsonrpc": "2.0", "id": 2, "result": {"x": 1}}
    assert {"initialize", "server/discover"} == HANDSHAKE_METHODS


def test_miss_error_carries_the_request_id() -> None:
    """S2's miss error answers the request it belongs to."""
    error = miss_error(_request(_call(4, "x")), detail="tools/call")
    assert error.id == 4
    assert error.error.code == MISS_CODE
    assert "no recorded reply" in error.error.message


class _Out:
    """A binary sink that keeps every written line."""

    def __init__(self) -> None:
        """Start empty."""
        self.lines: list[bytes] = []

    def write(self, data: bytes) -> None:
        """Keep written bytes.

        Args:
            data: The bytes.
        """
        self.lines.extend(data.splitlines(keepends=True))

    async def drain(self) -> None:
        """Return at once."""

    def json(self) -> list[dict[str, Any]]:
        """Decode the written lines.

        Returns:
            The decoded messages.
        """
        return [json.loads(line) for line in self.lines]


def _serve(cassette: Cassette, **options: Any) -> ReplayServer:
    """Build a replayer.

    Args:
        cassette: The cassette.
        options: Extra ``ReplayServer`` options.

    Returns:
        The server.
    """
    return ReplayServer(cassette, **options)


@pytest.mark.asyncio
async def test_handle_line_answers_from_the_cassette(tmp_path: Path) -> None:
    """A recorded call is answered with the recorded result and the client's id."""
    cassette = _cassette(
        tmp_path,
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", _response(1, "x"))],
    )
    out = _Out()
    await _serve(cassette).handle_line(json.dumps(_call(42, "x")).encode(), out)
    assert [message["id"] for message in out.json()] == [42]
    assert out.json()[0]["result"]["content"][0]["text"] == "x"


@pytest.mark.asyncio
async def test_handle_line_answers_a_miss_with_an_error(tmp_path: Path) -> None:
    """Under ``error`` a miss is a JSON-RPC error (S2)."""
    out = _Out()
    await _serve(_cassette(tmp_path, [_header()])).handle_line(
        json.dumps(_call(5, "x")).encode(), out
    )
    (message,) = out.json()
    assert message["id"] == 5
    assert message["error"]["code"] == MISS_CODE


@pytest.mark.asyncio
async def test_handle_line_ignores_notifications_and_reports_parse_errors(tmp_path: Path) -> None:
    """A notification gets no reply; a broken line gets a parse error."""
    out = _Out()
    server = _serve(_cassette(tmp_path, [_header()]))
    await server.handle_line(b'{"jsonrpc":"2.0","method":"notifications/initialized"}', out)
    assert out.lines == []
    await server.handle_line(b"not json", out)
    (message,) = out.json()
    assert message["error"]["code"] == -32700
    assert message["id"] is None


@pytest.mark.asyncio
async def test_handle_line_answers_discover_from_an_initialize_recording(tmp_path: Path) -> None:
    """A modern client's ``server/discover`` reaches a legacy recording (S4.2)."""
    initialize = {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-11-25"}}
    cassette = _cassette(
        tmp_path,
        [
            _header(),
            _msg("c2s", {"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            _msg("s2c", initialize),
        ],
    )
    out = _Out()
    await _serve(cassette).handle_line(b'{"jsonrpc":"2.0","id":7,"method":"server/discover"}', out)
    assert out.json() == [{"jsonrpc": "2.0", "id": 7, "result": {"protocolVersion": "2025-11-25"}}]


@pytest.mark.integration
def test_load_rejects_a_reply_that_is_not_a_message(tmp_path: Path) -> None:
    """A reply whose shape is not a JSON-RPC message cannot be replayed."""
    path = _write(
        tmp_path / "c.jsonl",
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", {"jsonrpc": "1.0", "result": 1})],
    )
    with pytest.raises(ReplayError, match="not a JSON-RPC message"):
        Cassette.load(path)


def test_cli_rejects_an_unknown_on_miss(tmp_path: Path) -> None:
    """S2 allows only ``error`` and ``live``."""
    result = CliRunner().invoke(
        app, ["replay", "--cassette", str(tmp_path / "c.jsonl"), "--on-miss", "skip"]
    )
    assert result.exit_code == EXIT_USAGE


def test_cli_requires_a_command_for_live(tmp_path: Path) -> None:
    """``--on-miss live`` needs an upstream after ``--``."""
    result = CliRunner().invoke(
        app, ["replay", "--cassette", str(tmp_path / "c.jsonl"), "--on-miss", "live"]
    )
    assert result.exit_code == EXIT_USAGE


def test_cli_rejects_an_invalid_cassette(tmp_path: Path) -> None:
    """A bad cassette exits with S2's invalid-file code."""
    result = CliRunner().invoke(app, ["replay", "--cassette", str(tmp_path / "nope.jsonl")])
    assert result.exit_code == 3


def test_cli_reports_a_failed_live_upstream(tmp_path: Path) -> None:
    """A live upstream that cannot start exits with S2's invalid-file code."""
    cassette = _write(
        tmp_path / "c.jsonl",
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", _response(1, "x"))],
    )
    result = CliRunner().invoke(
        app,
        ["replay", "--cassette", str(cassette), "--on-miss", "live", "--", "no-such-command-xyz"],
    )
    assert result.exit_code == EXIT_INVALID


def test_cli_serves_a_cassette_end_to_end(tmp_path: Path) -> None:
    """``skeptic replay`` answers over its own stdin and stdout (S2)."""
    cassette = _write(
        tmp_path / "c.jsonl",
        [_header(), _msg("c2s", _call(1, "x")), _msg("s2c", _response(1, "x"))],
    )
    requests = b"".join(
        json.dumps(payload).encode() + b"\n" for payload in (_call(3, "x"), _call(4, "y"))
    )
    completed = subprocess.run(
        [sys.executable, "-m", "skeptic_agent.cli", "replay", "--cassette", str(cassette)],
        input=requests,
        capture_output=True,
        timeout=60,
        check=False,
        cwd=ROOT,
    )
    assert completed.returncode == 0, completed.stderr
    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [reply["id"] for reply in replies] == [3, 4]
    assert replies[0]["result"]["content"][0]["text"] == "x"
    assert replies[1]["error"]["code"] == MISS_CODE


@pytest.mark.asyncio
async def test_run_stops_at_eof(tmp_path: Path) -> None:
    """The server returns ``0`` when its input closes."""

    class _Input:
        def __init__(self) -> None:
            """Start empty."""
            self.line = b""

        def readline(self) -> bytes:
            """Return one queued line, then EOF.

            Returns:
                The line, then ``b""``.
            """
            line, self.line = self.line, b""
            return line

    source = _Input()
    code = await _serve(_cassette(tmp_path, [_header()])).run(stdin=source, stdout=_Out())
    assert code == 0
    assert ON_MISS_ERROR == "error"
    assert ON_MISS_LIVE == "live"
