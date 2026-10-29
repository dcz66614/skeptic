"""Proxy latency and concurrency benchmark (P17).

Measures the per-message cost the proxy adds on top of the upstream, for both
transports, against ``tests/fixtures/echo_server.py``:

- **stdio**: an SDK client goes direct to the echo server, then a second SDK
  client goes to ``skeptic proxy stdio -- python echo_server.py``.
- **HTTP**: the echo fixture and the proxy are served in this process (the
  proxy is the ``HttpProxy`` the CLI runs), and a plain ``httpx`` client posts
  the same body direct and then through the proxy.

Each sample is one ``tools/call`` through the proxy minus the ``tools/call``
before it sent direct. One long-lived proxy and its upstream (and one direct
upstream for the baseline) serve every sample of a transport, so the samples
measure the proxy hop rather than process startup. p50 and p99 are computed over
the samples; P17's acceptance is p50 < 5 ms and p99 < 30 ms.

The default pipeline runs: no faults and no Guards, which is the "proxy with no
faults, no Guards" overhead P17 asks for. The concurrency check then has 50
clients make 100 calls each; every reply must carry its own id and text.

Run it with ``uv run python tests/perf/bench_proxy.py`` (``--help`` lists the
knobs). A short smoke run of the same code lives in
``tests/perf/test_bench_proxy.py`` behind the ``perf`` marker, which the default
pytest run deselects.
"""

import argparse
import asyncio
import contextlib
import json
import os
import statistics
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.utilities.logging import configure_logging

from skeptic_agent.proxy.http import HttpProxy

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
MCP_PATH: str = "/mcp"
PAYLOAD: str = "benchmark"
LISTEN_ADDRESS: str = "127.0.0.1"
"""The address every benchmark server listens on."""
STARTUP_SECONDS: float = 60.0
SESSION_PROTOCOL_VERSION: str = "2025-06-18"
"""The protocol version the HTTP echo fixture negotiates; its session is required
for every later message."""

P50_LIMIT_MS: float = 5.0
"""P17's acceptance: the added latency p50 in milliseconds."""

P99_LIMIT_MS: float = 30.0
"""P17's acceptance: the added latency p99 in milliseconds."""


def _pythonpath() -> str:
    """Return a ``PYTHONPATH`` that finds the package source and the fixtures.

    Returns:
        ``src``, the fixtures dir and the existing ``PYTHONPATH``, joined.
    """
    parts = [str(ROOT / "src"), str(ECHO_SERVER.parent)]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _env() -> dict[str, str]:
    """Return the child environment with the benchmark ``PYTHONPATH``.

    Returns:
        A copy of the environment with ``PYTHONPATH`` set.
    """
    return {**os.environ, "PYTHONPATH": _pythonpath()}


