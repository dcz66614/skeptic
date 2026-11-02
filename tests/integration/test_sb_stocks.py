"""Integration tests: the sb_stocks sandbox (S9.2, S32).

Every one of the five tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_stocks`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run
stocks`` starts the same server, and a state file is written at startup (the
sandbox is all-read, so there is no later write).
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
from skeptic_agent.sandboxes.sb_stocks import TOOLS
from skeptic_agent.sandboxes.sb_stocks import server as stocks
from skeptic_agent.sandboxes.sb_stocks.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {
    "get_quote",
    "get_quote_delayed",
    "get_history",
    "get_company_profile",
    "screen",
}


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
    """Serve sb_stocks over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_stocks",
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
        args=["-m", "skeptic_agent.sandboxes.sb_stocks"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run stocks``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "stocks"],
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
    return SandboxState({"market": stocks.load_market()}, tmp_path / "state.json")


@pytest.mark.asyncio
async def test_get_quote_success(tmp_path: Path) -> None:
    """The primary tool returns the S9.2 quote fields from the committed close."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_quote", {"ticker": "ACME"})
    structured = result.structured_content
    committed = json.loads(stocks.MARKET_FILE.read_text(encoding="utf-8"))["ACME"]
    assert structured is not None
    assert set(structured) == {"ticker", "price", "currency", "change_pct", "as_of"}
    assert structured["ticker"] == "ACME"
    assert structured["price"] == committed["price"]
    assert structured["currency"] == "USD"
    assert structured["as_of"] == "2026-10-30T20:00:00Z"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_get_quote_accepts_lower_case_tickers(tmp_path: Path) -> None:
    """Ticker arguments are case-insensitive."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_quote", {"ticker": "acme"})
    assert result.structured_content is not None
    assert result.structured_content["ticker"] == "ACME"


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"ticker": "NOPE"}, "unknown ticker"),
        ({"ticker": 42}, "valid string"),
    ],
)
@pytest.mark.asyncio
async def test_get_quote_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An unknown ticker and a non-string ticker are business errors."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_quote", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_quote_delayed_success(tmp_path: Path) -> None:
    """The alternate quote lags the primary by 15 minutes."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_quote_delayed", {"ticker": "BOLT"})
    structured = result.structured_content
    assert structured is not None
    assert structured["ticker"] == "BOLT"
    assert structured["as_of"] == "2026-10-30T19:45:00Z"


@pytest.mark.asyncio
async def test_get_quote_delayed_misuse_unknown_ticker(tmp_path: Path) -> None:
    """The alternate tool reports an unknown ticker as a business error."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_quote_delayed", {"ticker": "ZZZZ"})
    assert result.is_error
    assert _text(result) == "Error: unknown ticker 'ZZZZ'"


@pytest.mark.asyncio
async def test_get_history_success(tmp_path: Path) -> None:
    """The history returns the bars in the inclusive window, oldest first."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_history", {"ticker": "ACME", "start": "2026-10-26", "end": "2026-10-30"}
        )
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {"ticker", "bars"}
    assert len(structured["bars"]) == 5
    dates = [bar["date"] for bar in structured["bars"]]
    assert dates == sorted(dates)
    assert dates[0] == "2026-10-26"
    assert dates[-1] == "2026-10-30"
    for bar in structured["bars"]:
        assert set(bar) == {"date", "open", "high", "low", "close", "volume"}
        assert bar["low"] <= bar["open"] <= bar["high"]
        assert bar["low"] <= bar["close"] <= bar["high"]


@pytest.mark.asyncio
async def test_get_history_returns_the_last_close_as_the_quote_price(
    tmp_path: Path,
) -> None:
    """A quote's price is the last bar's close, so both tools agree."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        quote = await client.call_tool("get_quote", {"ticker": "HELX"})
        history = await client.call_tool(
            "get_history", {"ticker": "HELX", "start": "2026-10-30", "end": "2026-10-30"}
        )
    assert quote.structured_content is not None
    assert history.structured_content is not None
    assert quote.structured_content["price"] == history.structured_content["bars"][0]["close"]


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"ticker": "NOPE", "start": "2026-10-26", "end": "2026-10-30"}, "unknown ticker"),
        ({"ticker": "ACME", "start": "2026-13-01", "end": "2026-10-30"}, "invalid start"),
        (
            {"ticker": "ACME", "start": "2026-11-10", "end": "2026-11-12"},
            "after the last trading day",
        ),
        ({"ticker": "ACME", "start": "2026-10-30", "end": "2026-10-26"}, "is after end"),
        ({"ticker": "ACME", "start": "2026-10-24", "end": "2026-10-25"}, "no trading bars"),
    ],
)
@pytest.mark.asyncio
async def test_get_history_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """An unknown ticker and bad windows are business errors."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_history", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_company_profile_success(tmp_path: Path) -> None:
    """The profile returns the company's S9.2 fields."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_company_profile", {"ticker": "CRUX"})
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {
        "ticker",
        "name",
        "sector",
        "currency",
        "listed_at",
        "employees",
        "headquarters",
    }
    assert structured["ticker"] == "CRUX"
    assert structured["name"] == "Crux Analytics"
    assert structured["sector"] == "technology"
    assert structured["currency"] == "USD"
    assert structured["employees"] == 780
    assert structured["headquarters"] == "Cambridge, USA"


