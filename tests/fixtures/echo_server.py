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

ECHO_DESCRIPTION = (
    "Return the text unchanged.\n\n"
    "Args:\n"
    "    text: The text to echo.\n\n"
    "Returns:\n"
    "    A tool result whose only content block is the same text.\n"
)
"""The ``echo`` tool description, written out so it is identical on every Python.

Python 3.13 strips the indentation of a docstring at compile time and 3.12 does
not, and the SDK reads ``__doc__`` as is. An explicit description keeps the text
the proxy sees, and the tests assert on, the same on both.
"""


@server.tool(description=ECHO_DESCRIPTION)
def echo(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "http":
        server.run("streamable-http", host="127.0.0.1", port=int(sys.argv[2]))
    else:
        server.run("stdio")