def _percentile(samples: Sequence[float], fraction: float) -> float:
    """Return a percentile of the samples in milliseconds, interpolated.

    Args:
        samples: The samples in seconds.
        fraction: The percentile as a fraction, for example ``0.99``.

    Returns:
        The percentile in milliseconds, or ``0.0`` for no samples.
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return (ordered[lower] + (ordered[upper] - ordered[lower]) * weight) * 1000


def _summary(samples: Sequence[float]) -> dict[str, float]:
    """Summarize latency samples in milliseconds.

    Args:
        samples: The samples in seconds.

    Returns:
        ``count``, ``p50``, ``p90``, ``p99``, ``mean``, ``min`` and ``max``.
    """
    return {
        "count": float(len(samples)),
        "p50": _percentile(samples, 0.50),
        "p90": _percentile(samples, 0.90),
        "p99": _percentile(samples, 0.99),
        "mean": statistics.fmean(samples) * 1000 if samples else 0.0,
        "min": min(samples) * 1000 if samples else 0.0,
        "max": max(samples) * 1000 if samples else 0.0,
    }


def _passes(summary: dict[str, float]) -> bool:
    """Report whether a summary meets the P17 acceptance.

    Args:
        summary: A summary from ``_summary``.

    Returns:
        ``True`` when p50 < 5 ms and p99 < 30 ms.
    """
    return summary["p50"] < P50_LIMIT_MS and summary["p99"] < P99_LIMIT_MS


async def _wait_for_listening(server: uvicorn.Server) -> None:
    """Wait until an in-process server has taken its listen socket.

    Args:
        server: The uvicorn server started as a task.

    Raises:
        RuntimeError: When the server does not start in time.
    """
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if server.started or server.should_exit:
            break
        await asyncio.sleep(0.01)
    if not server.started:
        raise RuntimeError("the server did not start")


@contextlib.asynccontextmanager
async def _served(upstream: str) -> AsyncIterator[str]:
    """Serve ``skeptic proxy http`` in this process until the block ends.

    Serving the proxy in-process keeps one proxy and one ``httpx.AsyncClient``
    alive for the whole transport, which is what a real client sees.

    Args:
        upstream: The upstream MCP endpoint.

    Yields:
        The proxy's MCP endpoint.
    """
    proxy = HttpProxy(upstream)
    config = uvicorn.Config(proxy.app(), host=LISTEN_ADDRESS, port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_for_listening(server)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://{LISTEN_ADDRESS}:{port}{MCP_PATH}"
    finally:
        server.should_exit = True
        await task


class _EchoApp:
    """Serve the echo fixture's streamable-HTTP app.

    The fixture is an MCP SDK ``MCPServer``; serving its own app lets every sample
    of one transport talk to a single long-lived upstream.
    """

    def __init__(self) -> None:
        """Import the echo fixture and keep its server object."""
        sys.path.insert(0, str(ECHO_SERVER.parent))
        try:
            from echo_server import server  # type: ignore[import-not-found]
        finally:
            sys.path.remove(str(ECHO_SERVER.parent))
        self.server = server

    def app(self) -> Any:
        """Return the fixture's streamable-HTTP ASGI app.

        Returns:
            The Starlette app of the MCP SDK server.
        """
        configure_logging("WARNING")
        app: Any = self.server.streamable_http_app()
        return app


@contextlib.asynccontextmanager
async def _echo_http() -> AsyncIterator[str]:
    """Serve the echo fixture over streamable HTTP until the block ends.

    Yields:
        The fixture's MCP endpoint.
    """
    app = _EchoApp().app()
    config = uvicorn.Config(app, host=LISTEN_ADDRESS, port=0, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_for_listening(server)
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://{LISTEN_ADDRESS}:{port}{MCP_PATH}"
    finally:
        server.should_exit = True
        await task


def _echo_stdio() -> list[str]:
    """Return the command that serves the echo fixture on stdio.

    Returns:
        ``[python, echo_server.py]``.
    """
    return [sys.executable, str(ECHO_SERVER)]


def _proxy_stdio() -> list[str]:
    """Return the command that serves ``skeptic proxy stdio`` to the fixture.

    Returns:
        ``[python, -m, skeptic_agent.cli, proxy, stdio, --, python, echo_server.py]``.
    """
    return [sys.executable, "-m", "skeptic_agent.cli", "proxy", "stdio", "--", *_echo_stdio()]


@contextlib.asynccontextmanager
async def _session(command: Sequence[str]) -> AsyncIterator[ClientSession]:
    """Open one initialized stdio session to a command.

    Args:
        command: The server command and its arguments.

    Yields:
        The initialized session.
    """
    params = StdioServerParameters(
        command=command[0], args=list(command[1:]), env=_env(), cwd=str(ROOT)
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


async def _call_and_check(session: ClientSession, text: str) -> None:
    """Call ``echo`` and assert the reply echoes ``text``.

    Args:
        session: The initialized session.
        text: The text to send and expect back.

    Raises:
        RuntimeError: When the server answers with an error or the text differs.
    """
    result = await session.call_tool("echo", {"text": text})
    if result.is_error or _first_text(result) != text:
        raise RuntimeError(f"unexpected echo result for {text!r}: {result}")


def _first_text(result: "types.CallToolResult | types.Result") -> str:
    """Return the text of the first content block of a tool result.

    Args:
        result: The tool result.

    Returns:
        The first block's text, or ``""`` when there is none.
    """
    if not isinstance(result, types.CallToolResult) or not result.content:
        return ""
    block = result.content[0]
    return block.text if isinstance(block, types.TextContent) else ""


async def _timed_stdio(session: ClientSession, text: str) -> float:
    """Time one ``tools/call`` on an open session.

    Args:
        session: The initialized session.
        text: The text argument.

    Returns:
        The call's wall time in seconds.
    """
    started = time.perf_counter()
    await _call_and_check(session, text)
    return time.perf_counter() - started


async def _stdio_pairs(count: int, warmup: int) -> list[float]:
    """Measure the stdio proxy's added latency on one session pair.

    One direct session and one proxied session stay open for every sample: each
    sample times a proxied call, then a direct call with the same arguments, and
    reports their difference (paired samples cancel the run-to-run jitter of
    the machine).

    Args:
        count: The number of samples.
        warmup: The untimed calls at the start of each session.

    Returns:
        One latency difference in seconds per sample.
    """
    samples: list[float] = []
    async with _session(_echo_stdio()) as direct, _session(_proxy_stdio()) as proxied:
        for index in range(warmup):
            await _call_and_check(direct, f"{PAYLOAD}-warmup-{index}")
            await _call_and_check(proxied, f"{PAYLOAD}-warmup-{index}")
        for index in range(count):
            text = f"{PAYLOAD}-{index}"
            through = await _timed_stdio(proxied, text)
            straight = await _timed_stdio(direct, text)
            samples.append(through - straight)
    return samples


async def bench_stdio(count: int, warmup: int) -> list[float]:
    """Measure the stdio proxy's added latency over ``count`` paired calls.

    Args:
        count: The number of samples.
        warmup: The untimed calls per session.

    Returns:
        One latency difference in seconds per sample.
    """
    return await _stdio_pairs(count, warmup)


def _call_body(request_id: int, text: str) -> dict[str, Any]:
    """Build one ``tools/call`` request.

    Args:
        request_id: The JSON-RPC id.
        text: The text argument.

    Returns:
        The request object.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": "echo", "arguments": {"text": text}},
    }


