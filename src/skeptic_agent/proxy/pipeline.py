"""Interceptor pipeline for the client-to-server and server-to-client directions (S4.4).

Stages are plain objects with two async methods, ``on_c2s`` and ``on_s2c``, that
return a list of ``Action`` values. The ``Pipeline`` decides which stages run, in
which order, and turns their actions into the messages the transports send.
"""

import time
from dataclasses import dataclass
from typing import Any, Protocol

from skeptic_agent.jsonrpc import ErrorResponse, Message, Request, Response
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
    """

    ms: int
    then: Forward | ReplyToClient | SendToServer | Drop


Action = Forward | ReplyToClient | SendToServer | Drop | Hold
"""One thing the pipeline can do with a message."""


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


async def _run(
    stages: tuple[Stage, ...],
    msg: Message,
    ctx: EpisodeContext,
    *,
    c2s: bool,
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

    Returns:
        The stopping stage's actions, or one ``Forward`` of the final message
        when every stage forwarded.
    """
    current = msg
    for stage in stages:
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

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Process one client-to-server message.

        A ``tools/call`` runs recorder, guard and fault, then forwards; its
        attempt counter is incremented only when it is actually forwarded. A
        ``tools/list`` is only recorded and forwarded unchanged, like any other
        message, but a pending call with ``attempt=0`` is registered so its
        response still runs fault, guard and recorder. Any other message is only
        recorded and forwarded unchanged.

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
        actions = await _run((self.recorder, self.guard, self.fault), msg, ctx, c2s=True)
        if len(actions) == 1 and isinstance(actions[0], Forward):
            tool = _tool_name(msg)
            ctx.pending[(C2S, msg.id)] = PendingCall(
                method=msg.method,
                tool_name=tool,
                arguments=_tool_arguments(msg),
                t_start=time.monotonic(),
                attempt=ctx.next_call_index(tool) if tool is not None else 0,
            )
        return actions

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Process one server-to-client message.

        The matching pending c2s request decides the order. A ``tools/call`` or
        ``tools/list`` response runs fault, guard and recorder; the recorder
        records only the final message. Every other message is recorded and
        forwarded unchanged, and a response to an internal ``skeptic-`` id is
        dropped without reaching the client.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            The actions to take.
        """
        message_id = _request_id(msg)
        if message_id is not None and str(message_id).startswith(INTERNAL_ID_PREFIX):
            return [Drop()]
        key = (C2S, message_id)
        if message_id is None or key not in ctx.pending:
            return await _run((self.recorder,), msg, ctx, c2s=False)
        del ctx.pending[key]
        return await _run((self.fault, self.guard, self.recorder), msg, ctx, c2s=False)

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
