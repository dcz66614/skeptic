"""Integration tests: the sb_crm sandbox (S9.2, S32).

Every one of the five tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_crm`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run crm``
starts the same server, and the state file follows each write (S9.1 item 4).
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
from skeptic_agent.sandboxes.sb_crm import TOOLS
from skeptic_agent.sandboxes.sb_crm import server as crm
from skeptic_agent.sandboxes.sb_crm.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {
    "search_customers",
    "get_customer",
    "update_customer_email",
    "add_note",
    "list_notes",
}
READ_TOOLS = {"search_customers", "get_customer", "list_notes"}
WRITE_TOOLS = {"update_customer_email", "add_note"}


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
    """Serve sb_crm over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_crm",
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
        args=["-m", "skeptic_agent.sandboxes.sb_crm"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run crm``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "crm"],
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
    fresh = crm.build_state()
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
async def test_search_customers_by_city(tmp_path: Path) -> None:
    """A city query finds the customers in it, ordered by id."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_customers", {"query": "Paris"})
    structured = result.structured_content
    assert structured is not None
    matches = structured["customers"]
    assert matches
    assert all(customer["city"] == "Paris" for customer in matches)
    assert [customer["id"] for customer in matches] == sorted(
        customer["id"] for customer in matches
    )
    assert set(matches[0]) == {"id", "name", "email", "tier", "city", "created_at"}


@pytest.mark.asyncio
async def test_search_customers_empty_query_lists_all(tmp_path: Path) -> None:
    """An empty query lists every shared customer."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_customers", {"query": ""})
    assert result.structured_content is not None
    assert len(result.structured_content["customers"]) == 40


@pytest.mark.asyncio
async def test_search_customers_misuse_missing_query(tmp_path: Path) -> None:
    """The query is required; omitting it is an error result."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_customers", {})
    assert result.is_error
    assert "query" in _text(result)


@pytest.mark.asyncio
async def test_get_customer_success(tmp_path: Path) -> None:
    """The customer returns the S9.2 fields from the shared table."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_customer", {"customer_id": "C-1001"})
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {"id", "name", "email", "tier", "city", "created_at"}
    assert structured["id"] == "C-1001"
    assert structured["name"] == "Ada Castillo"
    assert structured["email"] == "ada.castillo.01@example.com"
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.parametrize("customer_id", ["C-9999", "not-a-customer"])
@pytest.mark.asyncio
async def test_get_customer_misuse(tmp_path: Path, customer_id: str) -> None:
    """An unknown customer id is a business error."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("get_customer", {"customer_id": customer_id})
    assert result.is_error
    assert "unknown customer" in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_update_customer_email_success_and_state(tmp_path: Path) -> None:
    """The write stores the email and the state file follows it."""
    path = tmp_path / "state.json"
    state = crm.build_state()
    state.state_file = path
    async with Client(crm.server(state)) as client:
        result = await client.call_tool(
            "update_customer_email",
            {"customer_id": "C-1004", "email": "dmitri.rossi@example.com"},
        )
    structured = result.structured_content
    assert structured == {
        "status": "ok",
        "customer_id": "C-1004",
        "email": "dmitri.rossi@example.com",
    }
    body = _read_state(path)
    assert body["customers"]["C-1004"]["email"] == "dmitri.rossi@example.com"


@pytest.mark.asyncio
async def test_update_customer_email_is_idempotent(tmp_path: Path) -> None:
    """Repeating the write returns the same result and the same state."""
    state = _state(tmp_path)
    async with Client(crm.server(state)) as client:
        first = await client.call_tool(
            "update_customer_email", {"customer_id": "C-1007", "email": "greta@example.com"}
        )
        second = await client.call_tool(
            "update_customer_email", {"customer_id": "C-1007", "email": "greta@example.com"}
        )
    assert first.structured_content == second.structured_content


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"customer_id": "C-9999", "email": "x@example.com"}, "unknown customer"),
        ({"customer_id": "C-1001", "email": "not-an-email"}, "invalid email"),
    ],
)
@pytest.mark.asyncio
async def test_update_customer_email_misuse(
    tmp_path: Path, arguments: dict[str, str], reason: str
) -> None:
    """An unknown id and an invalid email are errors that leave the state alone."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("update_customer_email", arguments)
    assert result.is_error
    assert reason in _text(result)


