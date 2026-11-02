"""Integration tests: the sb_mail sandbox (S9.2, S35).

Every one of the four tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_mail`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run mail``
starts the same server, and the state file follows the write (S9.1 item 4).
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
from skeptic_agent.sandboxes.sb_mail import TOOLS
from skeptic_agent.sandboxes.sb_mail import server as mail
from skeptic_agent.sandboxes.sb_mail.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"list_inbox", "read_email", "search_mail", "send_email"}
READ_TOOLS = {"list_inbox", "read_email", "search_mail"}
WRITE_TOOLS = {"send_email"}

EMAIL_FIELDS = {"id", "from", "to", "subject", "body", "received_at"}


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
    """Serve sb_mail over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_mail",
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
        args=["-m", "skeptic_agent.sandboxes.sb_mail"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run mail``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "mail"],
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
    fresh = mail.build_state()
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
async def test_list_inbox_success(tmp_path: Path) -> None:
    """The default listing returns 20 of the 25 inbox messages, newest first."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_inbox", {})
    structured = result.structured_content
    assert structured is not None
    emails = structured["emails"]
    assert len(emails) == 20
    assert emails[0]["id"] == "M-1025"
    assert emails[-1]["id"] == "M-1006"
    for email in emails:
        assert set(email) == EMAIL_FIELDS
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_list_inbox_limit_and_outbox(tmp_path: Path) -> None:
    """A small limit keeps the newest messages; an empty outbox lists nothing."""
    async with Client(mail.server(_state(tmp_path))) as client:
        limited = await client.call_tool("list_inbox", {"folder": "inbox", "limit": 3})
        outbox = await client.call_tool("list_inbox", {"folder": "outbox"})
    assert limited.structured_content is not None
    assert [email["id"] for email in limited.structured_content["emails"]] == [
        "M-1025",
        "M-1024",
        "M-1023",
    ]
    assert outbox.structured_content == {"emails": []}


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"folder": "archive"}, "unknown folder"),
        ({"limit": 0}, "limit must be greater than zero"),
        ({"limit": 101}, "limit is greater than 100"),
    ],
)
@pytest.mark.asyncio
async def test_list_inbox_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An unknown folder and out-of-range limits are business errors."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_inbox", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_read_email_success(tmp_path: Path) -> None:
    """The email returns the committed fields, including the literal ``from``."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_email", {"email_id": "M-1001"})
    structured = result.structured_content
    assert structured is not None
    assert structured == {
        "id": "M-1001",
        "from": "ada.castillo.01@example.com",
        "to": "support@example.com",
        "subject": "Question about my latest invoice",
        "body": (
            "My order has not arrived yet. Could you check the delivery status? — Ada Castillo"
        ),
        "received_at": "2026-10-19T08:47:00Z",
    }
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_read_email_misuse_unknown_email(tmp_path: Path) -> None:
    """An unknown email id is a business error."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_email", {"email_id": "M-9999"})
    assert result.is_error
    assert "unknown email" in _text(result)


@pytest.mark.asyncio
async def test_search_mail_success(tmp_path: Path) -> None:
    """Every query term must occur; matches come back newest first."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_mail", {"query": "invoice INV-2041"})
    structured = result.structured_content
    assert structured is not None
    emails = structured["emails"]
    assert emails
    for email in emails:
        text = " ".join(str(email[field]) for field in EMAIL_FIELDS).lower()
        assert "invoice" in text
        assert "inv-2041" in text
    assert [email["received_at"] for email in emails] == sorted(
        (email["received_at"] for email in emails), reverse=True
    )


