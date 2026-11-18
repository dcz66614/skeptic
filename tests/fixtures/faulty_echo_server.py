"""MCP stdio server with two echo tools, one of which fails on purpose.

The server offers ``echo`` and ``echo_other``. ``echo`` returns an ``isError``
result when the text is ``"error"``, so an e2e test can prove that a failed call
does not count as a successful one for A03. ``echo_other`` always succeeds, so a
test can also prove that a success on one target does not count for another.
"""

from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent

server: MCPServer[Any] = MCPServer("faulty-echo")

FAILED_TEXT = "upstream failed"
"""The text of the ``isError`` result."""


def describe() -> str:
    """Return the description every tool of this server declares.

    The text is written out rather than read from the SDK, so a test still
    knows exactly what the server said before the proxy rewrote it.

    Returns:
        The description.
    """
    return (
        "Return the text unchanged.\n\n"
        "Args:\n"
        "    text: The text to echo.\n\n"
        "Returns:\n"
        "    A tool result whose only content block is the same text.\n"
    )


@server.tool(description=describe())
def echo(text: str) -> CallToolResult:
    if text == "error":
        return CallToolResult(content=[TextContent(type="text", text=FAILED_TEXT)], isError=True)
    return CallToolResult(content=[TextContent(type="text", text=text)])


@server.tool(description=describe())
def echo_other(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


if __name__ == "__main__":
    server.run("stdio")
