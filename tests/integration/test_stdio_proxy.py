"""Integration tests: an MCP SDK client talks to an echo server through the proxy (P13)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.session import HANDSHAKE_PROTOCOL_VERSIONS
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"
PINNED_VERSION = "2025-11-25"
TIMEOUT_SECONDS = 60


def _pythonpath() -> str:
    """Return a PYTHONPATH that also finds the package source.

    Returns:
        ``src``, the fixtures dir and the existing ``PYTHONPATH``, joined.
    """
    parts = [str(ROOT / "src"), str(ECHO_SERVER.parent)]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.append(existing)
    return os.pathsep.join(parts)


def _proxy_params(*, with_seed: bool = False) -> StdioServerParameters:
    """Build the server parameters that start the proxy with the echo server.

    Args:
        with_seed: When true, pass ``--seed 1`` before the ``--`` separator.

    Returns:
        The parameters for the stdio client.
    """
    args = ["-m", "skeptic_agent.cli", "proxy", "stdio"]
    if with_seed:
        args += ["--seed", "1"]
    args += ["--", sys.executable, str(ECHO_SERVER)]
    env = dict(os.environ)
    env["PYTHONPATH"] = _pythonpath()
    return StdioServerParameters(command=sys.executable, args=args, env=env, cwd=str(ROOT))


def _first_text(result: types.CallToolResult) -> str:
    """Return the text of the first content block of a tool result.

    Args:
        result: The tool result.

    Returns:
        The text block's text.
    """
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


@pytest.mark.parametrize("with_seed", [False, True], ids=["auto", "seed"])
@pytest.mark.asyncio
async def test_echo_through_proxy_auto(with_seed: bool) -> None:
    params = _proxy_params(with_seed=with_seed)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("echo", {"text": "hello proxy"})
        assert not result.is_error
        assert _first_text(result) == "hello proxy"


@pytest.mark.skipif(
    PINNED_VERSION not in HANDSHAKE_PROTOCOL_VERSIONS,
    reason=f"the installed MCP SDK cannot negotiate protocol version {PINNED_VERSION}",
)
@pytest.mark.parametrize("with_seed", [False, True], ids=["auto", "seed"])
@pytest.mark.asyncio
async def test_echo_through_proxy_pinned_version(with_seed: bool) -> None:
    params = _proxy_params(with_seed=with_seed)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        request = types.InitializeRequest(
            params=types.InitializeRequestParams(
                protocol_version=PINNED_VERSION,
                capabilities=types.ClientCapabilities(),
                client_info=types.Implementation(name="test", version="1"),
            )
        )
        init = await session.send_request(request, types.InitializeResult)
        assert init.protocol_version == PINNED_VERSION
        session.adopt(init)
        await session.send_notification(types.InitializedNotification())

        result = await session.call_tool("echo", {"text": "pinned"})
        assert not result.is_error
        assert _first_text(result) == "pinned"


@pytest.mark.parametrize("code", [0, 3, 7])
def test_upstream_exit_code_is_propagated(tmp_path: Path, code: int) -> None:
    script = tmp_path / "exit_server.py"
    script.write_text(
        "import sys\nfor line in sys.stdin:\n    sys.stdout.write(line)\n    sys.stdout.flush()\n"
        f"sys.exit({code})\n",
        encoding="utf-8",
    )
    args = ["-m", "skeptic_agent.cli", "proxy", "stdio", "--", sys.executable, str(script)]
    completed = subprocess.run(
        [sys.executable, *args],
        input=b"",
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
        env={**os.environ, "PYTHONPATH": _pythonpath()},
        cwd=ROOT,
    )
    assert completed.returncode == code
    assert completed.stdout == b""
