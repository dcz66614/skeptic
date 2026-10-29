"""Unit tests for the loud faults L01-L07 (S6, F21).

Each fault is driven through the ``FaultEngine`` so the schedule, the hooks and
the target filter run exactly as they do in a real episode. The rewritten
message is then compared as a whole against the JSON S6 spells out.
"""

import json
from typing import Any

import pytest

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.faults.loud import (
    L01_HOLD_MS,
    L02_CODE,
    L02_MESSAGE,
    L03_TEXT,
    L05_RETRY_AFTER_S,
    RENAME_SUFFIX,
    JsonRpcError,
    RateLimited,
    SchemaDrift,
    Timeout,
    ToolError,
    ToolMissing,
    _arguments,
    _required,
    _tool_definition,
)
from skeptic_agent.faults.registry import FAULT_IDS, REGISTRY, get_fault
from skeptic_agent.jsonrpc import (
    ErrorResponse,
    Message,
    Notification,
    Request,
    Response,
    dump,
    parse_line,
)
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import Forward, Hold, ReplyToClient, cancelled_id, new_pipeline

pytestmark = pytest.mark.unit

ERA = Era(kind="MODERN", version="2026-07-28")

SCENARIO = {
    "id": "weather.forecast.max-temp.001",
    "fault_targets": {"primary": ["get_forecast"]},
    "tool_defs": {
        "get_forecast": {
            "name": "get_forecast",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["city"],
            },
        },
        "ping": {"name": "ping", "inputSchema": {"type": "object", "required": []}},
    },
}


def _parse(payload: dict[str, Any]) -> Message:
    """Parse a JSON-RPC object into a message.

    Args:
        payload: The message object.

    Returns:
        The parsed message.
    """
    message = parse_line(json.dumps(payload).encode())
    assert isinstance(message, (Request, Response, ErrorResponse, Notification))
    return message


def _call(id_: int, tool: str = "get_forecast", arguments: dict | None = None) -> Request:
    """Build a ``tools/call`` request.

    Args:
        id_: The request id.
        tool: The tool name.
        arguments: The arguments, or ``None`` to omit them.

    Returns:
        The request.
    """
    params: dict[str, Any] = {"name": tool}
    if arguments is not None:
        params["arguments"] = arguments
    message = _parse({"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": params})
    assert isinstance(message, Request)
    return message


def _ok(id_: int, result: dict[str, Any] | None = None) -> Response:
    """Build a successful response.

    Args:
        id_: The response id.
        result: The result object; a plain tool result by default.

    Returns:
        The response.
    """
    payload = {"content": [{"type": "text", "text": "18.4"}], "isError": False}
    message = _parse({"jsonrpc": "2.0", "id": id_, "result": payload if result is None else result})
    assert isinstance(message, Response)
    return message


def _ctx(scenario: dict[str, Any] | None = SCENARIO) -> EpisodeContext:
    """Build an episode context.

    Args:
        scenario: The scenario, or ``None`` for no scenario context.

    Returns:
        The context.
    """
    return EpisodeContext(
        episode_id="run:weather.forecast.max-temp.001:L01:1",
        seed=1,
        era=ERA,
        scenario=scenario,
    )


def _engine(fault_id: str, **spec_fields: Any) -> FaultEngine:
    """Build an engine with one fault scheduled on every attempt.

    Args:
        fault_id: The S6 fault id.
        spec_fields: Extra ``FaultSpec`` fields.

    Returns:
        The engine.
    """
    spec = FaultSpec(
        fault_id=fault_id,
        tool=str(spec_fields.pop("tool", "$primary")),
        call_index=spec_fields.pop("call_index", "all"),
        probability=float(spec_fields.pop("probability", 1.0)),
        persistence=str(spec_fields.pop("persistence", "permanent")),
        params=spec_fields.pop("params", None),
    )
    return FaultEngine([spec], scenario=SCENARIO)


async def _call_through(engine: FaultEngine, ctx: EpisodeContext, tool: str = "get_forecast"):
    """Send one ``tools/call`` and return its actions.

    Args:
        engine: The engine.
        ctx: The episode context.
        tool: The tool to call.

    Returns:
        The actions the pipeline returned.
    """
    return await new_pipeline(fault=engine).on_c2s(_call(1, tool, {"city": "Paris"}), ctx)