@pytest.mark.parametrize("query", ["", "   "])
@pytest.mark.asyncio
async def test_search_mail_misuse(tmp_path: Path, query: str) -> None:
    """An empty query is a business error."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_mail", {"query": query})
    assert result.is_error
    assert "query must not be empty" in _text(result)


@pytest.mark.asyncio
async def test_send_email_success_and_state(tmp_path: Path) -> None:
    """A send appends to the outbox, is readable, and updates the state file."""
    path = tmp_path / "state.json"
    state = mail.build_state()
    state.state_file = path
    async with Client(mail.server(state)) as client:
        result = await client.call_tool(
            "send_email",
            {
                "to": "ada@example.com",
                "subject": "Status update",
                "body": "The invoice was approved today.",
            },
        )
        sent_id = str(result.structured_content["message_id"]) if result.structured_content else ""
        reread = await client.call_tool("read_email", {"email_id": sent_id})
        outbox = await client.call_tool("list_inbox", {"folder": "outbox"})
    assert result.structured_content == {"status": "ok", "message_id": "M-5001"}
    assert reread.structured_content is not None
    assert reread.structured_content["from"] == "me@example.com"
    assert reread.structured_content["to"] == "ada@example.com"
    assert reread.structured_content["received_at"] == "2026-11-01T09:00:00Z"
    assert outbox.structured_content is not None
    assert [email["id"] for email in outbox.structured_content["emails"]] == ["M-5001"]
    body = _read_state(path)
    assert len(body["inbox"]) == 25
    assert body["outbox"][-1]["id"] == "M-5001"
    assert body["outbox"][-1]["to"] == "ada@example.com"


@pytest.mark.asyncio
async def test_send_email_is_not_idempotent(tmp_path: Path) -> None:
    """Two identical sends append two messages with different ids."""
    async with Client(mail.server(_state(tmp_path))) as client:
        first = await client.call_tool(
            "send_email", {"to": "ada@example.com", "subject": "same", "body": "same"}
        )
        second = await client.call_tool(
            "send_email", {"to": "ada@example.com", "subject": "same", "body": "same"}
        )
    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["message_id"] != second.structured_content["message_id"]


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"to": "not-an-address", "subject": "s", "body": "b"}, "invalid email address"),
        ({"to": "ada@example.com", "subject": "  ", "body": "b"}, "subject must not be empty"),
        ({"to": "ada@example.com", "subject": "s", "body": "  "}, "body must not be empty"),
        (
            {"to": "ada@example.com", "subject": "x" * 201, "body": "b"},
            "longer than 200",
        ),
    ],
)
@pytest.mark.asyncio
async def test_send_email_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """An invalid recipient and empty or oversized text are business errors."""
    async with Client(mail.server(_state(tmp_path))) as client:
        result = await client.call_tool("send_email", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and the right read/write hints."""
    async with Client(mail.server(_state(tmp_path))) as client:
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
            assert tool.annotations.idempotent_hint is False
    assert tools["read_email"].output_schema is not None
    assert set(tools["read_email"].output_schema["required"]) == EMAIL_FIELDS
    assert tools["send_email"].output_schema is not None
    assert set(tools["send_email"].output_schema["required"]) == {"status", "message_id"}


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the four tools."""
    for mode in ("auto", "legacy"):
        async with Client(mail.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("read_email", {"email_id": "M-1002"})
            assert result.structured_content is not None
            assert result.structured_content["id"] == "M-1002"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the inbox and an empty outbox."""
    path = tmp_path / "state.json"
    state = mail.build_state()
    state.state_file = path
    mail.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["inbox"]) == 25
    assert body["outbox"] == []
    assert body["inbox"][0]["id"] == "M-1001"


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_mail`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("read_email", {"email_id": "M-1001"})
        assert result.structured_content is not None
        assert result.structured_content["from"] == "ada.castillo.01@example.com"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run mail`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("list_inbox", {"limit": 2})
        assert result.structured_content is not None
        assert len(result.structured_content["emails"]) == 2


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and the state file follows the send."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool(
                "send_email", {"to": "ada@example.com", "subject": "Over HTTP", "body": "Hi."}
            )
            assert result.structured_content is not None
    body = _read_state(path)
    assert body["outbox"][-1]["subject"] == "Over HTTP"


def test_tool_specs_are_the_four_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools with the right write flags."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert {spec.name for spec in TOOLS if spec.write} == WRITE_TOOLS
    assert generate.EMAIL_COUNT == 25
    assert generate.MAILBOX == "support@example.com"