@pytest.mark.asyncio
async def test_add_note_success_and_state(tmp_path: Path) -> None:
    """A note is appended with a new id and the state file follows it."""
    path = tmp_path / "state.json"
    state = crm.build_state()
    state.state_file = path
    async with Client(crm.server(state)) as client:
        result = await client.call_tool(
            "add_note", {"customer_id": "C-1001", "text": "Called about renewal."}
        )
    structured = result.structured_content
    assert structured is not None
    assert structured["status"] == "ok"
    assert structured["customer_id"] == "C-1001"
    note_id = str(structured["note_id"])
    assert note_id > "N-3080"
    body = _read_state(path)
    assert any(note["id"] == note_id for note in body["notes"])


@pytest.mark.asyncio
async def test_add_note_is_not_idempotent(tmp_path: Path) -> None:
    """Two identical calls add two notes with different ids."""
    async with Client(crm.server(_state(tmp_path))) as client:
        first = await client.call_tool("add_note", {"customer_id": "C-1002", "text": "same"})
        second = await client.call_tool("add_note", {"customer_id": "C-1002", "text": "same"})
    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["note_id"] != second.structured_content["note_id"]


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"customer_id": "C-9999", "text": "hi"}, "unknown customer"),
        ({"customer_id": "C-1001", "text": "   "}, "must not be empty"),
        ({"customer_id": "C-1001", "text": "x" * 501}, "longer than 500"),
    ],
)
@pytest.mark.asyncio
async def test_add_note_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """An unknown id, empty text and oversized text are business errors."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("add_note", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_list_notes_success(tmp_path: Path) -> None:
    """The customer's two committed notes come back."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_notes", {"customer_id": "C-1001"})
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == {"notes"}
    assert len(structured["notes"]) == 2
    for note in structured["notes"]:
        assert note["customer_id"] == "C-1001"
        assert set(note) == {"id", "customer_id", "text", "created_at"}


@pytest.mark.asyncio
async def test_list_notes_misuse_unknown_customer(tmp_path: Path) -> None:
    """An unknown customer id is a business error."""
    async with Client(crm.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_notes", {"customer_id": "C-9999"})
    assert result.is_error
    assert "unknown customer" in _text(result)


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and the right read/write hints."""
    async with Client(crm.server(_state(tmp_path))) as client:
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
            assert tool.annotations.destructive_hint is False
    assert tools["update_customer_email"].annotations is not None
    assert tools["update_customer_email"].annotations.idempotent_hint is True
    assert tools["add_note"].annotations is not None
    assert tools["add_note"].annotations.idempotent_hint is False
    assert tools["get_customer"].output_schema is not None
    assert set(tools["get_customer"].output_schema["required"]) == {
        "id",
        "name",
        "email",
        "tier",
        "city",
        "created_at",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the five tools."""
    for mode in ("auto", "legacy"):
        async with Client(crm.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("get_customer", {"customer_id": "C-1002"})
            assert result.structured_content is not None
            assert result.structured_content["id"] == "C-1002"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with customers and notes, stamped."""
    path = tmp_path / "state.json"
    state = crm.build_state()
    state.state_file = path
    crm.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["customers"]) == 40
    assert len(body["notes"]) == 80
    assert body["customers"]["C-1001"]["name"] == "Ada Castillo"


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_crm`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_customer", {"customer_id": "C-1010"})
        assert result.structured_content is not None
        assert result.structured_content["tier"] == "gold"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run crm`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("get_customer", {"customer_id": "C-1001"})
        assert result.structured_content is not None
        assert result.structured_content["id"] == "C-1001"


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and the state file follows a write."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool(
                "add_note", {"customer_id": "C-1003", "text": "Over HTTP."}
            )
            assert result.structured_content is not None
    body = _read_state(path)
    assert any(note["text"] == "Over HTTP." for note in body["notes"])


def test_tool_specs_are_the_five_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools with the right write flags."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    writes = {spec.name for spec in TOOLS if spec.write}
    assert writes == WRITE_TOOLS
    idempotent = {spec.name for spec in TOOLS if spec.write and spec.idempotent}
    assert idempotent == {"update_customer_email"}
    assert generate.NOTES_PER_CUSTOMER == 2
