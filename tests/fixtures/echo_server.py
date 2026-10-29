"""Minimal MCP stdio server with one ``echo`` tool, built on the MCP SDK."""

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
    server.run("stdio")
