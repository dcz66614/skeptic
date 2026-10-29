"""Minimal MCP server with one ``echo`` tool, built on the MCP SDK.

``python echo_server.py`` serves stdio; ``python echo_server.py http PORT``
serves streamable HTTP on ``127.0.0.1:PORT`` at ``/mcp``, so a test can bind a
port of its own choosing.
"""

import sys
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent

server: MCPServer[Any] = MCPServer("echo")


@server.tool()
def echo(text: str) -> CallToolResult:
    """Return the text unchanged.

    Args:
        text: The text to echo.

    Returns:
        A tool result whose only content block is the same text.
    """
    return CallToolResult(content=[TextContent(type="text", text=text)])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "http":
        server.run("streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run("stdio")
