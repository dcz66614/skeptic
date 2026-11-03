"""Interceptor pipeline for the client-to-server and server-to-client directions (S4.4).

Stages are plain objects with two async methods, ``on_c2s`` and ``on_s2c``, that
return a list of ``Action`` values. The ``Pipeline`` decides which stages run, in
which order, and turns their actions into the messages the transports send.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from skeptic_agent.jsonrpc import ErrorResponse, Message, Notification, Request, Response
from skeptic_agent.proxy.context import (
    INTERNAL_ID_PREFIX,
    EpisodeContext,
    PendingCall,
    new_internal_id,
)

C2S: str = "c2s"
"""The pending-call direction key for requests going to the server."""

S2C: str = "s2c"
"""The pending-call direction key for responses coming from the server."""

TOOLS_CALL: str = "tools/call"
"""The method of a tool invocation."""

TOOLS_LIST: str = "tools/list"
"""The method of a tool listing."""


@dataclass(frozen=True)
class Forward:
    """Send the message unchanged to the other side, byte for byte.

    Attributes:
        msg: The message to forward.
    """

    msg: Message


@dataclass(frozen=True)
class ReplyToClient:
    """Answer the client without contacting the server.

    Attributes:
        msg: The message to send to the client.
    """

    msg: Message


@dataclass(frozen=True)
class ReplyWithStatus:
    """Answer the client with a bare HTTP status instead of a message.

    Only the HTTP transport can send it (L04); the stdio proxy has no status
    line to write, so it ignores the action (S6).

    Attributes:
        status: The HTTP status code.
    """

    status: int


@dataclass(frozen=True)
class SendToServer:
    """Send a message to the server.

    Attributes:
        msg: The message to send to the server.
    """

    msg: Message


@dataclass(frozen=True)
class Drop:
    """Discard the message."""


@dataclass(frozen=True)
class Hold:
    """Delay the message before continuing with a follow-up action.

    Attributes:
        ms: The delay in milliseconds.
        then: The action to take after the delay.
        unless_cancelled: A request id. When the client cancels that request
            before the delay ends, ``then`` is replaced by ``Drop`` (L01).
            ``None`` always performs ``then``.
    """

    ms: int
    then: Forward | ReplyToClient | ReplyWithStatus | SendToServer | Drop
    unless_cancelled: int | str | None = None


Action = Forward | ReplyToClient | ReplyWithStatus | SendToServer | Drop | Hold
"""One thing the pipeline can do with a message."""

CANCELLED: str = "notifications/cancelled"
"""The client's request to abandon one call (L01)."""


def cancelled_id(msg: Message) -> int | str | None:
    """Return the request id a ``notifications/cancelled`` message cancels.

    Args:
        msg: Any message.

    Returns:
        ``params.requestId`` when ``msg`` cancels a request, else ``None``.
    """
    if isinstance(msg, Notification) and msg.method == CANCELLED:
        params = msg.params if isinstance(msg.params, dict) else {}
        request_id = params.get("requestId")
        if isinstance(request_id, int | str) and not isinstance(request_id, bool):
            return request_id
    return None


class Interceptor(Protocol):
    """A pipeline stage that can inspect and rewrite messages in both directions."""

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Handle a client-to-server message.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            The actions to take.
        """
        ...

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Handle a server-to-client message.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            The actions to take.
        """
        ...


class FaultStage:
    """Mount point for the fault injector (S7)."""

    def counts_attempts(self) -> bool:
        """Report whether this stage counts ``tools/call`` attempts itself.

        Returns:
            ``False``: the pipeline assigns ``call_index`` before the stage runs
            (ADR-0007). A stage that needs to count differently overrides this.
        """
        return False

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the fault pre hooks; by default forward unchanged.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the fault post hooks; by default forward unchanged.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]


class GuardStage:
    """Mount point for the Guards (S6)."""

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the c2s Guards; by default forward unchanged.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the s2c Guards; by default forward unchanged.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]


class RecorderStage:
    """Mount point for the cassette recorder (S5)."""

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Record a c2s message; by default record nothing.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Record an s2c message; by default record nothing.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        return [Forward(msg)]


