"""Integration tests: the sb_docs sandbox (S9.2, S34).

Every one of the three tools gets a success case and a misuse case, driven
through the SDK client. The tests then cover the sandbox-level acceptance
line: ``python -m skeptic_agent.sandboxes.sb_docs`` starts over stdio, both
protocol generations can list and call the tools, ``skeptic sandbox run docs``
starts the same server, and the read-only state file is written at startup
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
from skeptic_agent.sandboxes.sb_docs import TOOLS
from skeptic_agent.sandboxes.sb_docs import server as docs
from skeptic_agent.sandboxes.sb_docs.data import generate

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60
STARTUP_SECONDS = 30

TOOL_NAMES = {"search_docs", "read_doc", "read_doc_archive"}


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
    """Serve sb_docs over Streamable HTTP on a free port.

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
            "skeptic_agent.sandboxes.sb_docs",
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
        args=["-m", "skeptic_agent.sandboxes.sb_docs"],
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=str(ROOT),
    )


def _cli_stdio_server() -> StdioServerParameters:
    """Return the stdio parameters for ``skeptic sandbox run docs``.

    Returns:
        How the client should launch the CLI, which starts the sandbox module.
    """
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "skeptic_agent.cli", "sandbox", "run", "docs"],
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
    fresh = docs.build_state()
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
async def test_search_docs_success(tmp_path: Path) -> None:
    """A term in a current body returns the S9.2 search fields."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_docs", {"query": "payload", "top_k": 1})
    structured = result.structured_content
    assert structured is not None
    assert len(structured["results"]) == 1
    hit = structured["results"][0]
    assert set(hit) == {"doc_id", "title", "snippet", "updated_at"}
    assert hit["doc_id"] == "KB-004"
    assert "payload" in hit["snippet"]
    assert _text(result) == json.dumps(structured, ensure_ascii=False, sort_keys=True)


@pytest.mark.asyncio
async def test_search_docs_chinese(tmp_path: Path) -> None:
    """A Chinese term matches the Chinese half of the corpus."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_docs", {"query": "电池"})
    structured = result.structured_content
    assert structured is not None
    assert structured["results"][0]["doc_id"] == "KB-019"


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"query": "   "}, "query must not be empty"),
        ({"query": "payload", "top_k": 0}, "top_k must be greater than zero"),
        ({"query": "payload", "top_k": -1}, "top_k must be greater than zero"),
        ({"query": "payload", "unexpected": 1}, "unexpected"),
    ],
)
@pytest.mark.asyncio
async def test_search_docs_misuse(tmp_path: Path, arguments: dict[str, Any], reason: str) -> None:
    """An empty query, a bad top_k and an unexpected argument are errors."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("search_docs", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_read_doc_success(tmp_path: Path) -> None:
    """The current document has the S9.2 fields and version 2."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_doc", {"doc_id": "kb-004"})
    structured = result.structured_content
    assert structured is not None
    assert list(structured) == ["doc_id", "title", "body", "updated_at", "version"]
    assert structured["doc_id"] == "KB-004"
    assert structured["version"] == 2
    assert structured["body"].startswith("The Atlas X1")
    assert not structured["body"].startswith("Initial release.")


@pytest.mark.asyncio
async def test_read_doc_misuse_unknown_document(tmp_path: Path) -> None:
    """An unknown document id is a business error."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_doc", {"doc_id": "KB-999"})
    assert result.is_error
    assert "unknown document" in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_read_doc_archive_success(tmp_path: Path) -> None:
    """The archived version is the older text of the same document."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_doc_archive", {"doc_id": "KB-004", "version": 1})
    structured = result.structured_content
    assert structured is not None
    assert structured["doc_id"] == "KB-004"
    assert structured["version"] == 1
    assert structured["body"].startswith("Initial release.")


