"""Unit tests for the interceptor pipeline and episode context (S4.3, S4.4)."""

import json
import uuid

import pytest

from skeptic_agent.jsonrpc import Message, Notification, Request, Response, dump, parse_line
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.context import EpisodeContext, PendingCall, new_internal_id
from skeptic_agent.proxy.pipeline import (
    C2S,
    Drop,
    FaultStage,
    Forward,
    GuardStage,
    Hold,
    RecorderStage,
    ReplyToClient,
    SendToServer,
    new_pipeline,
)

pytestmark = pytest.mark.unit

ERA = Era(kind="MODERN", version="2026-07-28")


def _ctx() -> EpisodeContext:
    """Build a fresh episode context.

    Returns:
        A context with the test episode identity and the MODERN era.
    """
    return EpisodeContext(episode_id="ep-1", seed=7, era=ERA)


def _parse(payload: str) -> Message:
    """Parse one JSON-RPC line.

    Args:
        payload: A JSON-RPC message.

    Returns:
        The parsed message.
    """
    message = parse_line(payload.encode("utf-8"))
    assert not isinstance(message, Exception)
    assert isinstance(message, (Request, Notification, Response))
    return message


def _call(id: int | str, tool: str = "weather.forecast") -> Request:
    """Build a ``tools/call`` request.

    Args:
        id: The request id.
        tool: The tool name.

    Returns:
        The parsed request.
    """
    return _request(id, "tools/call", {"name": tool, "arguments": {"city": "Berlin"}})


def _list(id: int | str) -> Request:
    """Build a ``tools/list`` request.

    Args:
        id: The request id.

    Returns:
        The parsed request.
    """
    return _request(id, "tools/list", {})


def _result(id: int | str, text: str = "22") -> Response:
    """Build a successful response carrying one text block.

    Args:
        id: The response id.
        text: The text block content.

    Returns:
        The parsed response.
    """
    return _response(id, {"content": [{"type": "text", "text": text}]})


def _request(id: int | str, method: str, params: dict[str, object]) -> Request:
    """Build and parse a request with the given id, method and params.

    Args:
        id: The request id.
        method: The JSON-RPC method.
        params: The request params.

    Returns:
        The parsed request.
    """
    payload = {"jsonrpc": "2.0", "id": id, "method": method, "params": params}
    return _parse(json.dumps(payload))  # type: ignore[return-value]


def _response(id: int | str, result: dict[str, object]) -> Response:
    """Build and parse a successful response.

    Args:
        id: The response id.
        result: The result object.

    Returns:
        The parsed response.
    """
    return _parse(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}))  # type: ignore[return-value]


class OrderStage:
    """A stage that appends its label to a shared list."""

    def __init__(self, label: str, calls: list[str]) -> None:
        """Store the label and the shared call log.

        Args:
            label: The name written on every call.
            calls: The shared list of call labels.
        """
        self.label = label
        self.calls = calls

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
        """Record the c2s call.

        Args:
            msg: The message.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        self.calls.append(f"{self.label}:c2s")
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[object]:
        """Record the s2c call.

        Args:
            msg: The message.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        self.calls.append(f"{self.label}:s2c")
        return [Forward(msg)]


class ReplyStage(RecorderStage):
    """A stage that answers the client instead of forwarding."""

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
        """Reply to the client with a fixed response.

        Args:
            msg: The message.
            ctx: The episode context.

        Returns:
            ``[ReplyToClient(...)]``.
        """
        assert isinstance(msg, Request)
        return [ReplyToClient(_result(msg.id, "blocked"))]


class FaultReplyStage(FaultStage):
    """A fault stage that counts attempts itself and answers the client."""

    def __init__(self, seen: list[int]) -> None:
        """Store the list that collects the attempt numbers it assigns.

        Args:
            seen: The shared list of attempt numbers.
        """
        self.seen = seen

    def counts_attempts(self) -> bool:
        """Take over attempt counting from the pipeline.

        Returns:
            ``True``.
        """
        return True

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
        """Count the attempt, then answer the client from the fault stage.

        Args:
            msg: The message.
            ctx: The episode context.

        Returns:
            ``[ReplyToClient(...)]``.
        """
        assert isinstance(msg, Request)
        assert isinstance(msg.params, dict)
        index = ctx.next_call_index(str(msg.params["name"]))
        ctx.current_call_index[str(msg.params["name"])] = index
        self.seen.append(index)
        return [ReplyToClient(_result(msg.id, "faulted"))]