Stage = FaultStage | GuardStage | RecorderStage
"""A pipeline stage object; each override may return ``list[Action]``."""


def _request_id(msg: Message) -> int | str | None:
    """Return the id of a request or response, or ``None``.

    Args:
        msg: Any message.

    Returns:
        The id, or ``None`` for a notification.
    """
    if isinstance(msg, (Request, Response, ErrorResponse)):
        return msg.id
    return None


def _tool_name(msg: Request) -> str | None:
    """Return the tool name of a ``tools/call`` request.

    Args:
        msg: A request.

    Returns:
        ``params.name`` when it is a string, else ``None``.
    """
    if msg.method != TOOLS_CALL or not isinstance(msg.params, dict):
        return None
    name = msg.params.get("name")
    return name if isinstance(name, str) else None


def _tool_arguments(msg: Request) -> dict[str, Any] | None:
    """Return the arguments of a ``tools/call`` request.

    Args:
        msg: A request.

    Returns:
        ``params.arguments`` when it is an object, else ``None``.
    """
    if not isinstance(msg.params, dict):
        return None
    arguments = msg.params.get("arguments")
    return arguments if isinstance(arguments, dict) else None


def _tool_meta(msg: Request) -> dict[str, Any] | None:
    """Return the _meta object of a ``tools/call`` request if present.

    Args:
        msg: A request.

    Returns:
        ``params._meta`` when it is a dict, else ``None``.
    """
    if not isinstance(msg.params, dict):
        return None
    meta = msg.params.get("_meta")
    return meta if isinstance(meta, dict) else None


async def _run(
    stages: tuple[Stage, ...],
    msg: Message,
    ctx: EpisodeContext,
    *,
    c2s: bool,
    before_fault: Callable[[Message], None] | None = None,
) -> list[Action]:
    """Pass a message through the stages until one stops the chain.

    Each stage sees the message as it currently stands. A stage that returns
    ``[Forward(next)]`` hands ``next`` to the following stage; any other result
    ends the chain and is returned as is.

    Args:
        stages: The stages to call, in order.
        msg: The message entering the chain.
        ctx: The episode context.
        c2s: ``True`` to call ``on_c2s``, ``False`` to call ``on_s2c``.
        before_fault: Called with the message just before the fault stage runs,
            after every earlier stage has forwarded it.

    Returns:
        The stopping stage's actions, or one ``Forward`` of the final message
        when every stage forwarded.
    """
    current = msg
    for stage in stages:
        if isinstance(stage, FaultStage) and before_fault is not None:
            before_fault(current)
        if c2s:
            actions = await stage.on_c2s(current, ctx)
        else:
            actions = await stage.on_s2c(current, ctx)
        if len(actions) != 1 or not isinstance(actions[0], Forward):
            return actions
        current = actions[0].msg
    return [Forward(current)]


