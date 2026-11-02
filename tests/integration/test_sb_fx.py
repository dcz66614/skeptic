"""Integration tests: the sb_fx sandbox (S9.2, S31).

Every one of the four tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_fx`` starts over stdio, both
protocol generations can list and call the tools, and a state file is
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
from skeptic_agent.sandboxes.sb_fx import TOOLS
from skeptic_agent.sandboxes.sb_fx import server as fx
from skeptic_agent.sandboxes.sb_fx.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"list_currencies", "get_rate", "get_rate_backup", "convert"}
DAY = "2026-11-01"


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
    """Serve sb_fx over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_fx",
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
        args=["-m", "skeptic_agent.sandboxes.sb_fx"],
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
    return SandboxState({"rates": fx.load_rates()}, tmp_path / "state.json")


def _expected_rate(base: str, quote: str) -> float:
    """Return the primary quote-per-base rate from the generator.

    Args:
        base: The base currency.
        quote: The quote currency.

    Returns:
        The rate, rounded to six decimals.
    """
    returns = generate.build_rates()
    return round(returns[quote][DAY] / returns[base][DAY], 6)


@pytest.mark.asyncio
async def test_list_currencies_success(tmp_path: Path) -> None:
    """S9.2: the 7 currencies."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_currencies", {})
    assert result.structured_content == {"currencies": list(fx.CURRENCY_ORDER)}


@pytest.mark.asyncio
async def test_get_rate_misuse_rejects_an_unquoted_code(tmp_path: Path) -> None:
    """The argument is typed as a string; a bare object is refused."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "get_rate", {"base": {"code": "USD"}, "quote": "CNY", "date": DAY}
        )
    assert result.is_error
    assert "valid string" in _text(result)


@pytest.mark.asyncio
async def test_get_rate_success(tmp_path: Path) -> None:
    """The primary tool returns the S9.2 rate fields."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_rate", {"base": "USD", "quote": "CNY", "date": DAY})
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {"base", "quote", "date", "rate", "unit", "source"}
    assert structured["base"] == "USD"
    assert structured["quote"] == "CNY"
    assert structured["date"] == DAY
    assert structured["rate"] == _expected_rate("USD", "CNY")
    assert structured["unit"] == "quote_per_base"
    assert structured["source"] == "primary"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_get_rate_accepts_lower_case_codes(tmp_path: Path) -> None:
    """Currency codes are case-insensitive."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_rate", {"base": "usd", "quote": "eur", "date": DAY})
    assert result.structured_content is not None
    assert result.structured_content["base"] == "USD"
    assert result.structured_content["quote"] == "EUR"


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"base": "USD", "quote": "XYZ", "date": DAY}, "unknown currency"),
        ({"base": "USD", "quote": "CNY", "date": "2026-09-01"}, "no rates"),
        ({"base": "USD", "quote": "CNY", "date": "next week"}, "invalid date"),
    ],
)
@pytest.mark.asyncio
async def test_get_rate_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """An unknown currency, a day outside the window and a bad date are errors."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_rate", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_rate_backup_success(tmp_path: Path) -> None:
    """The alternate tool quotes the same pair 0.2% worse, from a pair string."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_rate_backup", {"pair": "USD/CNY", "date": DAY})
    structured = result.structured_content
    assert structured is not None
    assert structured["base"] == "USD"
    assert structured["quote"] == "CNY"
    assert structured["source"] == "backup"
    primary = _expected_rate("USD", "CNY")
    assert float(structured["rate"]) < primary
    assert abs(float(structured["rate"]) - primary * (1.0 - fx.BACKUP_SPREAD)) < 1e-6


@pytest.mark.asyncio
async def test_get_rate_backup_misuse_bad_pair(tmp_path: Path) -> None:
    """A pair without the slash is a business error."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_rate_backup", {"pair": "USDCNY", "date": DAY})
    assert result.is_error
    assert _text(result) == "Error: invalid pair 'USDCNY', expected BASE/QUOTE"


@pytest.mark.asyncio
async def test_convert_success(tmp_path: Path) -> None:
    """The conversion reports amount, rate, result and the result currency."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "convert", {"amount": 100, "base": "EUR", "quote": "USD", "date": DAY}
        )
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {"amount", "base", "quote", "date", "rate", "result", "currency"}
    assert structured["amount"] == 100.0
    assert structured["rate"] == _expected_rate("EUR", "USD")
    assert structured["result"] == pytest.approx(100 * _expected_rate("EUR", "USD"))
    assert structured["currency"] == "USD"


@pytest.mark.asyncio
async def test_convert_accepts_a_negative_amount(tmp_path: Path) -> None:
    """A negative amount is a refund and converts like any other."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "convert", {"amount": -50, "base": "USD", "quote": "CNY", "date": DAY}
        )
    assert result.structured_content is not None
    assert result.structured_content["result"] < 0


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"amount": 0, "base": "USD", "quote": "CNY", "date": DAY}, "must not be zero"),
        ({"amount": 10.5, "base": "USD", "quote": "JPY", "date": DAY}, "decimals for JPY"),
        ({"amount": 10, "base": "USD", "quote": "XYZ", "date": DAY}, "unknown currency"),
    ],
)
@pytest.mark.asyncio
async def test_convert_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """Zero, too fine for the quote currency, or an unknown code are errors."""
    async with Client(fx.server(_state(tmp_path))) as client:
        result = await client.call_tool("convert", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_read_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema and the read-only hints on every tool."""
    async with Client(fx.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
    assert tools["get_rate"].output_schema is not None
    assert set(tools["get_rate"].output_schema["required"]) == {
        "base",
        "quote",
        "date",
        "rate",
        "unit",
        "source",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the four tools."""
    for mode in ("auto", "legacy"):
        async with Client(fx.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("list_currencies", {})
            assert result.structured_content == {"currencies": list(fx.CURRENCY_ORDER)}


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the full table, stamped."""
    path = tmp_path / "state.json"
    fx.server(SandboxState({"rates": fx.load_rates()}, path))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert set(body["rates"]) == set(generate.CURRENCIES)
    assert body["rates"]["USD"][DAY] == 1.0


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_fx`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_rate", {"base": "USD", "quote": "JPY", "date": DAY})
        assert result.structured_content is not None
        assert result.structured_content["quote"] == "JPY"


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and writes the ``--state-file`` it was given."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("list_currencies", {})
            assert result.structured_content == {"currencies": list(fx.CURRENCY_ORDER)}
    body = json.loads(path.read_text(encoding="utf-8"))
    assert set(body["rates"]) == set(generate.CURRENCIES)


def test_tool_specs_are_the_four_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools, all read-only."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert all(not spec.write for spec in TOOLS)