async def _respond(engine: FaultEngine, ctx: EpisodeContext, msg: Message):
    """Send one upstream response through the engine.

    Args:
        engine: The engine.
        ctx: The episode context.
        msg: The upstream response.

    Returns:
        The actions the pipeline returned.
    """
    return await new_pipeline(fault=engine).on_s2c(msg, ctx)


def test_all_loud_faults_are_registered() -> None:
    """L01-L07 are the loud half of the catalogue and are now registered."""
    assert FAULT_IDS[:7] == ("L01", "L02", "L03", "L04", "L05", "L06", "L07")
    for fault_id, cls in (
        ("L01", Timeout),
        ("L02", JsonRpcError),
        ("L03", ToolError),
        ("L05", RateLimited),
        ("L06", ToolMissing),
        ("L07", SchemaDrift),
    ):
        assert get_fault(fault_id) is cls
        assert REGISTRY[fault_id].cls == "loud"


def test_l04_is_not_registered_in_stdio() -> None:
    """L04 only applies to HTTP, so F21 ships no stdio implementation."""
    assert get_fault("L04") is None


def test_defaults_match_s6() -> None:
    """The default parameters are the ones S6 lists."""
    assert L01_HOLD_MS == 30000
    assert (L02_CODE, L02_MESSAGE) == (-32603, "Internal error")
    assert L03_TEXT == "Error: upstream service unavailable (HTTP 503). Please retry later."
    assert L05_RETRY_AFTER_S == 2
    assert RENAME_SUFFIX == "_v2"


@pytest.mark.asyncio
async def test_l01_holds_then_times_out() -> None:
    """L01 holds the response and then answers with the S6 timeout error."""
    engine, ctx = _engine("L01"), _ctx()
    call = _call(7, "get_forecast", {"city": "Paris"})
    assert await new_pipeline(fault=engine).on_c2s(call, ctx) == [Forward(call)]

    actions = await _respond(engine, ctx, _ok(7))

    hold = actions[0]
    assert isinstance(hold, Hold)
    assert hold.ms == 30000
    error = hold.then
    assert isinstance(error, ReplyToClient)
    assert dump(error.msg) == (
        b'{"jsonrpc":"2.0","id":7,"error":{"code":-32001,"message":"Request timed out",'
        b'"data":null}}\n'
    )


@pytest.mark.asyncio
async def test_l01_hold_ms_comes_from_params() -> None:
    """``hold_ms`` overrides the 30 s default."""
    engine, ctx = _engine("L01", params={"hold_ms": 50}), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    hold = actions[0]
    assert isinstance(hold, Hold)
    assert hold.ms == 50


@pytest.mark.asyncio
async def test_l01_with_zero_hold_does_not_hold() -> None:
    """A non-positive hold answers at once, keeping the same reply."""
    engine, ctx = _engine("L01", params={"hold_ms": 0}), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    reply = actions[0]
    assert isinstance(reply, ReplyToClient)
    assert reply.msg.error.code == -32001  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_l01_ignores_an_already_failed_response() -> None:
    """An error response has no result to hold, so L01 passes it through."""
    engine, ctx = _engine("L01"), _ctx()
    await _call_through(engine, ctx)
    error = _parse({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}})
    assert await _respond(engine, ctx, error) == [Forward(error)]


@pytest.mark.asyncio
async def test_l01_ignores_untracked_responses() -> None:
    """A response to an uncounted request is forwarded; nothing is held."""
    engine, ctx = _engine("L01"), _ctx()
    response = _ok(99)
    assert await _respond(engine, ctx, response) == [Forward(response)]


def test_cancelled_id_reads_the_request_id() -> None:
    """Only ``notifications/cancelled`` carries an id to cancel."""
    cancelled = _parse(
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7}}
    )
    assert cancelled_id(cancelled) == 7
    other = _parse({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert cancelled_id(other) is None
    no_id = _parse(
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"reason": "x"}}
    )
    assert cancelled_id(no_id) is None
    bad_id = _parse(
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": {"a": 1}}}
    )
    assert cancelled_id(bad_id) is None


@pytest.mark.asyncio
async def test_l02_replaces_the_response_with_the_s6_error() -> None:
    """L02 answers with code -32603 and message "Internal error"."""
    engine, ctx = _engine("L02"), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    assert len(actions) == 1
    rewritten = actions[0].msg  # type: ignore[attr-defined]
    assert dump(rewritten) == (
        b'{"jsonrpc":"2.0","id":1,"error":{"code":-32603,"message":"Internal error","data":null}}\n'
    )