@pytest.mark.asyncio
async def test_read_doc_archive_chinese_success(tmp_path: Path) -> None:
    """The archived Chinese version carries the Chinese marker."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_doc_archive", {"doc_id": "KB-019", "version": 1})
    structured = result.structured_content
    assert structured is not None
    assert structured["body"].startswith("初版。")


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({"doc_id": "KB-999", "version": 1}, "unknown document"),
        ({"doc_id": "KB-004", "version": 9}, "has no version 9"),
        ({"doc_id": "KB-004", "version": 0}, "version must be greater than zero"),
    ],
)
@pytest.mark.asyncio
async def test_read_doc_archive_misuse(
    tmp_path: Path, arguments: dict[str, Any], reason: str
) -> None:
    """An unknown document, an unknown version and version zero are errors."""
    async with Client(docs.server(_state(tmp_path))) as client:
        result = await client.call_tool("read_doc_archive", arguments)
    assert result.is_error
    assert reason in _text(result)
    assert result.structured_content is None


@pytest.mark.asyncio
async def test_every_tool_publishes_schemas_and_annotations(tmp_path: Path) -> None:
    """S9.1 item 5: one outputSchema per tool and read-only annotations."""
    async with Client(docs.server(_state(tmp_path))) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert set(tools) == TOOL_NAMES
    for tool in tools.values():
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
    assert docs.TOOLS[1].output is not None
    assert tools["read_doc"].output_schema is not None
    assert set(tools["read_doc"].output_schema["required"]) == {
        "doc_id",
        "title",
        "body",
        "updated_at",
        "version",
    }


@pytest.mark.asyncio
async def test_both_protocol_eras_list_and_call(tmp_path: Path) -> None:
    """Both protocol generations list and call the three tools."""
    for mode in ("auto", "legacy"):
        async with Client(docs.server(_state(tmp_path)), mode=mode) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("read_doc", {"doc_id": "KB-004"})
            assert result.structured_content is not None
            assert result.structured_content["version"] == 2


def test_state_file_is_written_at_startup(tmp_path: Path) -> None:
    """S9.1 item 4: the read-only state file appears stamped at startup."""
    path = tmp_path / "state.json"
    state = docs.build_state()
    state.state_file = path
    docs.server(state)
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["documents"]) == 60
    assert body["documents"][0]["doc_id"] == "KB-001"
    assert body["documents"][0]["version"] == 1


@pytest.mark.asyncio
async def test_stdio_module_entry_point_lists_and_calls() -> None:
    """``python -m skeptic_agent.sandboxes.sb_docs`` serves stdio (S9.1 item 2)."""
    async with Client(_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("read_doc", {"doc_id": "KB-010"})
        assert result.structured_content is not None
        assert result.structured_content["doc_id"] == "KB-010"


@pytest.mark.asyncio
async def test_cli_sandbox_run_starts_the_sandbox() -> None:
    """``skeptic sandbox run docs`` starts the module (S2, S9.1 item 2)."""
    async with Client(_cli_stdio_server()) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert tools == TOOL_NAMES
        result = await client.call_tool("read_doc_archive", {"doc_id": "KB-004", "version": 1})
        assert result.structured_content is not None
        assert result.structured_content["version"] == 1


@pytest.mark.asyncio
async def test_http_entry_point_lists_and_calls_and_writes_state(tmp_path: Path) -> None:
    """``--http`` serves the tools and writes the startup state file."""
    path = tmp_path / "state.json"
    with _served_http(path) as url:
        async with Client(url) as client:
            listed = {tool.name for tool in (await client.list_tools()).tools}
            assert listed == TOOL_NAMES
            result = await client.call_tool("search_docs", {"query": "AES-256"})
            assert result.structured_content is not None
            assert len(result.structured_content["results"]) == 2
    body = _read_state(path)
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert len(body["documents"]) == 60


def test_tool_specs_are_the_three_s9_2_tools() -> None:
    """The registry names exactly the S9.2 tools, all read-only."""
    assert {spec.name for spec in TOOLS} == TOOL_NAMES
    assert all(not spec.write for spec in TOOLS)
    assert generate.DOC_COUNT == 30
    assert generate.CURRENT_VERSION == 2