def _initialize_body() -> dict[str, Any]:
    """Build the handshake that opens a session on the echo fixture.

    The fixture's protocol version is the last legacy one, so the handshake is
    an ``initialize`` request whose reply is an event stream with the session
    id in its headers.

    Returns:
        The ``initialize`` request.
    """
    return {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": SESSION_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "skeptic-bench", "version": "1"},
        },
    }


def _session_headers(reply: httpx.Response) -> dict[str, str]:
    """Return the headers every later message of a session must carry.

    Args:
        reply: The handshake reply.

    Returns:
        The JSON content type plus the session id, when the server gave one.
    """
    headers = {"Content-Type": "application/json"}
    session_id = reply.headers.get("mcp-session-id")
    if session_id is not None:
        headers["Mcp-Session-Id"] = session_id
    return headers


async def _open_session(client: httpx.AsyncClient, url: str) -> dict[str, str]:
    """Complete the handshake with an endpoint.

    Args:
        client: The HTTP client.
        url: The MCP endpoint.

    Returns:
        The headers for the session's later messages.
    """
    reply = await client.post(
        url,
        headers={"Content-Type": "application/json"},
        content=_encode(_initialize_body()),
    )
    if reply.status_code != 200:
        raise RuntimeError(f"the handshake answered {reply.status_code}")
    headers = _session_headers(reply)
    await client.post(
        url, headers=headers, content=b'{"jsonrpc":"2.0","method":"notifications/initialized"}'
    )
    return headers


def _reply_payload(body: str) -> dict[str, Any]:
    """Decode a JSON or event-stream reply body.

    Args:
        body: The response body.

    Returns:
        The first JSON-RPC message in the body.

    Raises:
        ValueError: When the body carries no JSON message.
    """
    for line in body.splitlines():
        if line.startswith("data: "):
            return dict(json.loads(line[len("data: ") :]))
    return dict(json.loads(body))


def _encode(value: dict[str, Any]) -> bytes:
    """Encode a request body the compact way a client writes it.

    Args:
        value: The request object.

    Returns:
        The UTF-8 body.
    """
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