@pytest.mark.asyncio
async def test_l02_params_override_the_defaults() -> None:
    """``code`` and ``message`` come from the fault params."""
    engine, ctx = _engine("L02", params={"code": -32601, "message": "Nope"}), _ctx()
    await new_pipeline(fault=engine).on_c2s(_call(2, "get_forecast", {"city": "Paris"}), ctx)
    actions = await _respond(engine, ctx, _ok(2))
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":2,"error":{"code":-32601,"message":"Nope","data":null}}\n'
    )


@pytest.mark.asyncio
async def test_l03_returns_the_s6_tool_error() -> None:
    """L03 replaces the result with the S6 503 text and ``isError`` true."""
    engine, ctx = _engine("L03"), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text",'
        b'"text":"Error: upstream service unavailable (HTTP 503). Please retry later."}],'
        b'"isError":true}}\n'
    )


@pytest.mark.asyncio
async def test_l03_respects_result_type() -> None:
    """A non-complete ``resultType`` is passed through untouched (S4.5)."""
    engine, ctx = _engine("L03"), _ctx()
    await _call_through(engine, ctx)
    response = _ok(1, {"content": [], "resultType": "input_required"})
    assert await _respond(engine, ctx, response) == [Forward(response)]


@pytest.mark.asyncio
async def test_l03_respects_the_call_index() -> None:
    """L03 is transient by default only when the profile says so; here it fires once."""
    engine, ctx = _engine("L03", call_index=2, persistence="transient"), _ctx()
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_call(1, "get_forecast", {"city": "Paris"}), ctx)
    first = _ok(1)
    assert await pipeline.on_s2c(first, ctx) == [Forward(first)]
    await pipeline.on_c2s(_call(2, "get_forecast", {"city": "Paris"}), ctx)
    second = _ok(2)
    assert (await pipeline.on_s2c(second, ctx))[0] != Forward(second)


@pytest.mark.asyncio
async def test_l05_returns_the_s6_rate_limit_error() -> None:
    """L05 answers with the 429 text carrying ``retry_after_s``."""
    engine, ctx = _engine("L05"), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text",'
        b'"text":"Error 429: rate limit exceeded. Retry after 2 seconds."}],'
        b'"isError":true}}\n'
    )


@pytest.mark.asyncio
async def test_l05_uses_retry_after_s() -> None:
    """``retry_after_s`` replaces the default 2 seconds."""
    engine, ctx = _engine("L05", params={"retry_after_s": 7}), _ctx()
    await _call_through(engine, ctx)
    actions = await _respond(engine, ctx, _ok(1))
    text = actions[0].msg.result["content"][0]["text"]  # type: ignore[attr-defined,index]
    assert text == "Error 429: rate limit exceeded. Retry after 7 seconds."


@pytest.mark.asyncio
async def test_l06_removes_the_tool_from_tools_list() -> None:
    """L06 drops the target tool and keeps the others, in order."""
    engine, ctx = _engine("L06"), _ctx()
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_parse({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}), ctx)
    listing = _parse(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "tools": [
                    {"name": "get_forecast"},
                    {"name": "ping"},
                ]
            },
        }
    )
    actions = await pipeline.on_s2c(listing, ctx)
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"ping"}]}}\n'
    )


@pytest.mark.asyncio
async def test_l06_answers_calls_with_unknown_tool() -> None:
    """L06 does not forward the call; the client gets -32602 directly."""
    engine, ctx = _engine("L06"), _ctx()
    actions = await _call_through(engine, ctx)
    reply = actions[0]
    assert isinstance(reply, ReplyToClient)
    assert dump(reply.msg) == (
        b'{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":"Unknown tool: get_forecast",'
        b'"data":null}}\n'
    )


@pytest.mark.asyncio
async def test_l06_is_permanent() -> None:
    """A permanent L06 keeps rejecting every later call."""
    engine, ctx = _engine("L06", persistence="permanent"), _ctx()
    pipeline = new_pipeline(fault=engine)
    for id_ in (1, 2):
        actions = await pipeline.on_c2s(_call(id_, "get_forecast", {"city": "Paris"}), ctx)
        assert isinstance(actions[0], ReplyToClient)