class Pipeline:
    """Route messages through the S4.4 stage order.

    Attributes:
        fault: The fault stage.
        guard: The guard stage.
        recorder: The recorder stage.
    """

    def __init__(self, fault: FaultStage, guard: GuardStage, recorder: RecorderStage) -> None:
        """Build a pipeline from three stages.

        Args:
            fault: The fault stage.
            guard: The guard stage.
            recorder: The recorder stage.
        """
        self.fault = fault
        self.guard = guard
        self.recorder = recorder
        if hasattr(fault, "set_recorder"):
            fault.set_recorder(recorder)
        if hasattr(guard, "set_recorder"):
            guard.set_recorder(recorder)
        if hasattr(guard, "set_fault"):
            guard.set_fault(fault)

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Process one client-to-server message.

        A ``tools/call`` runs recorder, guard and fault. After the Guard lets it
        through, and before the fault pre hooks, the pipeline assigns the
        attempt number (ADR-0007) unless the fault stage counts attempts
        itself. The same number is stored on ``ctx.current_call_index`` and on
        the pending call. A ``tools/list`` is only recorded and forwarded
        unchanged, like any other message, but a pending call with
        ``attempt=0`` is registered so its response still runs fault, guard and
        recorder. Any other message is only recorded and forwarded unchanged.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            The actions to take.
        """
        if not isinstance(msg, Request):
            return await _run((self.recorder,), msg, ctx, c2s=True)
        if msg.method == TOOLS_LIST:
            ctx.pending[(C2S, msg.id)] = PendingCall(
                method=msg.method,
                tool_name=None,
                arguments=None,
                t_start=time.monotonic(),
                attempt=0,
            )
            return await _run((self.recorder,), msg, ctx, c2s=True)
        if msg.method != TOOLS_CALL:
            return await _run((self.recorder,), msg, ctx, c2s=True)

        def count_attempt(current: Message) -> None:
            """Assign the attempt number of a call entering the fault stage (ADR-0007).

            Args:
                current: The request as the guard forwarded it.
            """
            if not isinstance(current, Request) or self.fault.counts_attempts():
                return
            tool = _tool_name(current)
            if tool is None:
                return
            index = ctx.next_call_index(tool)
            ctx.current_call_index[tool] = index
            ctx.pending[(C2S, current.id)] = PendingCall(
                method=current.method,
                tool_name=tool,
                arguments=_tool_arguments(current),
                t_start=time.monotonic(),
                attempt=index,
                meta=_tool_meta(current),
            )

        actions = await _run(
            (self.recorder, self.guard, self.fault), msg, ctx, c2s=True, before_fault=count_attempt
        )
        if len(actions) == 1 and isinstance(actions[0], Forward):
            pending = ctx.pending.get((C2S, msg.id))
            if pending is None:
                ctx.pending[(C2S, msg.id)] = PendingCall(
                    method=msg.method,
                    tool_name=_tool_name(msg),
                    arguments=_tool_arguments(msg),
                    t_start=time.monotonic(),
                    attempt=0,
                    meta=_tool_meta(msg),
                )
        return actions

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Process one server-to-client message.

        The matching pending c2s request decides the order. A ``tools/call`` or
        ``tools/list`` response runs fault, guard and recorder; the recorder
        records only the final message. The pending call stays visible for that
        chain so the fault post hooks can read its ``attempt`` (ADR-0007), and
        is removed before this method returns. Every other message is recorded
        and forwarded unchanged, and a response to an internal ``skeptic-`` id
        is dropped without reaching the client.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            The actions to take.
        """
        message_id = _request_id(msg)
        if message_id is not None and str(message_id).startswith(INTERNAL_ID_PREFIX):
            if (C2S, message_id) not in ctx.pending:
                return [Drop()]
        elif message_id is None or (C2S, message_id) not in ctx.pending:
            return await _run((self.recorder,), msg, ctx, c2s=False)
        key = (C2S, message_id)
        try:
            actions = await _run((self.fault, self.guard, self.recorder), msg, ctx, c2s=False)
            if len(actions) == 1 and isinstance(actions[0], Forward):
                final_id = _request_id(actions[0].msg)
                if final_id is not None and str(final_id).startswith(INTERNAL_ID_PREFIX):
                    return [Drop()]
            return actions
        finally:
            ctx.pending.pop(key, None)

    def send_to_server(self, method: str, params: dict[str, Any]) -> SendToServer:
        """Build a request the proxy sends on its own behalf.

        The id is a ``skeptic-<uuid4>`` id, which marks it as internal so the
        client never sees its response (S4.3).

        Args:
            method: The JSON-RPC method.
            params: The request params.

        Returns:
            A ``SendToServer`` action.
        """
        return SendToServer(Request(id=new_internal_id(), method=method, params=params))


def new_pipeline(
    fault: FaultStage | None = None,
    guard: GuardStage | None = None,
    recorder: RecorderStage | None = None,
) -> Pipeline:
    """Build a pipeline, filling in the no-op stage for every stage omitted.

    Args:
        fault: The fault stage, or ``None`` for a no-op one.
        guard: The guard stage, or ``None`` for a no-op one.
        recorder: The recorder stage, or ``None`` for a no-op one.

    Returns:
        The pipeline.
    """
    return Pipeline(
        fault=fault if fault is not None else FaultStage(),
        guard=guard if guard is not None else GuardStage(),
        recorder=recorder if recorder is not None else RecorderStage(),
    )