async def _timed_http(
    client: httpx.AsyncClient, headers: dict[str, str], url: str, request_id: int, text: str
) -> float:
    """Time one ``tools/call`` against an HTTP endpoint on an open session.

    Args:
        client: The HTTP client.
        headers: The session headers from ``_open_session``.
        url: The MCP endpoint.
        request_id: The JSON-RPC id.
        text: The text argument.

    Returns:
        The call's wall time in seconds.

    Raises:
        RuntimeError: When the endpoint does not echo ``text``.
    """
    started = time.perf_counter()
    reply = await client.post(url, headers=headers, content=_encode(_call_body(request_id, text)))
    elapsed = time.perf_counter() - started
    if reply.status_code != 200 or _first_text_http(reply.text) != text:
        raise RuntimeError(f"unexpected HTTP reply: {reply.status_code} {reply.text[:200]}")
    return elapsed


def _first_text_http(body: str) -> str:
    """Return the echoed text of an HTTP reply.

    Args:
        body: The response body.

    Returns:
        The first content block's text.
    """
    payload = _reply_payload(body)
    return str(payload["result"]["content"][0]["text"])


async def bench_http(count: int, warmup: int) -> list[float]:
    """Measure the HTTP proxy's added latency over ``count`` paired calls.

    One direct session and one proxied session stay open for every sample, and
    both live until the block ends. Each sample times a proxied call,
    then a direct call with the same body, and reports their difference. The
    proxy is the same ``HttpProxy`` the CLI serves, in this process.

    Args:
        count: The number of samples.
        warmup: The untimed calls per endpoint.

    Returns:
        One latency difference in seconds per sample.
    """
    samples: list[float] = []
    async with (
        _echo_http() as upstream,
        _served(upstream) as proxied_url,
        httpx.AsyncClient(timeout=STARTUP_SECONDS) as client,
    ):
        direct_headers = await _open_session(client, upstream)
        proxied_headers = await _open_session(client, proxied_url)
        for index in range(warmup):
            text = f"{PAYLOAD}-warmup-{index}"
            await _timed_http(client, direct_headers, upstream, index, text)
            await _timed_http(client, proxied_headers, proxied_url, index, text)
        for index in range(count):
            text = f"{PAYLOAD}-{index}"
            through = await _timed_http(client, proxied_headers, proxied_url, index, text)
            straight = await _timed_http(client, direct_headers, upstream, index + warmup, text)
            samples.append(through - straight)
    return samples


async def _run_stdio_client(client_index: int, calls: int) -> tuple[int, int]:
    """Drive one stdio session through ``calls`` calls and check every reply.

    Args:
        client_index: The session number, part of every payload and id.
        calls: The number of calls.

    Returns:
        ``(errors, mismatches)``.
    """
    errors = 0
    mismatches = 0
    async with _session(_proxy_stdio()) as session:
        for call in range(calls):
            expected = f"{client_index}:{call}"
            try:
                result = await session.call_tool("echo", {"text": expected})
            except Exception:
                errors += 1
                continue
            if _first_text(result) != expected:
                mismatches += 1
    return errors, mismatches


async def bench_stdio_concurrency(clients: int, calls: int) -> dict[str, int]:
    """Run ``clients`` concurrent stdio sessions, each with ``calls`` calls.

    Args:
        clients: The number of concurrent sessions.
        calls: The number of calls per session.

    Returns:
        ``sessions``, ``calls``, ``errors`` and ``mismatches``.
    """
    outcomes = await asyncio.gather(*(_run_stdio_client(index, calls) for index in range(clients)))
    errors = sum(item[0] for item in outcomes)
    mismatches = sum(item[1] for item in outcomes)
    return {
        "sessions": clients,
        "calls": clients * calls,
        "errors": errors + mismatches,
        "mismatches": mismatches,
    }


async def _run_http_client(client_index: int, calls: int, url: str) -> tuple[int, int]:
    """Drive one HTTP client through ``calls`` calls and check every reply.

    Args:
        client_index: The client number, part of every payload.
        calls: The number of calls.
        url: The MCP endpoint.

    Returns:
        ``(errors, mismatches)``.
    """
    errors = 0
    mismatches = 0
    async with httpx.AsyncClient(timeout=STARTUP_SECONDS) as client:
        try:
            headers = await _open_session(client, url)
        except (httpx.HTTPError, RuntimeError):
            return calls, 0
        for call in range(calls):
            expected = f"{client_index}:{call}"
            request_id = client_index * calls + call + 1
            try:
                reply = await client.post(
                    url, headers=headers, content=_encode(_call_body(request_id, expected))
                )
            except httpx.HTTPError:
                errors += 1
                continue
            if reply.status_code != 200:
                errors += 1
                continue
            payload = _reply_payload(reply.text)
            if payload.get("id") != request_id or _first_text_http(reply.text) != expected:
                mismatches += 1
    return errors, mismatches


