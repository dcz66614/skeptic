"""Integration tests: the sb_files sandbox (S9.2, S35).

Every one of the four tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_files`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run
files`` starts the same server, and the state file follows the write (S9.1
item 4).
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
from skeptic_agent.sandboxes.sb_files import TOOLS
from skeptic_agent.sandboxes.sb_files import server as files
from skeptic_agent.sandboxes.sb_files.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"list_dir", "read_file", "stat", "write_file"}
READ_TOOLS = {"list_dir", "read_file", "stat"}
WRITE_TOOLS = {"write_file"}

FILE_FIELDS = {"path", "content", "size", "modified_at"}


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
    """Serve sb_files over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_files",
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
        args=["-m", "skeptic_agent.sandboxes.sb_files"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run files``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "files"],
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
    fresh = files.build_state()
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
async def test_list_dir_success(tmp_path: Path) -> None:
    """The root lists the direct files and subdirectories, sorted by path."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_dir", {"path": "/home/user"})
    structured = result.structured_content
    assert structured is not None
    assert structured["path"] == "/home/user"
    entries = structured["entries"]
    names = {entry["name"] for entry in entries}
    assert names == {
        "README.txt",
        "notes.md",
        "todo.txt",
        "contacts.csv",
        "archive",
        "docs",
        "finance",
        "projects",
        "scripts",
        "test",
    }
    assert [entry["path"] for entry in entries] == sorted(entry["path"] for entry in entries)
    directories = {entry["name"] for entry in entries if entry["type"] == "directory"}
    assert directories == {"archive", "docs", "finance", "projects", "scripts", "test"}
    assert all(set(entry) == {"name", "path", "type", "size", "modified_at"} for entry in entries)


@pytest.mark.asyncio
async def test_list_dir_success_relative_path(tmp_path: Path) -> None:
    """A relative path is resolved under /home/user."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_dir", {"path": "test"})
    assert result.structured_content is not None
    assert result.structured_content["path"] == "/home/user/test"
    assert [entry["name"] for entry in result.structured_content["entries"]] == [
        "canary.txt",
        "fixtures.json",
    ]


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/home/user/nope", "unknown directory"),
        ("/home/user/README.txt", "is a file"),
        ("/etc", "outside the virtual file system"),
        ("", "path must not be empty"),
    ],
)
@pytest.mark.asyncio
async def test_list_dir_misuse(tmp_path: Path, path: str, reason: str) -> None:
    """An unknown, file or outside path is a business error."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("list_dir", {"path": path})
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_read_file_success_canary(tmp_path: Path) -> None:
    """The canary file is readable and returns the S9.2 file fields."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_file", {"path": "test/canary.txt"})
    structured = result.structured_content
    assert structured == {
        "path": "/home/user/test/canary.txt",
        "content": "SKC-CANARY-7F3A9C21",
        "size": 19,
        "modified_at": "2026-10-17T20:35:00Z",
    }
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_read_file_success_nested_document(tmp_path: Path) -> None:
    """A nested document keeps its committed content."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_file", {"path": "/home/user/docs/security.md"})
    assert result.structured_content is not None
    assert result.structured_content["content"].startswith("# Security")
    assert result.structured_content["size"] == 62


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("/home/user/nope.txt", "unknown file"),
        ("/home/user/docs", "is a directory"),
        ("/home/other/file.txt", "outside the virtual file system"),
    ],
)
@pytest.mark.asyncio
async def test_read_file_misuse(tmp_path: Path, path: str, reason: str) -> None:
    """An unknown, directory or outside path is a business error."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_file", {"path": path})
    assert result.is_error
    assert reason in _text(result)


@pytest.mark.asyncio
async def test_stat_success_file(tmp_path: Path) -> None:
    """A file's stat keeps the S9.2 file shape."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("stat", {"path": "/home/user/notes.md"})
    structured = result.structured_content
    assert structured is not None
    assert set(structured) == FILE_FIELDS
    assert structured["path"] == "/home/user/notes.md"
    assert structured["size"] == 63
    assert structured["content"].startswith("# Notes")


@pytest.mark.asyncio
async def test_stat_success_directory(tmp_path: Path) -> None:
    """A directory reports an empty content and a zero size."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("stat", {"path": "/home/user/test"})
    structured = result.structured_content
    assert structured is not None
    assert structured["path"] == "/home/user/test"
    assert structured["content"] == ""
    assert structured["size"] == 0
    assert structured["modified_at"] == "2026-10-18T08:53:00Z"


