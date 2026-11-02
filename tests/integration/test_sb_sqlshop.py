"""Integration tests: the sb_sqlshop sandbox (S9.2, S34).

Every one of the three tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_sqlshop`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run
sqlshop`` starts the same server, and the read-only state file is written at
startup (S9.1 item 4).
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
from skeptic_agent.sandboxes.sb_sqlshop import TOOLS
from skeptic_agent.sandboxes.sb_sqlshop import server as sqlshop
from skeptic_agent.sandboxes.sb_sqlshop.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"get_schema", "run_query", "run_query_replica"}


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
    """Serve sb_sqlshop over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_sqlshop",
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
        args=["-m", "skeptic_agent.sandboxes.sb_sqlshop"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run sqlshop``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "sqlshop"],
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
    fresh = sqlshop.build_state()
    return SandboxState(fresh.data, tmp_path / "state.json")


def _read_state(path: Path) -> dict[str, Any]:
    """Read the state file as JSON.

    Args:
        path: The state file.

    Returns:
        The decoded state.
    """
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return body


@pytest.mark.asyncio
async def test_get_schema_success(tmp_path: Path) -> None:
    """The schema names the four S9.2 tables and their columns."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_schema", {})
    structured = result.structured_content
    assert structured is not None
    assert [table["name"] for table in structured["tables"]] == list(sqlshop.TABLES)
    products = structured["tables"][0]
    assert [column["name"] for column in products["columns"]] == [
        "product_id",
        "name",
        "category",
        "price",
        "stock",
    ]
    assert products["columns"][0]["primary_key"] is True
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_get_schema_misuse_unexpected_argument(tmp_path: Path) -> None:
    """``get_schema`` takes no arguments; an unexpected one is an error."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_schema", {"table": "products"})
    assert result.is_error
    assert "table" in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_run_query_success(tmp_path: Path) -> None:
    """A SELECT returns the S9.2 columns, rows and row_count."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "run_query",
            {"sql": "SELECT product_id, name, price FROM products ORDER BY product_id LIMIT 2"},
        )
    structured = result.structured_content
    assert structured is not None
    assert structured["columns"] == ["product_id", "name", "price"]
    assert structured["row_count"] == 2
    assert structured["rows"][0] == ["P-1001", "Atlas Arm X1", 665.87]


@pytest.mark.asyncio
async def test_run_query_replica_matches_the_primary(tmp_path: Path) -> None:
    """The alternate returns the same committed rows."""
    sql = "SELECT COUNT(*) AS n FROM order_items"
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        primary = await client.call_tool("run_query", {"sql": sql})
        replica = await client.call_tool("run_query_replica", {"sql": sql})
    assert primary.structured_content is not None
    assert replica.structured_content is not None
    assert primary.structured_content == replica.structured_content
    assert replica.structured_content["rows"] == [[300]]


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("", "must not be empty"),
        ("   ", "must not be empty"),
        ("DELETE FROM products", "only SELECT"),
        ("UPDATE products SET price = 0", "only SELECT"),
        ("INSERT INTO products VALUES ('P-X', 'X', 'x', 1, 1)", "only SELECT"),
        ("DROP TABLE products", "only SELECT"),
        ("SELECT * FROM products; DELETE FROM products", "only one SQL statement"),
        ("SELECT * FROM missing_table", "SQL error"),
    ],
)
@pytest.mark.asyncio
async def test_run_query_misuse(tmp_path: Path, sql: str, reason: str) -> None:
    """Non-SELECT text, several statements and SQL errors are business errors."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        result = await client.call_tool("run_query", {"sql": sql})
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DELETE FROM customers", "only SELECT"),
        ("SELECT * FROM orders; DROP TABLE orders", "only one SQL statement"),
        ("SELECT nope FROM orders", "SQL error"),
    ],
)
@pytest.mark.asyncio
async def test_run_query_replica_misuse(tmp_path: Path, sql: str, reason: str) -> None:
    """The replica applies the same SELECT-only rule."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        result = await client.call_tool("run_query_replica", {"sql": sql})
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and read-only annotations."""
    async with Client(sqlshop.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
    assert tools["run_query"].output_schema is not None
    assert set(tools["run_query"].output_schema["required"]) == {
        "columns",
        "rows",
        "row_count",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the three tools."""
    for mode in ("auto", "legacy"):
        async with Client(sqlshop.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("run_query", {"sql": "SELECT COUNT(*) FROM products"})
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [[40]]


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the read-only state file appears stamped at startup."""
    path = tmp_path / "state.json"
    state = sqlshop.build_state()
    state.state_file = path
    sqlshop.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert body["database"] == "shop.sql"
    assert body["tables"] == list(sqlshop.TABLES)


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_sqlshop`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("run_query", {"sql": "SELECT COUNT(*) FROM orders"})
        assert result.structured_content is not None
        assert result.structured_content["rows"] == [[120]]


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run sqlshop`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_schema", {})
        assert result.structured_content is not None
        assert len(result.structured_content["tables"]) == 4


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and writes the startup state file."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool(
                "run_query_replica", {"sql": "SELECT COUNT(*) FROM customers"}
            )
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [[40]]
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert body["database"] == "shop.sql"


def test_tool_specs_are_the_three_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools, all read-only."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert all(not spec.write for spec in TOOLS)
    assert generate.PRODUCT_COUNT == 40
    assert generate.ORDER_ITEM_COUNT == 300