@pytest.mark.asyncio
async def test_l06_leaves_other_tools_alone() -> None:
    """The target glob keeps L06 away from other tools."""
    engine, ctx = _engine("L06", tool="get_forecast"), _ctx()
    call = _call(1, "ping", {})
    assert await new_pipeline(fault=engine).on_c2s(call, ctx) == [Forward(call)]


def test_l07_renames_the_first_required_parameter() -> None:
    """``_drift_tool`` renames the first required property and its ``required`` entry."""
    drifted = SchemaDrift()._drift_tool(
        {
            "name": "get_forecast",
            "inputSchema": {
                "properties": {"city": {"type": "string"}, "days": {"type": "integer"}},
                "required": ["city"],
            },
        },
        _ctx(),
    )
    assert drifted == {
        "name": "get_forecast",
        "inputSchema": {
            "properties": {"city_v2": {"type": "string"}, "days": {"type": "integer"}},
            "required": ["city_v2"],
        },
    }


def test_l07_drift_tool_without_a_schema_is_unchanged() -> None:
    """A tool with no ``inputSchema``, no name, or no required parameters is kept."""
    fault = SchemaDrift()
    assert fault._drift_tool({"name": "x"}, _ctx()) == {"name": "x"}
    assert fault._drift_tool({"name": "x", "inputSchema": {}}, _ctx()) == {
        "name": "x",
        "inputSchema": {},
    }
    assert fault._drift_tool({"inputSchema": {"required": ["a"]}}, _ctx()) == {
        "inputSchema": {"required": ["a"]}
    }


@pytest.mark.asyncio
async def test_l07_snapshot_of_the_drifted_list() -> None:
    """The drifted ``tools/list`` is exactly the S6 rename."""
    engine, ctx = _engine("L07"), _ctx()
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_parse({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}), ctx)
    listing = _parse(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "tools": [
                    {
                        "name": "get_forecast",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                    {"name": "ping", "inputSchema": {"type": "object"}},
                ]
            },
        }
    )
    actions = await pipeline.on_s2c(listing, ctx)
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":3,"result":{"tools":[{"name":"get_forecast","inputSchema":'
        b'{"type":"object","properties":{"city_v2":{"type":"string"}},"required":["city_v2"]}},'
        b'{"name":"ping","inputSchema":{"type":"object"}}]}}\n'
    )


@pytest.mark.asyncio
async def test_l07_rejects_the_old_name() -> None:
    """A call that still sends ``old`` is answered with the S6 argument error."""
    engine, ctx = _engine("L07"), _ctx()
    actions = await _call_through(engine, ctx)
    reply = actions[0]
    assert isinstance(reply, ReplyToClient)
    assert dump(reply.msg) == (
        b'{"jsonrpc":"2.0","id":1,"error":{"code":-32602,"message":'
        b'"Invalid arguments: missing required property \'city_v2\'","data":null}}\n'
    )


@pytest.mark.asyncio
async def test_l07_accepts_the_new_name_and_translates_it() -> None:
    """A call with ``new`` is forwarded with the parameter renamed back to ``old``."""
    engine, ctx = _engine("L07"), _ctx()
    call = _call(1, "get_forecast", {"city_v2": "Paris", "days": 3})
    actions = await new_pipeline(fault=engine).on_c2s(call, ctx)
    forwarded = actions[0]
    assert isinstance(forwarded, Forward)
    assert forwarded.msg.params["arguments"] == {"city": "Paris", "days": 3}  # type: ignore[index]


@pytest.mark.asyncio
async def test_l07_both_names_keeps_the_old_one() -> None:
    """When the call carries both names, ``new`` is folded into ``old``."""
    engine, ctx = _engine("L07"), _ctx()
    call = _call(1, "get_forecast", {"city": "Lyon", "city_v2": "Paris"})
    actions = await new_pipeline(fault=engine).on_c2s(call, ctx)
    forwarded = actions[0]
    assert isinstance(forwarded, Forward)
    assert forwarded.msg.params["arguments"] == {"city": "Paris"}  # type: ignore[index]


@pytest.mark.asyncio
async def test_l07_without_the_argument_is_forwarded() -> None:
    """A call that names neither the old nor the new parameter is left alone."""
    engine, ctx = _engine("L07"), _ctx()
    call = _call(1, "get_forecast", {"days": 3})
    assert await new_pipeline(fault=engine).on_c2s(call, ctx) == [Forward(call)]


