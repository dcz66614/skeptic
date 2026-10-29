"""Explicit ("loud") faults L01-L07 (S6).

Every fault here makes the client see an error instead of a result. Each one
answers the JSON-RPC message itself from a hook. ``L06`` and ``L07`` also read
the tool definitions of the scenario, so they keep no state either.
"""

from collections.abc import Mapping
from typing import Any

from skeptic_agent.faults.base import Fault, FaultSpec
from skeptic_agent.faults.registry import register
from skeptic_agent.faults.schedule import resolve_targets, tool_matches
from skeptic_agent.jsonrpc import ErrorObject, ErrorResponse, Message, Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import Hold, ReplyToClient, ReplyWithStatus

L01_HOLD_MS = 30000
"""The default L01 hold (S6)."""

L02_CODE = -32603
"""The default L02 JSON-RPC error code (S6)."""

L02_MESSAGE = "Internal error"
"""The default L02 JSON-RPC error message (S6)."""

L03_TEXT = "Error: upstream service unavailable (HTTP 503). Please retry later."
"""The L03 tool-error text (S6)."""

L04_STATUS = 503
"""The default L04 HTTP status (S6)."""

L05_RETRY_AFTER_S = 2
"""The default L05 ``retry_after_s`` (S6)."""

TIMEOUT_CODE = -32001
"""The L01 JSON-RPC error code (S6)."""

TIMEOUT_MESSAGE = "Request timed out"
"""The L01 JSON-RPC error message (S6)."""

UNKNOWN_TOOL_CODE = -32602
"""The JSON-RPC error code L06 and L07 answer a rejected call with (S6)."""

RENAME_SUFFIX = "_v2"
"""L07 appends this to the first required parameter's name (S6, ADR-0002)."""


def _params(spec: FaultSpec) -> dict[str, Any]:
    """Return the fault-specific parameters, never ``None``.

    Args:
        spec: The scheduled fault.

    Returns:
        The parameters mapping.
    """
    return spec.params or {}


def _result_of(msg: Message) -> dict[str, Any] | None:
    """Return a mutable copy of a successful response's ``result`` object.

    A ``resultType`` other than ``"complete"`` is left alone (S4.5), as is a
    response that is already an error or whose result is not an object.

    Args:
        msg: The message a fault is about to rewrite.

    Returns:
        A fresh ``result`` dict to edit, or ``None`` when S6 rewrites nothing.
    """
    if not isinstance(msg, Response) or not isinstance(msg.result, dict):
        return None
    if msg.result.get("resultType", "complete") != "complete":
        return None
    return dict(msg.result)


def _with_result(msg: Response, result: dict[str, Any]) -> Response:
    """Return a copy of a response carrying a new result.

    Args:
        msg: The original response.
        result: The new ``result`` object.

    Returns:
        The rewritten response.
    """
    return msg.model_copy(update={"result": result})


def _error_text(text: str) -> dict[str, Any]:
    """Build the S6 tool-error result shape.

    Args:
        text: The error message.

    Returns:
        ``{"content": [{"type": "text", "text": text}], "isError": true}``.
    """
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _tool_definition(ctx: EpisodeContext, tool: str) -> dict[str, Any] | None:
    """Return the definition of a tool, from the episode or the scenario.

    ``ctx.tool_defs`` holds definitions seen in ``tools/list`` responses; the
    scenario may carry them as ``tool_defs`` (name to definition) or as
    ``tools`` (the array of a ``tools/list`` result), which is what the S7.4
    static check reads.

    Args:
        ctx: The episode context.
        tool: The tool name.

    Returns:
        The tool definition, or ``None`` when the tool is unknown.
    """
    definition = ctx.tool_defs.get(tool)
    if isinstance(definition, dict):
        return definition
    scenario = ctx.scenario
    if not isinstance(scenario, dict):
        return None
    return _scenario_tool_defs(scenario).get(tool)


