"""Integration tests: an HTTP client talks to an MCP server through the proxy (P14).

Each test starts the real ``tests/fixtures/echo_server.py`` on a streamable HTTP
port, serves ``HttpProxy`` on another, and drives it with the SDK client or with
plain ``httpx`` when the test needs to see the raw wire format.
"""

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import uvicorn
from mcp import Client, types

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.faults.loud import L02_CODE, L02_MESSAGE, L03_TEXT
from skeptic_agent.faults.profiles import FaultEntry, statically_applicable
from skeptic_agent.proxy.http import MCP_PATH, HttpProxy
from skeptic_agent.proxy.pipeline import Pipeline, new_pipeline

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

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


def _free_port() -> int:
    """Return a TCP port that is free right now.

    Returns:
        A port number the OS just handed out.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen[bytes] | None = None) -> None:
    """Wait until something accepts connections on a local port.

    Args:
        port: The port to poll.
        process: The child process that must stay alive, when there is one.

    Raises:
        RuntimeError: When the port does not open in time or the child exits.
    """
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("the upstream server exited before it listened")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"port {port} did not open")


class _EchoServer:
    """The echo fixture served over streamable HTTP on a free local port."""

    def __init__(self) -> None:
        """Choose a free port and start nothing yet."""
        self.port = _free_port()
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def url(self) -> str:
        """Return the upstream MCP endpoint.

        Returns:
            ``http://127.0.0.1:<port>/mcp``.
        """
        return f"http://127.0.0.1:{self.port}{MCP_PATH}"

    def __enter__(self) -> "_EchoServer":
        """Start the fixture and wait for its port.

        Returns:
            The running server.
        """
        self.process = subprocess.Popen(
            [sys.executable, str(ECHO_SERVER), "http", str(self.port)],
            env={**os.environ, "PYTHONPATH": _pythonpath()},
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_port(self.port, self.process)
        return self

    def __exit__(self, *exc: object) -> None:
        """Stop the fixture.

        Args:
            exc: The exception that left the block, if any.
        """
        if self.process is not None:
            self.process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=TIMEOUT_SECONDS)


class _Proxy:
    """Serve an ``HttpProxy`` on its own event loop and free local port."""

    def __init__(self, upstream: str, pipeline: Pipeline | None = None) -> None:
        """Build the proxy and pick a free listen port.

        Args:
            upstream: The upstream MCP endpoint.
            pipeline: The pipeline to serve, or ``None`` for the default one.
        """
        self.proxy = HttpProxy(upstream, pipeline, scenario={**SCENARIO, "transport": "http"})
        self.port = _free_port()
        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

    @property
    def url(self) -> str:
        """Return the proxy's MCP endpoint.

        Returns:
            ``http://127.0.0.1:<port>/mcp``.
        """
        return f"http://127.0.0.1:{self.port}{MCP_PATH}"

    def __enter__(self) -> "_Proxy":
        """Start the server in a background thread.

        Returns:
            The serving proxy.
        """
        config = uvicorn.Config(
            self.proxy.app(),
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        _wait_for_port(self.port)
        return self

    def _serve(self) -> None:
        """Run the server loop until it is told to stop."""
        assert self._server is not None
        asyncio.run(self._server.serve())

    def __exit__(self, *exc: object) -> None:
        """Stop the server and join its thread.

        Args:
            exc: The exception that left the block, if any.
        """
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=TIMEOUT_SECONDS)


def _engine(fault_id: str, scenario: dict[str, object] = SCENARIO, **params: object) -> FaultEngine:
    """Build an engine with one permanent fault on the echo tool.

    Args:
        fault_id: The S6 fault id.
        scenario: The scenario the episode runs against.
        params: The fault parameters.

    Returns:
        The engine.
    """
    spec = FaultSpec(
        fault_id=fault_id,
        tool="$primary",
        call_index="all",
        probability=1.0,
        persistence="permanent",
        params=dict(params) or None,
    )
    return FaultEngine([spec], scenario=scenario)


@contextlib.contextmanager
def _served(fault_id: str | None = None, **params: object) -> Iterator[_Proxy]:
    """Serve the echo fixture behind a proxy.

    Every episode runs over HTTP, so the scenario says so: L04 is applicable
    only then (S7.4).

    Args:
        fault_id: A fault to schedule on ``echo``, or ``None`` for a clean run.
        params: The fault parameters.

    Yields:
        The serving proxy.
    """
    pipeline = (
        new_pipeline(fault=_engine(fault_id, {**SCENARIO, "transport": "http"}, **params))
        if fault_id
        else None
    )
    with _EchoServer() as upstream, _Proxy(upstream.url, pipeline) as proxy:
        yield proxy


async def _initialize(client: httpx.AsyncClient, url: str) -> dict[str, str]:
    """Complete the MCP handshake and return the headers it established.

    The upstream SDK rejects messages from an unknown session, so every raw
    test message needs the session id the initialize reply carried.

    Args:
        client: The client talking to the proxy.
        url: The proxy's MCP endpoint.

    Returns:
        The headers to reuse for the session's later messages.
    """
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    reply = await client.post(
        url,
        headers=headers,
        content=b'{"jsonrpc":"2.0","id":0,"method":"initialize","params":{}}',
    )
    assert reply.status_code == 200
    session_id = reply.headers.get("mcp-session-id")
    if session_id is not None:
        headers["Mcp-Session-Id"] = session_id
    await client.post(
        url, headers=headers, content=b'{"jsonrpc":"2.0","method":"notifications/initialized"}'
    )
    return headers


def _payload(body: str) -> object:
    """Decode the JSON-RPC message of a reply, JSON or event stream.

    Args:
        body: The response body.

    Returns:
        The first message's JSON, or the body itself when it is not SSE.
    """
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    return json.loads(body)


def _first_text(result: types.CallToolResult) -> str:
    """Return the text of the first content block of a tool result.

    Args:
        result: The tool result.

    Returns:
        The text block's text.
    """
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


@pytest.mark.asyncio
async def test_echo_through_proxy() -> None:
    """The SDK client sees an undisturbed echo through the HTTP proxy."""
    with _served() as proxy:
        async with Client(proxy.url) as client:
            result = await client.call_tool("echo", {"text": "hello http proxy"})
            assert not result.is_error
            assert _first_text(result) == "hello http proxy"


@pytest.mark.asyncio
async def test_sse_response_is_relayed_as_events() -> None:
    """A streamed reply reaches the client as an event stream, not a JSON body."""
    with _served() as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            init = await client.post(
                proxy.url,
                headers={"Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            )
            assert init.status_code == 200
            assert init.headers["content-type"].startswith("text/event-stream")
            assert init.headers.get("mcp-session-id")

            headers = await _initialize(client, proxy.url)
            call = await client.post(
                proxy.url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": "streamed"}},
                },
            )
            assert call.status_code == 200
            assert 'data: {"jsonrpc":"2.0","id":2' in call.text
            assert '"streamed"' in call.text


@pytest.mark.asyncio
async def test_l02_answers_with_an_error() -> None:
    """L02 replaces the upstream reply with a JSON-RPC error."""
    with _served("L02") as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = await _initialize(client, proxy.url)
            reply = await client.post(
                proxy.url,
                headers=headers,
                content=(
                    b'{"jsonrpc":"2.0","id":7,"method":"tools/call",'
                    b'"params":{"name":"echo","arguments":{"text":"x"}}}'
                ),
            )
            assert reply.status_code == 200
            assert _payload(reply.text) == {
                "jsonrpc": "2.0",
                "id": 7,
                "error": {"code": L02_CODE, "message": L02_MESSAGE, "data": None},
            }


@pytest.mark.asyncio
async def test_l03_rewrites_an_event() -> None:
    """L03 rewrites the result of an event-stream reply."""
    with _served("L03") as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            init = await _initialize(client, proxy.url)
            reply = await client.post(
                proxy.url,
                headers=init,
                content=(
                    b'{"jsonrpc":"2.0","id":9,"method":"tools/call",'
                    b'"params":{"name":"echo","arguments":{"text":"x"}}}'
                ),
            )
            assert reply.status_code == 200
            assert L03_TEXT in reply.text
            assert '"isError":true' in reply.text


@pytest.mark.asyncio
async def test_l04_needs_an_http_scenario() -> None:
    """A scenario without ``transport: http`` is statically ruled out (S7.4)."""
    entry = FaultEntry(
        id="L04",
        target="$primary",
        call_index="all",
        probability=1.0,
        persistence="transient",
    )
    assert not statically_applicable(entry, SCENARIO)
    assert statically_applicable(entry, {**SCENARIO, "transport": "http"})


@pytest.mark.asyncio
async def test_l04_answers_503_and_never_reaches_the_upstream() -> None:
    """L04 answers the HTTP call with 503 and an empty body (S6, P14)."""
    with _served("L04") as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            init = await _initialize(client, proxy.url)
            started = time.monotonic()
            reply = await client.post(
                proxy.url,
                headers=init,
                content=(
                    b'{"jsonrpc":"2.0","id":11,"method":"tools/call",'
                    b'"params":{"name":"echo","arguments":{"text":"x"}}}'
                ),
            )
            assert reply.status_code == 503
            assert reply.content == b""
            assert time.monotonic() - started < 5


@pytest.mark.asyncio
async def test_l04_status_comes_from_the_params() -> None:
    """The ``status`` parameter is the one the client sees."""
    with _served("L04", status=418) as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = await _initialize(client, proxy.url)
            reply = await client.post(
                proxy.url,
                headers=headers,
                content=(
                    b'{"jsonrpc":"2.0","id":12,"method":"tools/call",'
                    b'"params":{"name":"echo","arguments":{"text":"x"}}}'
                ),
            )
            assert reply.status_code == 418
            assert reply.content == b""


@pytest.mark.asyncio
async def test_unreachable_upstream_is_a_bad_gateway() -> None:
    """A client message with no upstream to answer it gets 502."""
    dead = f"http://127.0.0.1:{_free_port()}{MCP_PATH}"
    with _Proxy(dead) as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            reply = await client.post(
                proxy.url, content=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
            )
            assert reply.status_code == 502


@pytest.mark.asyncio
async def test_delete_ends_the_session() -> None:
    """``DELETE /mcp`` reaches the upstream and answers with an empty body."""
    with _served() as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            headers = await _initialize(client, proxy.url)
            reply = await client.delete(proxy.url, headers=headers)
            assert reply.status_code in {200, 204}
            assert reply.content == b""


@pytest.mark.asyncio
async def test_other_paths_are_not_served() -> None:
    """Only ``/mcp`` exists; anything else is a 404 (S4.1)."""
    with _served() as proxy:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            reply = await client.post(
                proxy.url.replace(MCP_PATH, "/other"), content=b'{"jsonrpc":"2.0"}'
            )
            assert reply.status_code == 404