async def bench_http_concurrency(clients: int, calls: int) -> dict[str, int]:
    """Run ``clients`` concurrent HTTP clients, each with ``calls`` calls.

    Args:
        clients: The number of concurrent clients.
        calls: The number of calls per client.

    Returns:
        ``sessions``, ``calls``, ``errors`` and ``mismatches``.
    """
    async with _echo_http() as upstream, _served(upstream) as url:
        outcomes = await asyncio.gather(
            *(_run_http_client(index, calls, url) for index in range(clients))
        )
    errors = sum(item[0] for item in outcomes)
    mismatches = sum(item[1] for item in outcomes)
    return {
        "sessions": clients,
        "calls": clients * calls,
        "errors": errors + mismatches,
        "mismatches": mismatches,
    }


def _report_line(name: str, summary: dict[str, float], passed: bool) -> None:
    """Print one transport's summary.

    Args:
        name: The transport name.
        summary: The summary from ``_summary``.
        passed: Whether the acceptance passed.
    """
    verdict = "PASS" if passed else "FAIL"
    print(
        f"{name:<5} n={int(summary['count']):<5} p50={summary['p50']:.3f}ms "
        f"p90={summary['p90']:.3f}ms p99={summary['p99']:.3f}ms "
        f"mean={summary['mean']:.3f}ms max={summary['max']:.3f}ms {verdict}"
    )


async def _run(args: argparse.Namespace) -> int:
    """Run the benchmarks selected on the command line.

    Args:
        args: The parsed arguments.

    Returns:
        ``0`` when every selected acceptance passes, else ``1``.
    """
    report: dict[str, Any] = {"python": sys.version.split()[0], "platform": sys.platform}
    passed = True
    if "stdio" in args.only:
        summary = _summary(await bench_stdio(args.count, args.warmup))
        passed = passed and _passes(summary)
        _report_line("stdio", summary, _passes(summary))
        report["stdio"] = summary
    if "http" in args.only:
        summary = _summary(await bench_http(args.count, args.warmup))
        passed = passed and _passes(summary)
        _report_line("http", summary, _passes(summary))
        report["http"] = summary
    if "concurrency" in args.only:
        stdio = await bench_stdio_concurrency(args.clients, args.calls)
        http = await bench_http_concurrency(args.clients, args.calls)
        passed = passed and stdio["errors"] == 0 and http["errors"] == 0
        report["concurrency"] = {"stdio": stdio, "http": http}
        print(f"concurrency stdio={stdio}")
        print(f"concurrency http={http}")
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"wrote {args.report}")
    print(f"acceptance p50<{P50_LIMIT_MS}ms p99<{P99_LIMIT_MS}ms: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: The arguments, or ``None`` for ``sys.argv``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Benchmark the Skeptic proxy overhead (P17).")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=["stdio", "http", "concurrency"],
        default=["stdio", "http", "concurrency"],
        help="The benchmarks to run (default: all).",
    )
    parser.add_argument("--count", type=int, default=5000, help="Latency samples per transport.")
    parser.add_argument("--warmup", type=int, default=3, help="Warm-up calls per session.")
    parser.add_argument("--clients", type=int, default=50, help="Concurrent clients.")
    parser.add_argument("--calls", type=int, default=100, help="Calls per client.")
    parser.add_argument("--report", type=Path, default=None, help="Write the JSON report here.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark.

    Args:
        argv: The arguments, or ``None`` for ``sys.argv``.

    Returns:
        ``0`` when every selected acceptance passes, else ``1``.
    """
    temp = Path(tempfile.gettempdir()).resolve()
    if temp != ROOT and ROOT not in temp.parents:
        print(f"warning: TEMP lies outside {ROOT}: {temp}", file=sys.stderr)
    return asyncio.run(_run(parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