def _scenario_tool_defs(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return a scenario's tool definitions, keyed by name.

    The scenario carries them as `tool_defs` (already keyed by name) or as
    `tools` (the array of a `tools/list` result).

    Args:
        scenario: The scenario mapping.

    Returns:
        The definitions by tool name.
    """
    defs = scenario.get("tool_defs")
    if isinstance(defs, dict):
        return {
            str(name): definition
            for name, definition in defs.items()
            if isinstance(definition, dict)
        }
    tools = scenario.get("tools")
    if not isinstance(tools, list):
        return {}
    return {
        item["name"]: item
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _input_schema(ctx: EpisodeContext, tool: str) -> dict[str, Any] | None:
    """Return the ``inputSchema`` of a tool.

    Args:
        ctx: The episode context.
        tool: The tool name.

    Returns:
        The schema object, or ``None`` when the tool or its schema is unknown.
    """
    definition = _tool_definition(ctx, tool)
    if definition is None:
        return None
    schema = definition.get("inputSchema", definition)
    return schema if isinstance(schema, dict) else None


def _required(schema: dict[str, Any] | None) -> list[str]:
    """Return the required property names of an input schema.

    Args:
        schema: The tool's ``inputSchema``, or ``None``.

    Returns:
        The required names in schema order; empty when there are none.
    """
    required = schema.get("required") if isinstance(schema, dict) else None
    return [str(name) for name in required] if isinstance(required, list) else []


def _arguments(msg: Message) -> dict[str, Any] | None:
    """Return the ``params.arguments`` object of a request.

    Args:
        msg: The message under inspection.

    Returns:
        The arguments object, or ``None`` when the message has none.
    """
    if not isinstance(msg, Request) or not isinstance(msg.params, dict):
        return None
    arguments = msg.params.get("arguments")
    return arguments if isinstance(arguments, dict) else None


def _with_arguments(msg: Request, arguments: dict[str, Any]) -> Request:
    """Return a copy of a request with different ``params.arguments``.

    Args:
        msg: The original request.
        arguments: The new arguments.

    Returns:
        The rewritten request.
    """
    params = msg.params if isinstance(msg.params, dict) else {}
    return msg.model_copy(update={"params": {**params, "arguments": arguments}})


def _structured_error(msg: Message, code: int, text: str) -> ReplyToClient | Message:
    """Build the S6 direct reply that replaces a ``tools/call`` (L06).

    Args:
        msg: The client's ``tools/call`` request.
        code: The JSON-RPC error code.
        text: The error message.

    Returns:
        A ``ReplyToClient`` addressed to the request id, or ``msg`` when the
        request has no usable id.
    """
    if not isinstance(msg, Request):
        return msg
    error = ErrorResponse(id=msg.id, error=ErrorObject(code=code, message=text))
    return ReplyToClient(error)


@register
class Timeout(Fault):
    """L01: hold the response for ``hold_ms``, then fail it (S6)."""

    id = "L01"
    cls = "loud"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Hold the upstream response, then replace it with a timeout error.

        ``unless_cancelled`` names the request, so the proxy drops the timeout
        error when the client cancels the call while it waits (S6, L01).

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.
            params: ``hold_ms``.

        Returns:
            The hold action, or ``payload`` when L01 cannot apply to it.
        """
        del ctx
        if not isinstance(payload, Response):
            return payload
        hold_ms = int(_params(spec).get("hold_ms", L01_HOLD_MS))
        error = ErrorResponse(
            id=payload.id,
            error=ErrorObject(code=TIMEOUT_CODE, message=TIMEOUT_MESSAGE),
        )
        if hold_ms <= 0:
            return ReplyToClient(error)
        return Hold(ms=hold_ms, then=ReplyToClient(error), unless_cancelled=payload.id)


@register
class JsonRpcError(Fault):
    """L02: replace the response with a JSON-RPC error (S6)."""

    id = "L02"
    cls = "loud"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Answer with ``{"error": {"code": code, "message": message}}``.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The error response, or ``payload`` when it is not a response.
        """
        del ctx
        if not isinstance(payload, (Response, ErrorResponse)):
            return payload
        params = _params(spec)
        error = ErrorObject(
            code=int(params.get("code", L02_CODE)),
            message=str(params.get("message", L02_MESSAGE)),
        )
        return ErrorResponse(id=payload.id, error=error)


@register
class ToolError(Fault):
    """L03: return an ``isError`` tool result (S6)."""

    id = "L03"
    cls = "loud"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Replace the result with the S6 upstream-error text.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when S4.5 says to skip it.
        """
        del ctx
        if not isinstance(payload, Response) or _result_of(payload) is None:
            return payload
        text = str(_params(spec).get("text", L03_TEXT))
        return _with_result(payload, _error_text(text))


@register
class HttpStatus(Fault):
    """L04: answer the HTTP request with a status and an empty body (S6).

    The fault never sees a list or a response, only the client's request on its
    way to the upstream. The proxy stops there and never forwards the call; the
    stdio proxy has no status to write, so it drops the action as S6 says L04 is
    not applicable there.
    """

    id = "L04"
    cls = "loud"
    hooks = ("pre_call",)

    def applicable(self, ctx: EpisodeContext) -> bool:
        """Report whether the episode runs over HTTP.

        Args:
            ctx: The episode context.

        Returns:
            ``True`` when the scenario records the HTTP transport (S7.4).
        """
        return _transport(ctx.scenario) == "http"

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Stop the call and answer with the configured status.

        Args:
            payload: The ``tools/call`` request.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            A ``ReplyWithStatus``, or ``payload`` when the fault cannot apply.
        """
        if not isinstance(payload, Request) or not self.applicable(ctx):
            return payload
        return ReplyWithStatus(int(_params(spec).get("status", L04_STATUS)))


@register
class RateLimited(Fault):
    """L05: return an ``isError`` rate-limit result (S6)."""

    id = "L05"
    cls = "loud"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Replace the result with the S6 429 text.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when S4.5 says to skip it.
        """
        del ctx
        if not isinstance(payload, Response) or _result_of(payload) is None:
            return payload
        retry_after_s = int(_params(spec).get("retry_after_s", L05_RETRY_AFTER_S))
        text = f"Error 429: rate limit exceeded. Retry after {retry_after_s} seconds."
        return _with_result(payload, _error_text(text))


@register
class ToolMissing(Fault):
    """L06: drop the tool from ``tools/list`` and reject its calls (S6)."""

    id = "L06"
    cls = "loud"
    hooks = ("pre_call", "list")

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Remove the definition from ``tools/list`` or reject the call.

        ``spec.tool`` is the target expression, which the engine already matched
        against the tool name. The tools it covers are therefore read from the
        message itself: the called name, or every listed name the expression
        matches.

        Args:
            payload: The ``tools/list`` response or the ``tools/call`` request.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The filtered list response, the direct error reply, or ``payload``.
        """
        patterns = resolve_targets(spec.tool, ctx.scenario)
        if isinstance(payload, Request):
            name = payload.params.get("name") if isinstance(payload.params, dict) else None
            tool = name if isinstance(name, str) else spec.tool
            return _structured_error(payload, UNKNOWN_TOOL_CODE, f"Unknown tool: {tool}")
        result = _result_of(payload)
        if result is None:
            return payload
        tools = result.get("tools")
        if not isinstance(tools, list):
            return payload
        result["tools"] = [
            tool
            for tool in tools
            if not (
                isinstance(tool, dict)
                and isinstance(tool.get("name"), str)
                and tool_matches(tool["name"], patterns)
            )
        ]
        assert isinstance(payload, Response)
        return _with_result(payload, result)


@register
class SchemaDrift(Fault):
    """L07: rename the first required parameter in the schema and on calls (S6)."""

    id = "L07"
    cls = "loud"
    hooks = ("pre_call", "list")

    def applicable(self, ctx: EpisodeContext) -> bool:
        """Report whether the target tool has at least one required parameter.

        Args:
            ctx: The episode context.

        Returns:
            ``True`` when the first required name can be read.
        """
        tools = _tool_names(self, ctx)
        return any(_required(_input_schema(ctx, tool)) for tool in tools)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Rename the parameter in ``tools/list`` or accept the new name on a call.

        Args:
            payload: The ``tools/list`` response or the ``tools/call`` request.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The drifted list response, the direct error reply, the rewritten
            call, or ``payload`` when L07 finds nothing to rename.
        """
        if isinstance(payload, Request):
            return self._rewrite_call(payload, ctx, resolve_targets(spec.tool, ctx.scenario))
        patterns = resolve_targets(spec.tool, ctx.scenario)
        result = _result_of(payload)
        if result is None:
            return payload
        tools = result.get("tools")
        if not isinstance(tools, list):
            return payload
        result["tools"] = [
            self._drift_tool(tool, ctx)
            if isinstance(tool, dict) and tool_matches(str(tool.get("name")), patterns)
            else tool
            for tool in tools
        ]
        assert isinstance(payload, Response)
        return _with_result(payload, result)

    def _first_required(self, ctx: EpisodeContext, tool: str) -> str | None:
        """Return the name L07 renames for one tool.

        Args:
            ctx: The episode context.
            tool: The tool name.

        Returns:
            The first required parameter, or ``None`` when there is none.
        """
        required = _required(_input_schema(ctx, tool))
        return required[0] if required else None

    def _drift_tool(self, tool: dict[str, Any], ctx: EpisodeContext) -> dict[str, Any]:
        """Return a copy of a tool definition with the first parameter renamed.

        Args:
            tool: A ``tools/list`` entry.
            ctx: The episode context.

        Returns:
            The drifted entry, or ``tool`` when there is nothing to rename.
        """
        name = tool.get("name")
        if not isinstance(name, str):
            return tool
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            return tool
        required = _required(schema)
        if not required:
            return tool
        old, new = required[0], required[0] + RENAME_SUFFIX
        properties = schema.get("properties")
        drifted = dict(schema)
        if isinstance(properties, dict) and old in properties:
            drifted["properties"] = {
                (new if key == old else key): value for key, value in properties.items()
            }
        drifted["required"] = [new if item == old else item for item in required]
        return {**tool, "inputSchema": drifted}

    def _rewrite_call(self, msg: Request, ctx: EpisodeContext, patterns: tuple[str, ...]) -> Any:
        """Check or translate the arguments of a drifted call.

        Args:
            msg: The ``tools/call`` request.
            ctx: The episode context.
            patterns: The tool name patterns the target expression stands for.

        Returns:
            The direct error reply, the call with ``new`` back as ``old``, or
            ``msg``.
        """
        tool = msg.params.get("name") if isinstance(msg.params, dict) else None
        if not isinstance(tool, str) or not tool_matches(tool, patterns):
            return msg
        old = self._first_required(ctx, tool)
        if old is None:
            return msg
        new = old + RENAME_SUFFIX
        arguments = _arguments(msg)
        if arguments is None:
            return msg
        if old in arguments and new not in arguments:
            return _structured_error(
                msg, UNKNOWN_TOOL_CODE, f"Invalid arguments: missing required property '{new}'"
            )
        if new not in arguments:
            return msg
        translated = {key: value for key, value in arguments.items() if key != old}
        translated = {(old if key == new else key): value for key, value in translated.items()}
        return _with_arguments(msg, translated)


def _tool_names(fault: Fault, ctx: EpisodeContext) -> list[str]:
    """Return the tools this fault covers in the episode.

    The engine filters by target before calling `apply`, but `applicable`
    runs first and only sees the context. L07 takes its required-parameter check
    from the scenario's primary tools (S7.4); when the context carries no
    scenario, it uses the definitions learned from `tools/list` instead.

    Args:
        fault: The fault instance.
        ctx: The episode context.

    Returns:
        The tool names to check.
    """
    del fault
    scenario = ctx.scenario
    if not isinstance(scenario, dict):
        return list(ctx.tool_defs)
    fault_targets = scenario.get("fault_targets") or {}
    primary = _field(fault_targets, "primary")
    names = [str(name) for name in primary] if isinstance(primary, list) else []
    if names:
        return names
    names = list(_scenario_tool_defs(scenario))
    return names or list(ctx.tool_defs)


def _field(value: object, name: str) -> Any:
    """Read a mapping field, or `None`.

    Args:
        value: A mapping or anything else.
        name: The field name.

    Returns:
        The value, or `None`.
    """
    return value.get(name) if isinstance(value, Mapping) else None


def _transport(scenario: object) -> str:
    """Return the transport a scenario runs on, from a mapping or a model.

    Args:
        scenario: The scenario, or ``None`` when none is loaded.

    Returns:
        The transport, ``"stdio"`` when the scenario does not record one.
    """
    transport = _field(scenario, "transport")
    if transport is None:
        transport = getattr(scenario, "transport", None)
    return str(transport or "stdio").lower()
