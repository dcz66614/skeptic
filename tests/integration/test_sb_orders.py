"""Integration tests: the sb_orders sandbox (S9.2, S33).

Every one of the five tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_orders`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run
orders`` starts the same server, and the state file follows each write
(S9.1 item 4).
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
from skeptic_agent.sandboxes.sb_orders import TOOLS
from skeptic_agent.sandboxes.sb_orders import server as orders
from skeptic_agent.sandboxes.sb_orders.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {
    "list_orders",
    "get_order",
    "get_order_status",
    "cancel_order",
    "refund_order",
}
READ_TOOLS = {"list_orders", "get_order", "get_order_status"}
WRITE_TOOLS = {"cancel_order", "refund_order"}


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
    """Serve sb_orders over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_orders",
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
        args=["-m", "skeptic_agent.sandboxes.sb_orders"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run orders``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "orders"],
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
    fresh = orders.build_state()
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


def _committed() -> dict[str, dict[str, Any]]:
    """Read the committed order table.

    Returns:
        ``{order_id: order}``.
    """
    table: dict[str, dict[str, Any]] = json.loads(orders.ORDERS_FILE.read_text(encoding="utf-8"))
    return table


def _first_with_status(status: str) -> dict[str, Any]:
    """Return the first committed order with a status.

    Args:
        status: The wanted status.

    Returns:
        The order entry.
    """
    return next(order for order in _committed().values() if order["status"] == status)


@pytest.mark.asyncio
async def test_list_orders_success(tmp_path: Path) -> None:
    """A customer's orders come back with the S9.2 fields, in id order."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_orders", {"customer_id": "C-1001"})
    structured = result.structured_content
    assert structured is not None
    matches = structured["orders"]
    assert [order["id"] for order in matches] == sorted(order["id"] for order in matches)
    assert len(matches) == 3
    assert all(order["customer_id"] == "C-1001" for order in matches)
    assert set(matches[0]) == {
        "id",
        "customer_id",
        "status",
        "total",
        "currency",
        "items",
        "created_at",
    }
    assert all(order["currency"] == "USD" for order in matches)


@pytest.mark.asyncio
async def test_list_orders_status_filter(tmp_path: Path) -> None:
    """The optional status keeps only orders in that state."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "list_orders", {"customer_id": "C-1001", "status": "shipped"}
        )
    structured = result.structured_content
    assert structured is not None
    assert len(structured["orders"]) == 2
    assert all(order["status"] == "shipped" for order in structured["orders"])


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"customer_id": "C-9999"}, "unknown customer"),
        ({"customer_id": "C-1001", "status": "lost"}, "unknown status"),
    ],
)
@pytest.mark.asyncio
async def test_list_orders_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An unknown customer and an unknown status are business errors."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_orders", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_get_order_success(tmp_path: Path) -> None:
    """The order returns the committed total and line items."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_order", {"order_id": "O-2001"})
    structured = result.structured_content
    assert structured is not None
    assert structured["id"] == "O-2001"
    assert structured["customer_id"] == "C-1001"
    assert structured["status"] == "shipped"
    assert structured["total"] == 521.97
    assert structured["currency"] == "USD"
    assert structured["items"][0]["product_id"] == "P-102"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_get_order_misuse_unknown_order(tmp_path: Path) -> None:
    """An unknown order id is a business error."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_order", {"order_id": "O-9999"})
    assert result.is_error
    assert "unknown order" in _text(result)


