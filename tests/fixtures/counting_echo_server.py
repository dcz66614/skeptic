"""Echo server that appends one line per tool call to a call log.

The server behaves like ``echo_server.py`` and additionally appends the called
tool name to the file named by ``--calls`` (or by ``SKEPTIC_CALL_LOG``), so a
test can count how many calls actually reached the upstream.
"""

import argparse
import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent

server: MCPServer[Any] = MCPServer("counting-echo")

CALL_LOG: Path | None = None
"""Where each call is recorded, set from the command line."""


def _record(name: str) -> None:
    """Append one line for a tool call.

    Args:
        name: The called tool name.
    """
    if CALL_LOG is None:
        return
    with CALL_LOG.open("a", encoding="utf-8") as handle:
        handle.write(name + "\n")


@server.tool()
def echo(text: str) -> CallToolResult:
    """Return the text unchanged and record the call.

    Args:
        text: The text to echo.

    Returns:
        A tool result whose only content block is the same text.
    """
    _record("echo")
    return CallToolResult(content=[TextContent(type="text", text=text)])


@server.tool()
def place_order(item: str) -> CallToolResult:
    """Pretend to place an order and record the call.

    Args:
        item: The item to order.

    Returns:
        A tool result reporting the new order.
    """
    _record("place_order")
    return CallToolResult(content=[TextContent(type="text", text=f"placed {item}")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", default=os.environ.get("SKEPTIC_CALL_LOG"))
    arguments = parser.parse_args()
    CALL_LOG = Path(arguments.calls) if arguments.calls else None
    server.run("stdio")