@pytest.mark.asyncio
async def test_get_company_profile_misuse_unknown_ticker(tmp_path: Path) -> None:
    """An unknown ticker is a business error."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_company_profile", {"ticker": "NOPE"})
    assert result.is_error
    assert "unknown ticker" in _text(result)


@pytest.mark.asyncio
async def test_screen_success(tmp_path: Path) -> None:
    """Screen returns the sector's quotes inside the inclusive price range."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "screen", {"sector": "technology", "min_price": 150, "max_price": 250}
        )
    structured = result.structured_content
    assert structured is not None
    tickers = [quote["ticker"] for quote in structured["results"]]
    assert tickers == ["CRUX", "FLUX"]
    for quote in structured["results"]:
        assert 150 <= quote["price"] <= 250


@pytest.mark.asyncio
async def test_screen_with_no_match_is_an_empty_list(tmp_path: Path) -> None:
    """No match is a valid empty result, not an error."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "screen", {"sector": "energy", "min_price": 1000, "max_price": 2000}
        )
    assert not result.is_error
    assert result.structured_content == {"results": []}


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"sector": "aerospace", "min_price": 1, "max_price": 2}, "unknown sector"),
        ({"sector": "technology", "min_price": 300, "max_price": 100}, "must not exceed"),
        ({"sector": "technology", "min_price": "cheap", "max_price": 100}, "valid number"),
    ],
)
@pytest.mark.asyncio
async def test_screen_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An unknown sector, a reversed range and a non-number are errors."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        result = await client.call_tool("screen", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_read_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema and the read-only hints on every tool."""
    async with Client(stocks.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
    assert tools["get_quote"].output_schema is not None
    assert set(tools["get_quote"].output_schema["required"]) == {
        "ticker",
        "price",
        "currency",
        "change_pct",
        "as_of",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the five tools."""
    for mode in ("auto", "legacy"):
        async with Client(stocks.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("get_quote", {"ticker": "GRIT"})
            assert result.structured_content is not None
            assert result.structured_content["ticker"] == "GRIT"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the full market, stamped."""
    path = tmp_path / "state.json"
    stocks.server(SandboxState({"market": stocks.load_market()}, path))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert set(body["market"]) == set(generate.TICKERS)
    assert len(body["market"]["ACME"]["bars"]) == 60


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_stocks`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_company_profile", {"ticker": "DYNA"})
        assert result.structured_content is not None
        assert result.structured_content["sector"] == "logistics"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run stocks`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_quote", {"ticker": "ECHO"})
        assert result.structured_content is not None
        assert result.structured_content["ticker"] == "ECHO"


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and writes the ``--state-file`` it was given."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("get_quote", {"ticker": "FLUX"})
            assert result.structured_content is not None
            assert result.structured_content["ticker"] == "FLUX"
    body = json.loads(path.read_text(encoding="utf-8"))
    assert set(body["market"]) == set(generate.TICKERS)


def test_tool_specs_are_the_five_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools, all read-only."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert all(not spec.write for spec in TOOLS)
