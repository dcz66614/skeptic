"""Integration tests: the sb_common sandbox framework (S30).

The example sandbox has two tools over one state dict: ``get_count`` (read)
and ``add`` (write). It lives in ``tests/integration/fixtures/sb_example.py``
and is driven through the SDK client, both in-process for the fast checks and
as real subprocesses for the stdio and Streamable HTTP entry points.
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
from pydantic import BaseModel

from skeptic_agent.sandboxes.sb_common.server import (
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLE = FIXTURES / "sb_example.py"
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

READ_TOOL = "get_count"
WRITE_TOOL = "add"


class ReadArguments(BaseModel):
    """No arguments; the S9.1 read tools still publish an object schema."""


class Count(BaseModel):
    count: int


class AddArguments(BaseModel):
    by: int


class AddResult(BaseModel):
    status: str
    count: int


async def _get_count(arguments: ReadArguments, tool: Any) -> Count:
    """Return the current count.

    Args:
        arguments: The validated arguments, unused.
        tool: The bound ``SandboxTool``.

    Returns:
        The count.
    """
    del arguments
    return Count(count=int(tool.data["count"]))


async def _add(arguments: AddArguments, tool: Any) -> AddResult:
    """Add to the count and persist the state file.

    Args:
        arguments: The validated arguments.
        tool: The bound ``SandboxTool``.

    Returns:
        The new status and count.

    Raises:
        ToolFailure: When ``by`` is negative.
    """
    if arguments.by < 0:
        raise ToolFailure("cannot add a negative amount")
    tool.data["count"] = int(tool.data["count"]) + arguments.by
    tool.finish()
    return AddResult(status="ok", count=int(tool.data["count"]))


TOOLS = (
    ToolSpec(READ_TOOL, "Return the current count.", ReadArguments, Count, _get_count),
    ToolSpec(
        WRITE_TOOL,
        "Add to the count and write the state file.",
        AddArguments,
        AddResult,
        _add,
        write=True,
        destructive=False,
        idempotent=False,
    ),
)
"""The two tools the S30 acceptance line asks for: one read, one write."""


def _state_file(tmp_path: Path) -> Path:
    """Return the state file path inside a test's temp directory.

    Args:
        tmp_path: The pytest temp directory.

    Returns:
        ``<tmp_path>/state.json``.
    """
    return tmp_path / "state.json"


def _read_state(path: Path) -> dict[str, Any]:
    """Read the state file as JSON.

    Args:
        path: The state file.

    Returns:
        The decoded object.
    """
    body = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(body, dict)
    return body


def _text(result: Any) -> str:
    """Return the first text block of a tool result.

    Args:
        result: The ``CallToolResult``.

    Returns:
        The block's text.
    """
    return str(result.content[0].text)


def _pythonpath() -> str:
    """Return a ``PYTHONPATH`` that also finds the package source and the fixture.

    Returns:
        ``src``, the fixtures dir and the existing ``PYTHONPATH``, joined.
    """
    parts = [str(ROOT / "src"), str(FIXTURES)]
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


def _wait_for_port(port: int, process: subprocess.Popen[bytes] | None = None) -> None:
    """Wait until a local port accepts connections.

    Args:
        port: The port to poll.
        process: The child that must stay alive, when there is one.

    Raises:
        RuntimeError: When the port does not open or the child exits first.
    """
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError("the sandbox exited before it listened")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"port {port} did not open")


@contextlib.contextmanager
def _served_http(state_file: Path):
    """Serve the example sandbox over Streamable HTTP on a free port.

    Args:
        state_file: The state file the child writes.

    Yields:
        The ``http://127.0.0.1:<port>/mcp`` URL.
    """
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            str(EXAMPLE),
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
    """Return the stdio parameters for the example sandbox.

    Returns:
        How the client should launch ``sb_example.py``.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=[str(EXAMPLE)],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list the two tools and call them."""
    for mode in ("auto", "legacy"):
        state = SandboxState({"count": 0}, _state_file(tmp_path))
        server = make_server("example", TOOLS, state)
        async with Client(server, mode=mode) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(tools) == {READ_TOOL, WRITE_TOOL}
            read = await client.call_tool(READ_TOOL, {})
            assert read.structured_content == {"count": 0}
            written = await client.call_tool(WRITE_TOOL, {"by": 2})
            assert written.structured_content == {"status": "ok", "count": 2}


@pytest.mark.asyncio
async def test_tools_publish_both_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 items 5 and 6: both schemas exist and every read/write hint is set."""
    state = SandboxState({"count": 0}, _state_file(tmp_path))
    server = make_server("example", TOOLS, state)
    async with Client(server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    read, write = tools[READ_TOOL], tools[WRITE_TOOL]
    assert read.input_schema["type"] == "object"
    assert read.output_schema is not None
    assert read.output_schema["properties"] == {"count": {"title": "Count", "type": "integer"}}
    assert write.input_schema["required"] == ["by"]
    assert write.output_schema is not None
    assert set(write.output_schema["required"]) == {"status", "count"}
    assert read.annotations is not None
    assert read.annotations.read_only_hint is True
    assert read.annotations.idempotent_hint is True
    assert write.annotations is not None
    assert write.annotations.read_only_hint is False
    assert write.annotations.destructive_hint is False
    assert write.annotations.idempotent_hint is False


@pytest.mark.asyncio
async def test_success_text_block_is_sorted_json(tmp_path: Path) -> None:
    """S9.1 item 6: the text block is exactly the sorted, non-escaped JSON."""
    state = SandboxState({"count": 0}, _state_file(tmp_path))
    server = make_server("example", TOOLS, state)
    async with Client(server) as client:
        result = await client.call_tool(WRITE_TOOL, {"by": 3})
    structured = result.structured_content
    assert structured == {"status": "ok", "count": 3}
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_business_error_is_an_iserror_result(tmp_path: Path) -> None:
    """S9.1 item 7: a business error is ``isError`` with ``Error: <reason>``."""
    state = SandboxState({"count": 0}, _state_file(tmp_path))
    server = make_server("example", TOOLS, state)
    async with Client(server) as client:
        result = await client.call_tool(WRITE_TOOL, {"by": -1})
    assert result.is_error
    assert _text(result) == "Error: cannot add a negative amount"
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_missing_argument_is_a_tool_error_not_a_jsonrpc_error(tmp_path: Path) -> None:
    """Bad arguments surface as an error result, never as a JSON-RPC error."""
    state = SandboxState({"count": 0}, _state_file(tmp_path))
    server = make_server("example", TOOLS, state)
    async with Client(server) as client:
        result = await client.call_tool(WRITE_TOOL, {})
    assert result.is_error
    assert "required" in _text(result)


@pytest.mark.asyncio
async def test_state_file_is_written_at_startup_and_after_a_write(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with the initial state and follows writes."""
    path = _state_file(tmp_path)
    state = SandboxState({"count": 0}, path)
    server = make_server("example", TOOLS, state)
    assert _read_state(path)["count"] == 0
    async with Client(server) as client:
        await client.call_tool(WRITE_TOOL, {"by": 5})
    body = _read_state(path)
    assert body["count"] == 5
    assert body["updated_at"] == "2026-11-01T09:00:00Z"


@pytest.mark.asyncio
async def test_read_does_not_rewrite_the_state_file(tmp_path: Path) -> None:
    """Only write tools touch the file; a read leaves it alone."""
    path = _state_file(tmp_path)
    state = SandboxState({"count": 7}, path)
    server = make_server("example", TOOLS, state)
    before = path.stat().st_mtime_ns
    async with Client(server) as client:
        await client.call_tool(READ_TOOL, {})
    assert path.stat().st_mtime_ns == before


def test_make_server_rejects_an_empty_tool_list() -> None:
    """A sandbox without tools is a programming error, not an empty server."""
    with pytest.raises(ValueError, match="no tools"):
        make_server("example", (), SandboxState({}))


def test_make_server_rejects_duplicate_tool_names() -> None:
    """Two tools with one name would silently shadow each other."""
    duplicate = (TOOLS[0], TOOLS[0])
    with pytest.raises(ValueError, match="duplicate"):
        make_server("example", duplicate, SandboxState({}))


def test_run_sandbox_rejects_a_bad_listen_address(tmp_path: Path) -> None:
    """``--http`` must be ``HOST:PORT``; anything else exits as a usage error."""
    state = SandboxState({"count": 0}, _state_file(tmp_path))
    with pytest.raises(SystemExit) as exit_info:
        run_sandbox("example", TOOLS, state, ["--http", "not-a-address"])
    assert exit_info.value.code == 2


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls(tmp_path: Path) -> None:
    """``--http`` serves the two tools and writes the ``--state-file`` it was given."""
    path = _state_file(tmp_path)
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == {READ_TOOL, WRITE_TOOL}
            result = await client.call_tool(WRITE_TOOL, {"by": 1})
            assert result.structured_content == {"status": "ok", "count": 1}
    assert _read_state(path)["count"] == 1


@pytest.mark.asyncio
async def test_stdio_entry_point_lists_and_calls() -> None:
    """The default stdio entry point serves the two tools through the SDK client."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == {READ_TOOL, WRITE_TOOL}
        result = await client.call_tool(WRITE_TOOL, {"by": 4})
        assert result.structured_content == {"status": "ok", "count": 4}