@pytest.mark.asyncio
async def test_l07_call_without_arguments_is_forwarded() -> None:
    """A call with no ``arguments`` object has nothing to translate."""
    engine, ctx = _engine("L07"), _ctx()
    call = _call(1)
    assert await new_pipeline(fault=engine).on_c2s(call, ctx) == [Forward(call)]


def test_l07_is_applicable_only_with_a_required_parameter() -> None:
    """L07 needs the target tool to declare at least one required parameter."""
    assert SchemaDrift().applicable(_ctx()) is True
    no_required = {"fault_targets": {"primary": ["ping"]}, "tool_defs": SCENARIO["tool_defs"]}
    assert SchemaDrift().applicable(_ctx(no_required)) is False
    assert SchemaDrift().applicable(_ctx(None)) is False


@pytest.mark.asyncio
async def test_l07_does_not_fire_without_a_required_parameter() -> None:
    """``applicable`` false keeps L07 silent even when the schedule would fire."""
    scenario = {"fault_targets": {"primary": ["ping"]}, "tool_defs": SCENARIO["tool_defs"]}
    engine, ctx = _engine("L07"), _ctx(scenario)
    call = _call(1, "ping", {})
    assert await new_pipeline(fault=engine).on_c2s(call, ctx) == [Forward(call)]


@pytest.mark.asyncio
async def test_l07_reads_tool_defs_from_tools_list() -> None:
    """A definition on ``ctx.tool_defs`` is enough when the scenario has none."""
    ctx = _ctx(None)
    engine = _engine("L07")
    ctx.tool_defs["get_forecast"] = {
        "name": "get_forecast",
        "inputSchema": {"required": ["city"]},
    }
    pipeline = new_pipeline(fault=engine)
    actions = await pipeline.on_c2s(_call(6, "get_forecast", {"city": "Paris"}), ctx)
    assert isinstance(actions[0], ReplyToClient)


def test_l07_drifts_only_the_tools_its_target_covers() -> None:
    """A glob or ``$primary`` target leaves the other listed tools untouched."""
    engine = _engine("L07", tool="get_*")
    spec = engine.planned[0].spec
    listing = _parse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "get_forecast", "inputSchema": {"required": ["city"]}},
                    {"name": "place_order", "inputSchema": {"required": ["id"]}},
                ]
            },
        }
    )
    drifted = SchemaDrift().apply(listing, spec, _ctx())
    assert [tool["name"] for tool in drifted.result["tools"]] == ["get_forecast", "place_order"]
    assert drifted.result["tools"][0]["inputSchema"]["required"] == ["city_v2"]
    assert drifted.result["tools"][1]["inputSchema"]["required"] == ["id"]


def test_tool_definition_sources() -> None:
    """The tool definition is read from the context, ``tool_defs`` or ``tools``."""
    ctx = _ctx({"tools": [{"name": "ping", "inputSchema": {"required": ["x"]}}]})
    assert _tool_definition(ctx, "ping") == {"name": "ping", "inputSchema": {"required": ["x"]}}
    ctx.tool_defs["ping"] = {"name": "ping", "inputSchema": {"required": ["y"]}}
    assert _tool_definition(ctx, "ping") == {"name": "ping", "inputSchema": {"required": ["y"]}}
    assert _tool_definition(_ctx(None), "ping") is None
    assert _tool_definition(_ctx({"tool_defs": {}}), "ping") is None
    assert _tool_definition(_ctx({"tools": "nope"}), "ping") is None


def test_required_handles_missing_schemas() -> None:
    """``_required`` is empty for a missing schema or a non-list ``required``."""
    assert _required(None) == []
    assert _required({"required": "city"}) == []
    assert _required({"required": ["city", "days"]}) == ["city", "days"]


def test_arguments_helper() -> None:
    """``_arguments`` only reads an object ``params.arguments``."""
    assert _arguments(_call(1, "get_forecast", {"city": "Paris"})) == {"city": "Paris"}
    assert _arguments(_call(1)) is None
    assert _arguments(_ok(1)) is None
    assert _arguments(_parse({"jsonrpc": "2.0", "id": 1, "method": "tools/call"})) is None