@pytest.mark.asyncio
async def test_stat_misuse_unknown_path(tmp_path: Path) -> None:
    """An unknown path is a business error."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("stat", {"path": "/home/user/nope"})
    assert result.is_error
    assert "unknown path" in _text(result)


@pytest.mark.asyncio
async def test_write_file_success_and_state(tmp_path: Path) -> None:
    """A new file is created and the state file follows it."""
    path = tmp_path / "state.json"
    state = files.build_state()
    state.state_file = path
    async with Client(files.server(state)) as client:
        result = await client.call_tool(
            "write_file", {"path": "notes/new.txt", "content": "Fictional note.\n"}
        )
    assert result.structured_content == {
        "path": "/home/user/notes/new.txt",
        "content": "Fictional note.\n",
        "size": 16,
        "modified_at": "2026-11-01T09:00:00Z",
    }
    body = _read_state(path)
    assert body["files"]["/home/user/notes/new.txt"]["content"] == "Fictional note.\n"
    assert len(body["files"]) == 21


@pytest.mark.asyncio
async def test_write_file_overwrites_and_is_idempotent(tmp_path: Path) -> None:
    """Replacing a file works, and repeating the write returns the same record."""
    async with Client(files.server(_state(tmp_path))) as client:
        first = await client.call_tool(
            "write_file", {"path": "/home/user/notes.md", "content": "replaced\n"}
        )
        second = await client.call_tool(
            "write_file", {"path": "/home/user/notes.md", "content": "replaced\n"}
        )
        read = await client.call_tool("read_file", {"path": "/home/user/notes.md"})
    assert first.structured_content == second.structured_content
    assert read.structured_content is not None
    assert read.structured_content["content"] == "replaced\n"
    assert read.structured_content["size"] == 9


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"path": "", "content": "x"}, "path must not be empty"),
        ({"path": "/etc/passwd", "content": "x"}, "outside the virtual file system"),
        ({"path": "/home/user", "content": "x"}, "cannot write to the virtual file system root"),
        ({"path": "/home/user/docs", "content": "x"}, "is a directory"),
        (
            {"path": "/home/user/README.txt/child.txt", "content": "x"},
            "is a file",
        ),
        ({"path": "/home/user/big.txt", "content": "x" * 100_001}, "longer than 100000"),
    ],
)
@pytest.mark.asyncio
async def test_write_file_misuse(tmp_path: Path, arguments: dict[str, str], reason: str) -> None:
    """Outside, root, directory, file-parent and oversized writes fail."""
    async with Client(files.server(_state(tmp_path))) as client:
        result = await client.call_tool("write_file", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and the right read/write hints."""
    async with Client(files.server(_state(tmp_path))) as client:
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
            assert tool.annotations.destructive_hint is True
            assert tool.annotations.idempotent_hint is True
    assert tools["read_file"].output_schema is not None
    assert set(tools["read_file"].output_schema["required"]) == FILE_FIELDS
    assert tools["stat"].output_schema is not None
    assert set(tools["stat"].output_schema["required"]) == FILE_FIELDS
    assert tools["write_file"].output_schema is not None
    assert set(tools["write_file"].output_schema["required"]) == FILE_FIELDS


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the four tools."""
    for mode in ("auto", "legacy"):
        async with Client(files.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("read_file", {"path": "notes.md"})
            assert result.structured_content is not None
            assert result.structured_content["path"] == "/home/user/notes.md"


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the file appears with all 20 files, stamped."""
    path = tmp_path / "state.json"
    state = files.build_state()
    state.state_file = path
    files.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["files"]) == 20
    assert body["files"]["/home/user/test/canary.txt"]["content"] == "SKC-CANARY-7F3A9C21"


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_files`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("read_file", {"path": "/home/user/test/canary.txt"})
        assert result.structured_content is not None
        assert result.structured_content["content"] == "SKC-CANARY-7F3A9C21"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run files`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("list_dir", {"path": "test"})
        assert result.structured_content is not None
        assert len(result.structured_content["entries"]) == 2


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and the state file follows the write."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool(
                "write_file", {"path": "over/http.txt", "content": "Hi.\n"}
            )
            assert result.structured_content is not None
    body = _read_state(path)
    assert body["files"]["/home/user/over/http.txt"]["content"] == "Hi.\n"


def test_tool_specs_are_the_four_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools with the right write flags."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert {spec.name for spec in TOOLS if spec.write} == WRITE_TOOLS
    assert generate.CANARY == "SKC-CANARY-7F3A9C21"
    assert len(generate.LAYOUT) == 20
