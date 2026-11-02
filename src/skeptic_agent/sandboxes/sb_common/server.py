"""The sandbox server factory every sandbox builds on (S9.1, ADR-0004).

``make_server`` wraps the SDK's ``MCPServer`` so all ten sandboxes answer the
same way without repeating the rules:

- every tool returns ``structuredContent`` plus one text block holding
  ``json.dumps(structured, ensure_ascii=False, sort_keys=True)`` (S9.1 item 6);
- a business error is an ``isError`` result whose text is ``Error: <reason>``
  and never a JSON-RPC error (S9.1 item 7);
- read tools are annotated ``readOnlyHint=true, idempotentHint=true``; write
  tools ``readOnlyHint=false`` plus the sandbox's ``destructiveHint`` and
  ``idempotentHint`` (S9.1 item 5);
- the state file is written once at startup and after every write (S9.1
  item 4).

S9.2 writes each tool as ``get_forecast(city, date)``. ``make_server`` builds
the callable the SDK registers from the tool's ``input`` model (as
``**kwargs``) and ``output`` model (as ``Annotated[CallToolResult, output]``),
so ``inputSchema`` and ``outputSchema`` come from those same models, the way
S9.1 item 5 requires, and the sandbox only writes its async ``handler``.
Raising :class:`ToolFailure` inside the handler produces the business error.
A tool that records its write in the state file calls ``tool.finish()`` on the
:class:`SandboxTool` the factory passes to the handler.

``run_sandbox`` is the shared command line: no flag serves stdio, ``--http
HOST:PORT`` serves Streamable HTTP, and ``--state-file PATH`` sets the state
file for this process (S2 ``skeptic sandbox run``, S9.1 item 2).
"""

import argparse
import inspect
import json
import os
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, ContentBlock, TextContent, ToolAnnotations
from pydantic import BaseModel

from skeptic_agent.sandboxes.sb_common.state import STATE_FILE_ENV, SandboxState

HTTP_PATH = "/mcp"
"""The Streamable HTTP path ``MCPServer.run`` serves (ADR-0004)."""

type ToolCall = Callable[[Any, "SandboxTool"], Awaitable[BaseModel]]
"""A sandbox tool's async body. It takes the validated arguments and the tool.

The arguments are typed ``Any`` so a tool body may declare its own ``input``
model on the first parameter; the factory validates the client's arguments
into exactly that model before calling the body.
"""


class ToolFailure(Exception):
    """A business error: the client gets ``isError`` with ``Error: <reason>``."""

    def __init__(self, reason: str) -> None:
        """Record the reason.

        Args:
            reason: The short reason, without the ``Error: `` prefix.
        """
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ToolSpec:
    """One tool of a sandbox (S9.1 item 5, S9.2).

    Attributes:
        name: The tool name the client calls.
        description: The tool description shown in ``tools/list``.
        input: The Pydantic model of the arguments, which becomes
            ``inputSchema``; its fields become the keyword parameters.
        output: The Pydantic model of the result, which becomes
            ``outputSchema``.
        handler: The async body. It takes the validated arguments and the
            :class:`SandboxTool`, and returns an ``output`` instance or raises
            :class:`ToolFailure`.
        write: ``True`` for a write tool, ``False`` for a read tool.
        destructive: ``destructiveHint`` of a write tool (S9.1 item 5).
        idempotent: For a read tool this is always reported as ``True``; for a
            write tool it is the ``idempotentHint`` (S9.1 item 5).
    """

    name: str
    description: str
    input: type[BaseModel]
    output: type[BaseModel]
    handler: ToolCall
    write: bool = False
    destructive: bool = False
    idempotent: bool = False

    def annotations(self) -> ToolAnnotations:
        """Build the S9.1 item 5 annotations.

        Returns:
            Read tools: ``readOnlyHint=True, idempotentHint=True``. Write
            tools: ``readOnlyHint=False`` plus the spec's destructive and
            idempotent hints.
        """
        if not self.write:
            return ToolAnnotations(read_only_hint=True, idempotent_hint=True)
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=self.destructive,
            idempotent_hint=self.idempotent,
        )


class SandboxTool:
    """A registered tool, with the state and helpers its body needs.

    The tool body receives this object as its second argument instead of the
    state, so it can record a write in the state file through
    :meth:`finish` without closing over the sandbox.
    """

    def __init__(self, spec: ToolSpec, state: SandboxState) -> None:
        """Bind a spec to the sandbox state.

        Args:
            spec: The tool definition.
            state: The sandbox state the tool reads and mutates.
        """
        self.spec = spec
        self.state = state

    @property
    def data(self) -> dict[str, Any]:
        """The mutable in-memory state dict."""
        return self.state.data

    def finish(self) -> None:
        """Persist the state file now, after a write tool changed the state."""
        self.state.save()


def _json_text(structured: Mapping[str, Any]) -> str:
    """Render the S9.1 item 6 text block.

    Args:
        structured: The structured content.

    Returns:
        ``json.dumps(structured, ensure_ascii=False, sort_keys=True)``.
    """
    return json.dumps(structured, ensure_ascii=False, sort_keys=True)


def _text_blocks(text: str) -> list[ContentBlock]:
    """Wrap text as one content block.

    Args:
        text: The block's text.

    Returns:
        A one-block list in the SDK's content-block type, which the
        ``CallToolResult.content`` field accepts.
    """
    return [TextContent(type="text", text=text)]


def _ok(result: BaseModel) -> CallToolResult:
    """Wrap a handler's model in the S9.1 success result.

    Args:
        result: The handler's ``output`` model.

    Returns:
        ``structuredContent`` plus one text block holding the S9.1 JSON.
    """
    structured = result.model_dump(mode="json")
    return CallToolResult(
        content=_text_blocks(_json_text(structured)),
        structured_content=structured,
    )