@pytest.mark.asyncio
async def test_get_order_status_success(tmp_path: Path) -> None:
    """The status view returns the id and the current status."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_order_status", {"order_id": "O-2002"})
    assert result.structured_content == {"order_id": "O-2002", "status": "pending"}


@pytest.mark.asyncio
async def test_get_order_status_misuse_unknown_order(tmp_path: Path) -> None:
    """An unknown order id is a business error."""
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_order_status", {"order_id": "O-0000"})
    assert result.is_error
    assert "unknown order" in _text(result)


@pytest.mark.asyncio
async def test_cancel_order_success_and_state(tmp_path: Path) -> None:
    """Cancelling a pending order changes it and the state file follows."""
    pending = _first_with_status("pending")
    path = tmp_path / "state.json"
    state = orders.build_state()
    state.state_file = path
    async with Client(orders.server(state)) as client:
        result = await client.call_tool(
            "cancel_order",
            {"order_id": str(pending["id"]), "reason": "Customer changed their mind."},
        )
    assert result.structured_content == {
        "status": "ok",
        "order_id": str(pending["id"]),
        "new_status": "cancelled",
    }
    body = _read_state(path)
    assert body["orders"][str(pending["id"])]["status"] == "cancelled"
    assert body["refunds"] == []


@pytest.mark.parametrize(
    ("order", "arguments", "reason"),
    [
        (None, {"order_id": "O-9999", "reason": "nope"}, "unknown order"),
        ("shipped", {"reason": "too late"}, "only pending orders"),
        ("pending", {"reason": "   "}, "must not be empty"),
    ],
)
@pytest.mark.asyncio
async def test_cancel_order_misuse(
    tmp_path: Path, order: str | None, arguments: dict[str, str], reason: str
) -> None:
    """A non-pending order, an unknown id and an empty reason are errors."""
    if order is not None:
        arguments = {"order_id": str(_first_with_status(order)["id"]), **arguments}
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("cancel_order", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_refund_order_success_and_state(tmp_path: Path) -> None:
    """Refunding a delivered order appends the refund and updates the file."""
    delivered = _first_with_status("delivered")
    path = tmp_path / "state.json"
    state = orders.build_state()
    state.state_file = path
    async with Client(orders.server(state)) as client:
        result = await client.call_tool(
            "refund_order", {"order_id": str(delivered["id"]), "amount": 10.0}
        )
    assert result.structured_content == {
        "status": "ok",
        "order_id": str(delivered["id"]),
        "amount": 10.0,
        "currency": "USD",
    }
    body = _read_state(path)
    assert body["refunds"][-1]["order_id"] == str(delivered["id"])
    assert body["refunds"][-1]["amount"] == 10.0


@pytest.mark.asyncio
async def test_refund_order_misuse_not_delivered(tmp_path: Path) -> None:
    """Only a delivered order can be refunded."""
    pending = _first_with_status("pending")
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "refund_order", {"order_id": str(pending["id"]), "amount": 1.0}
        )
    assert result.is_error
    assert "only delivered orders" in _text(result)


@pytest.mark.asyncio
async def test_refund_order_misuse_amount_above_total(tmp_path: Path) -> None:
    """A refund larger than the order total is a business error."""
    delivered = _first_with_status("delivered")
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool(
            "refund_order",
            {"order_id": str(delivered["id"]), "amount": float(delivered["total"]) + 1.0},
        )
    assert result.is_error
    assert "exceeds the order total" in _text(result)


@pytest.mark.parametrize(
    ("order", "amount", "reason"),
    [
        (None, 1.0, "unknown order"),
        ("delivered", 0.0, "greater than zero"),
        ("delivered", -5.0, "greater than zero"),
    ],
)
@pytest.mark.asyncio
async def test_refund_order_misuse(
    tmp_path: Path, order: str | None, amount: float, reason: str
) -> None:
    """An unknown id and a non-positive amount are business errors."""
    order_id = "O-9999" if order is None else str(_first_with_status(order)["id"])
    async with Client(orders.server(_state(tmp_path))) as client:
        result = await client.call_tool("refund_order", {"order_id": order_id, "amount": amount})
    assert result.is_error
    assert reason in _text(result)


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and the right read/write hints."""
    async with Client(orders.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for name, tool in tools.items():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        if name in READ_TOOLS:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.idempotent_hint is True
        else:
            assert tool.annotations.read_only_hint is False
            assert tool.annotations.idempotent_hint is False
    assert tools["cancel_order"].annotations is not None
    assert tools["cancel_order"].annotations.destructive_hint is True
    assert tools["refund_order"].annotations is not None
    assert tools["refund_order"].annotations.destructive_hint is False
    assert tools["get_order"].output_schema is not None
    assert set(tools["get_order"].output_schema["required"]) == {
        "id",
        "customer_id",
        "status",
        "total",
        "currency",
        "items",
        "created_at",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the five tools."""
    for mode in ("auto", "legacy"):
        async with Client(orders.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("get_order", {"order_id": "O-2001"})
            assert result.structured_content is not None
            assert result.structured_content["id"] == "O-2001"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the S9.3 shape, stamped."""
    path = tmp_path / "state.json"
    state = orders.build_state()
    state.state_file = path
    orders.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["orders"]) == 120
    assert body["orders"]["O-2001"]["id"] == "O-2001"
    assert body["refunds"] == []


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_orders`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_order_status", {"order_id": "O-2001"})
        assert result.structured_content is not None
        assert result.structured_content["status"] == "shipped"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run orders`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_order", {"order_id": "O-2001"})
        assert result.structured_content is not None
        assert result.structured_content["customer_id"] == "C-1001"


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and the state file follows a write."""
    pending = _first_with_status("pending")
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool(
                "cancel_order", {"order_id": str(pending["id"]), "reason": "Over HTTP."}
            )
            assert result.structured_content is not None
    body = _read_state(path)
    assert body["orders"][str(pending["id"])]["status"] == "cancelled"


def test_tool_specs_are_the_five_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools with the right write flags."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert {spec.name for spec in TOOLS if spec.write} == WRITE_TOOLS
    assert generate.ORDER_COUNT == 120
    assert set(generate.STATUSES) == {"pending", "shipped", "delivered", "cancelled"}