def test_context_defaults() -> None:
    """A new context is empty and the scenario defaults to None."""
    ctx = _ctx()
    assert ctx.pending == {}
    assert ctx.call_counts == {}
    assert ctx.current_call_index == {}
    assert ctx.taint == set()
    assert ctx.tool_defs == {}
    assert ctx.scenario is None


def test_next_call_index_starts_at_one() -> None:
    """Attempts count 1, 2, 3 per tool and independently between tools."""
    ctx = _ctx()
    assert [ctx.next_call_index("echo") for _ in range(3)] == [1, 2, 3]
    assert ctx.next_call_index("weather") == 1
    assert ctx.call_counts == {"echo": 3, "weather": 1}


def test_new_internal_id() -> None:
    """Internal ids are unique and carry the skeptic prefix."""
    first = new_internal_id()
    second = new_internal_id()
    assert first.startswith("skeptic-")
    assert uuid.UUID(first.removeprefix("skeptic-")).version == 4
    assert first != second


@pytest.mark.asyncio
async def test_unmodified_message_passes_through() -> None:
    """Both directions return a Forward of the very same object, bytes intact."""
    msg = _parse('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    pipeline = new_pipeline()
    ctx = _ctx()
    for actions in (await pipeline.on_c2s(msg, ctx), await pipeline.on_s2c(msg, ctx)):
        assert len(actions) == 1
        action = actions[0]
        assert isinstance(action, Forward)
        assert action.msg is msg
        assert action.msg.raw_bytes == msg.raw_bytes


@pytest.mark.asyncio
async def test_notification_is_recorded_and_forwarded() -> None:
    """A notification is only recorded and passes through unchanged."""
    notification = _parse('{"jsonrpc":"2.0","method":"notifications/initialized"}')
    assert isinstance(notification, Notification)
    actions = await new_pipeline().on_c2s(notification, _ctx())
    assert actions == [Forward(notification)]


@pytest.mark.asyncio
async def test_stage_can_reply_to_client() -> None:
    """A recorder that stops the chain yields ReplyToClient and no attempt count."""
    ctx = _ctx()
    pipeline = new_pipeline(recorder=ReplyStage())
    actions = await pipeline.on_c2s(_call(1, "echo"), ctx)
    assert len(actions) == 1
    action = actions[0]
    assert isinstance(action, ReplyToClient)
    assert isinstance(action.msg, Response)
    assert ctx.pending == {}
    assert ctx.call_counts == {}


@pytest.mark.asyncio
async def test_fault_stage_reply_is_counted() -> None:
    """A call answered directly by the counting fault stage advances call_index."""
    ctx = _ctx()
    seen: list[int] = []
    pipeline = new_pipeline(fault=FaultReplyStage(seen))
    for id_ in (1, 2, 3):
        actions = await pipeline.on_c2s(_call(id_, "echo"), ctx)
        assert isinstance(actions[0], ReplyToClient)
    assert seen == [1, 2, 3]
    assert ctx.call_counts == {"echo": 3}
    assert ctx.current_call_index == {"echo": 3}
    assert ctx.pending == {}


@pytest.mark.asyncio
async def test_internal_id_response_is_not_delivered() -> None:
    """A response to a skeptic- id is dropped and never reaches the client."""
    ctx = _ctx()
    pipeline = new_pipeline()
    call = pipeline.send_to_server("tools/call", {"name": "echo", "arguments": {}})
    assert isinstance(call, SendToServer)
    internal_id = call.msg.id
    assert str(internal_id).startswith("skeptic-")

    actions = await pipeline.on_s2c(_result(internal_id), ctx)
    assert actions == [Drop()]


@pytest.mark.asyncio
async def test_foreign_response_is_only_recorded() -> None:
    """A response that matches no pending request is recorded and forwarded."""
    msg = _result(42)
    actions = await new_pipeline().on_s2c(msg, _ctx())
    assert actions == [Forward(msg)]


@pytest.mark.asyncio
async def test_c2s_tools_call_order() -> None:
    """A tools/call runs recorder, guard, fault, then forwards."""
    calls: list[str] = []
    pipeline = new_pipeline(
        recorder=OrderStage("recorder", calls),
        guard=OrderStage("guard", calls),
        fault=OrderStage("fault", calls),
    )
    ctx = _ctx()
    msg = _call(1, "echo")
    actions = await pipeline.on_c2s(msg, ctx)
    assert calls == ["recorder:c2s", "guard:c2s", "fault:c2s"]
    assert actions == [Forward(msg)]
    assert (C2S, 1) in ctx.pending


@pytest.mark.asyncio
async def test_s2c_tools_call_response_order() -> None:
    """A response to a tools/call runs fault, guard, recorder, then forwards."""
    calls: list[str] = []
    pipeline = new_pipeline(
        recorder=OrderStage("recorder", calls),
        guard=OrderStage("guard", calls),
        fault=OrderStage("fault", calls),
    )
    ctx = _ctx()
    await pipeline.on_c2s(_call(1, "echo"), ctx)
    calls.clear()
    response = _result(1)
    actions = await pipeline.on_s2c(response, ctx)
    assert calls == ["fault:s2c", "guard:s2c", "recorder:s2c"]
    assert actions == [Forward(response)]
    assert ctx.pending == {}


@pytest.mark.asyncio
async def test_s2c_tools_list_response_order() -> None:
    """A tools/list is c2s recorded only; its response runs fault, guard, recorder."""
    calls: list[str] = []
    pipeline = new_pipeline(
        recorder=OrderStage("recorder", calls),
        guard=OrderStage("guard", calls),
        fault=OrderStage("fault", calls),
    )
    ctx = _ctx()
    await pipeline.on_c2s(_list(9), ctx)
    assert calls == ["recorder:c2s"]
    assert ctx.pending[(C2S, 9)].method == "tools/list"
    calls.clear()
    response = _result(9, "[]")
    actions = await pipeline.on_s2c(response, ctx)
    assert calls == ["fault:s2c", "guard:s2c", "recorder:s2c"]
    assert actions == [Forward(response)]
    assert ctx.call_counts == {}


@pytest.mark.asyncio
async def test_other_messages_only_run_recorder() -> None:
    """Other methods and responses use the recorder alone."""
    calls: list[str] = []
    pipeline = new_pipeline(
        recorder=OrderStage("recorder", calls),
        guard=OrderStage("guard", calls),
        fault=OrderStage("fault", calls),
    )
    ctx = _ctx()
    await pipeline.on_c2s(_parse('{"jsonrpc":"2.0","id":3,"method":"ping"}'), ctx)
    assert calls == ["recorder:c2s"]
    calls.clear()
    await pipeline.on_s2c(_result(3), ctx)
    assert calls == ["recorder:s2c"]


@pytest.mark.asyncio
async def test_tools_call_stages_rewrite_is_forwarded() -> None:
    """A rewrite by a later stage replaces the earlier Forward payload."""

    class Rewrite(GuardStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Return an unrelated message in a Forward.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Forward(other)]``.
            """
            return [Forward(_call(99, "rewritten"))]

    pipeline = new_pipeline(guard=Rewrite())
    msg = _call(1, "echo")
    actions = await pipeline.on_c2s(msg, _ctx())
    assert isinstance(actions[0], Forward)
    assert actions[0].msg.id == 99


@pytest.mark.asyncio
async def test_call_index_counts_per_tool() -> None:
    """Forwarded tools/call attempts count 1, 2, 3 per tool name."""
    ctx = _ctx()
    pipeline = new_pipeline()
    for id_, tool in enumerate(["echo", "echo", "weather", "echo"], start=1):
        await pipeline.on_c2s(_call(id_, tool), ctx)
    assert ctx.call_counts == {"echo": 3, "weather": 1}
    assert ctx.pending[(C2S, 3)].attempt == 1
    assert ctx.pending[(C2S, 4)].attempt == 3
    assert ctx.current_call_index == {"echo": 3, "weather": 1}


@pytest.mark.asyncio
async def test_call_index_is_assigned_before_the_fault_stage() -> None:
    """The fault stage sees the attempt number the pipeline just assigned."""

    class Capture(FaultStage):
        def __init__(self) -> None:
            self.seen: list[int | None] = []

        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Remember the attempt number visible during the pre hooks.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Forward(msg)]``.
            """
            self.seen.append(ctx.current_call_index.get("echo"))
            return [Forward(msg)]

    ctx = _ctx()
    fault = Capture()
    pipeline = new_pipeline(fault=fault)
    for id_ in (1, 2, 3):
        await pipeline.on_c2s(_call(id_, "echo"), ctx)
    assert fault.seen == [1, 2, 3]
    assert ctx.pending[(C2S, 3)].attempt == 3
    assert ctx.current_call_index == {"echo": 3}


@pytest.mark.asyncio
async def test_pending_call_fields() -> None:
    """A forwarded tools/call is registered with its method, tool and arguments."""
    ctx = _ctx()
    await new_pipeline().on_c2s(_call(5, "echo"), ctx)
    pending = ctx.pending[(C2S, 5)]
    assert isinstance(pending, PendingCall)
    assert pending.method == "tools/call"
    assert pending.tool_name == "echo"
    assert pending.arguments == {"city": "Berlin"}
    assert pending.attempt == 1
    assert pending.t_start > 0


@pytest.mark.asyncio
async def test_hold_stops_the_chain() -> None:
    """Hold ends the chain, so later stages never run and no call is pending."""

    class Holder(RecorderStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Hold the message, then forward it.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Hold(...)]`` with an inner Forward.
            """
            return [Hold(ms=10, then=Forward(msg))]

    calls: list[str] = []
    pipeline = new_pipeline(recorder=Holder(), guard=OrderStage("guard", calls))
    ctx = _ctx()
    actions = await pipeline.on_c2s(_call(1, "echo"), ctx)
    assert len(actions) == 1
    assert isinstance(actions[0], Hold)
    assert calls == []
    assert ctx.pending == {}


@pytest.mark.asyncio
async def test_dropped_request_is_not_pending() -> None:
    """Drop ends the chain, and the tool attempt is not counted."""

    class Dropper(GuardStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Drop the message.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Drop()]``.
            """
            return [Drop()]

    ctx = _ctx()
    actions = await new_pipeline(guard=Dropper()).on_c2s(_call(1, "echo"), ctx)
    assert actions == [Drop()]
    assert ctx.pending == {}
    assert ctx.call_counts == {}


def test_dump_is_compact() -> None:
    """A message parsed from compact JSON is forwarded byte for byte."""
    msg = _parse('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
    assert dump(msg) == msg.raw_bytes + b"\n"


def test_new_pipeline_fills_in_no_ops() -> None:
    """An omitted stage becomes a no-op instance of its class."""
    pipeline = new_pipeline()
    assert isinstance(pipeline.fault, FaultStage)
    assert isinstance(pipeline.guard, GuardStage)
    assert isinstance(pipeline.recorder, RecorderStage)


@pytest.mark.asyncio
async def test_default_s2c_stage_is_a_no_op() -> None:
    """An unmodified fault stage forwards the same object in the s2c direction."""
    msg = _result(1)
    assert await FaultStage().on_s2c(msg, _ctx()) == [Forward(msg)]


@pytest.mark.asyncio
async def test_tools_call_without_name_or_arguments() -> None:
    """A tools/call without a string name or object arguments is still forwarded."""
    ctx = _ctx()
    msg = _request(4, "tools/call", {"arguments": ["city"]})
    actions = await new_pipeline().on_c2s(msg, ctx)
    assert actions == [Forward(msg)]
    pending = ctx.pending[(C2S, 4)]
    assert pending.tool_name is None
    assert pending.arguments is None
    assert pending.attempt == 0


@pytest.mark.asyncio
async def test_guard_rewrite_reaches_the_next_stage() -> None:
    """The fault stage receives whatever the guard forwarded."""

    class Rewrite(GuardStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Forward a different request.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Forward(other)]``.
            """
            return [Forward(_call(7, "rewritten"))]

    class Capture(FaultStage):
        def __init__(self) -> None:
            self.seen: list[Message] = []

        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[object]:
            """Remember the message it was handed.

            Args:
                msg: The message.
                ctx: The episode context.

            Returns:
                ``[Forward(msg)]``.
            """
            self.seen.append(msg)
            return [Forward(msg)]

    fault = Capture()
    actions = await new_pipeline(guard=Rewrite(), fault=fault).on_c2s(_call(1, "echo"), _ctx())
    assert [msg.id for msg in fault.seen] == [7]
    assert actions == [Forward(_call(7, "rewritten"))]