def _business_error(reason: str) -> CallToolResult:
    """Wrap a business error in the S9.1 error result.

    Args:
        reason: The reason, without the ``Error: `` prefix.

    Returns:
        ``isError`` with a single block reading ``Error: <reason>``.
    """
    return CallToolResult(content=_text_blocks(f"Error: {reason}"), is_error=True)


def _make_tool_function(tool: SandboxTool) -> Callable[..., Coroutine[Any, Any, CallToolResult]]:
    """Build the callable the SDK registers for one tool.

    The callable is ``async def <name>(**parsed_arguments)`` whose parameters
    and annotations are copied from the spec's ``input`` model, and whose
    return annotation is ``Annotated[CallToolResult, <output>]``. The SDK
    reads that signature, so the wire ``inputSchema``/``outputSchema`` match
    the two models while the body keeps one implementation for every tool.

    Args:
        tool: The registered tool.

    Returns:
        The async function to register under the tool's name.
    """
    spec = tool.spec

    async def call(**arguments: Any) -> CallToolResult:
        """Run the tool body and return the S9.1 result shape.

        Args:
            **arguments: The client's arguments, already validated by the SDK.

        Returns:
            The success result, or ``isError`` ``Error: <reason>`` on a
            :class:`ToolFailure`.
        """
        parsed = spec.input.model_validate(arguments)
        try:
            result = await spec.handler(parsed, tool)
        except ToolFailure as failure:
            return _business_error(failure.reason)
        return _ok(result)

    parameters = [
        inspect.Parameter(
            name,
            inspect.Parameter.KEYWORD_ONLY,
            annotation=field.annotation,
            default=(
                inspect.Parameter.empty
                if field.is_required()
                else field.get_default(call_default_factory=True)
            ),
        )
        for name, field in spec.input.model_fields.items()
    ]
    call.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        parameters, return_annotation=Annotated[CallToolResult, spec.output]
    )
    call.__name__ = spec.name
    call.__qualname__ = spec.name
    call.__doc__ = spec.description
    return call


def make_server(name: str, tools: Sequence[ToolSpec], state: SandboxState) -> MCPServer[Any]:
    """Build the MCP server of a sandbox (S9.1, ADR-0004).

    Args:
        name: The server name, for example ``sb_weather``.
        tools: The tool specs (S9.2). At least one is required.
        state: The sandbox state. It is saved once here, before serving.

    Returns:
        The SDK ``MCPServer``, ready for ``run`` or a client.

    Raises:
        ValueError: When ``tools`` is empty or two specs share a name.
    """
    if not tools:
        raise ValueError(f"sandbox {name!r} declares no tools")
    names = [spec.name for spec in tools]
    duplicates = sorted({tool for tool in names if names.count(tool) > 1})
    if duplicates:
        raise ValueError(f"sandbox {name!r} declares duplicate tools: {duplicates}")
    server: MCPServer[Any] = MCPServer(name)
    state.save()
    for spec in tools:
        tool = SandboxTool(spec, state)
        server.tool(
            name=spec.name,
            description=spec.description,
            annotations=spec.annotations(),
            structured_output=True,
        )(_make_tool_function(tool))
    return server


def _parse_listen(value: str) -> tuple[str, int]:
    """Split ``HOST:PORT`` for ``--http``.

    Args:
        value: The ``--http`` argument.

    Returns:
        The host and port.

    Raises:
        ValueError: When the value is not ``HOST:PORT`` with a valid port.
    """
    host, separator, port = value.rpartition(":")
    if not separator or not host or not port.isdigit():
        raise ValueError(f"expected HOST:PORT, got {value!r}")
    return host, int(port)


def run_sandbox(
    name: str,
    tools: Sequence[ToolSpec],
    state: SandboxState,
    argv: Sequence[str] | None = None,
) -> None:
    """Build a sandbox and serve it, from the shared command line (S9.1 item 2).

    Args:
        name: The server name.
        tools: The tool specs.
        state: The sandbox state.
        argv: The arguments to parse; defaults to ``sys.argv[1:]``.

    Raises:
        SystemExit: With code 2 when the arguments are invalid.
    """
    parser = _parser(name)
    args = parser.parse_args(argv)
    listen: tuple[str, int] | None = None
    if args.http:
        try:
            listen = _parse_listen(args.http)
        except ValueError as error:
            parser.error(str(error))
    if args.state_file:
        os.environ[STATE_FILE_ENV] = args.state_file
        state.state_file = Path(args.state_file)
    server = make_server(name, tools, state)
    if listen is None:
        server.run("stdio")
    else:
        host, port = listen
        server.run("streamable-http", host=host, port=port)


def _parser(name: str) -> argparse.ArgumentParser:
    """Build the shared sandbox argument parser.

    Args:
        name: The server name, used in the usage line.

    Returns:
        The parser with ``--http`` and ``--state-file``.
    """
    parser = argparse.ArgumentParser(prog=f"python -m {name}", add_help=True)
    parser.add_argument(
        "--http",
        metavar="HOST:PORT",
        help="serve Streamable HTTP on HOST:PORT at /mcp instead of stdio",
    )
    parser.add_argument(
        "--state-file",
        metavar="PATH",
        help="write the sandbox state to PATH after startup and after each write",
    )
    return parser


__all__ = [
    "HTTP_PATH",
    "SandboxTool",
    "ToolCall",
    "ToolFailure",
    "ToolSpec",
    "make_server",
    "run_sandbox",
]
