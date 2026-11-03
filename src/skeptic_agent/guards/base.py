"""Guard base classes and the guard engine stage (S4.4, S11).

This module defines:
- The ``Guard`` abstract base class for S11 guards.
- The unified ``loudify`` result helper (S4.5).
- Registry and discovery functions for concrete guard implementations.
- The ``GuardEngine`` stage mounting into the proxy pipeline adhering strictly
  to the S4.4 execution order.
"""

import inspect
from abc import ABC
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from skeptic_agent.faults.schedule import resolve_targets, tool_matches
from skeptic_agent.guards.presets import resolve_guards
from skeptic_agent.jsonrpc import ErrorResponse, Message, Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import (
    C2S,
    TOOLS_CALL,
    TOOLS_LIST,
    Action,
    Forward,
    GuardStage,
)

C2S_GUARD_ORDER: tuple[str, ...] = (
    "loop_breaker",  # G06: c2s step ②
    "injection_shield",  # G07: c2s step ③
    "drift_lock",  # G08: c2s check for drifted tools
)
"""Order of c2s guard hooks for tools/call according to S4.4."""

S2C_CALL_GUARD_ORDER: tuple[str, ...] = (
    "retry_guard",  # G05: s2c step ②
    "schema_guard",  # G02: s2c step ③
    "staleness_guard",  # G03: s2c step ③
    "emptiness_guard",  # G04: s2c step ③
    "evidence_contract",  # G01: s2c step ④
    "injection_shield",  # G07: s2c step ⑤
)
"""Order of s2c guard hooks for tools/call response according to S4.4."""

S2C_LIST_GUARD_ORDER: tuple[str, ...] = (
    "drift_lock",  # G08: s2c tools/list step ②
)
"""Order of s2c guard hooks for tools/list response according to S4.4."""


def loudify(text: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the unified loudify result format specified in S4.5.

    result := {"content": [{"type": "text", "text": <GUARD_TEXT>}], "isError": True}
    Preserves _meta when present.

    Args:
        text: The error text to place in content[0].text.
        meta: Optional _meta mapping to preserve.

    Returns:
        The tool result dictionary.
    """
    res: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "isError": True,
    }
    if meta is not None:
        res["_meta"] = dict(meta)
    return res


@dataclass(frozen=True)
class GuardSpec:
    """Specification for configuring one guard instance (S11).

    Attributes:
        guard_id: The guard id from S11.
        enabled: Whether this guard is enabled (default True).
        tools: Tool target glob or sequence of globs (default "*").
        params: Guard-specific configuration parameters.
    """

    guard_id: str
    enabled: bool = True
    tools: str | tuple[str, ...] = "*"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardResult:
    """Outcome of a guard processing a message.

    Attributes:
        msg: The message after guard processing (or original message).
        action: Optional pipeline action ending the chain (e.g. ReplyToClient).
        note: Optional cassette guard action record to attach.
    """

    msg: Message
    action: Action | None = None
    note: Mapping[str, Any] | None = None


class Guard(ABC):
    """Abstract base class for all S11 Guards.

    Attributes:
        id: S11 guard identifier.
        hooks: Tuple of hooks implemented by this guard:
            - 'c2s': client-to-server request
            - 's2c_call': server-to-client response for tools/call
            - 's2c_list': server-to-client response for tools/list
    """

    id: str
    hooks: tuple[str, ...]

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize guard with its specification.

        Args:
            spec: Optional guard specification; defaults to default spec for self.id.
        """
        self.spec = spec or GuardSpec(guard_id=self.id)
        self.enabled = self.spec.enabled
        self.tools = self.spec.tools
        self.params = self.spec.params

    def matches_tool(self, tool_name: str | None, scenario: Any = None) -> bool:
        """Check whether this guard targets the specified tool.

        Args:
            tool_name: Name of tool being called, or None for tools/list.
            scenario: Optional scenario object for resolving targets.

        Returns:
            True if this guard targets the tool.
        """
        if tool_name is None:
            return True
        if isinstance(self.tools, str):
            targets = resolve_targets(self.tools, scenario)
        else:
            targets = tuple(pattern for t in self.tools for pattern in resolve_targets(t, scenario))
        return tool_matches(tool_name, targets)

    def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
        """Process a client-to-server tools/call request.

        Args:
            msg: The client request.
            ctx: Episode context.

        Returns:
            GuardResult if the guard intervenes, None otherwise.
        """
        del msg, ctx
        return None

    def on_s2c_call(
        self, msg: Response | ErrorResponse, ctx: EpisodeContext, tool_name: str | None
    ) -> GuardResult | None:
        """Process a server-to-client tools/call response.

        Args:
            msg: Server response.
            ctx: Episode context.
            tool_name: Name of tool called.

        Returns:
            GuardResult if the guard intervenes, None otherwise.
        """
        del msg, ctx, tool_name
        return None

    def on_s2c_list(self, msg: Response | ErrorResponse, ctx: EpisodeContext) -> GuardResult | None:
        """Process a server-to-client tools/list response.

        Args:
            msg: Server response.
            ctx: Episode context.

        Returns:
            GuardResult if the guard intervenes, None otherwise.
        """
        del msg, ctx
        return None


REGISTRY: dict[str, type[Guard]] = {}
"""Registry of concrete Guard classes keyed by S11 guard id."""


def register(guard_cls: type[Guard]) -> type[Guard]:
    """Register a guard class.

    Args:
        guard_cls: Guard class to register.

    Returns:
        The registered class.
    """
    REGISTRY[guard_cls.id] = guard_cls
    return guard_cls


def get_guard(guard_id: str) -> type[Guard] | None:
    """Look up a guard class by id.

    Args:
        guard_id: S11 guard id.

    Returns:
        The registered Guard class, or None if not registered.
    """
    return REGISTRY.get(guard_id)


class GuardEngine(GuardStage):
    """Pipeline guard stage executing enabled guards in S4.4 order.

    Attributes:
        scenario: Scenario context for target resolution.
        recorder: Cassette recorder stage for logging guard notes.
    """

    def __init__(
        self,
        guards: Sequence[Guard | GuardSpec | str] = (),
        *,
        scenario: Any = None,
        recorder: Any = None,
    ) -> None:
        """Initialize the guard engine with enabled guards.

        Args:
            guards: Enabled guards (instances, specs, or guard id strings).
            scenario: Optional scenario object.
            recorder: Optional recorder for guard action notes.
        """
        self.scenario = scenario
        self.recorder = recorder
        self._guards_by_id: dict[str, Guard] = {}

        for item in guards:
            if isinstance(item, Guard):
                self._guards_by_id[item.id] = item
            elif isinstance(item, GuardSpec):
                cls = get_guard(item.guard_id)
                if cls is not None:
                    self._guards_by_id[item.guard_id] = cls(item)
            elif isinstance(item, str):
                cls = get_guard(item)
                if cls is not None:
                    self._guards_by_id[item] = cls(GuardSpec(guard_id=item))

    def set_recorder(self, recorder: Any) -> None:
        """Attach a recorder stage to receive guard notes.

        Args:
            recorder: Cassette recorder.
        """
        self.recorder = recorder

    def set_fault(self, fault: Any) -> None:
        """Attach a fault stage to the guard engine and child guards.

        Args:
            fault: FaultStage instance.
        """
        self.fault = fault
        for guard in self._guards_by_id.values():
            if hasattr(guard, "set_fault"):
                guard.set_fault(fault)

    def _note_guard(self, note: Mapping[str, Any]) -> None:
        """Report a guard action to the cassette recorder."""
        if self.recorder is not None and hasattr(self.recorder, "note_guard"):
            self.recorder.note_guard(note)

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Execute c2s guards on tools/call requests according to S4.4.

        Execution order:
        ② G06 (loop_breaker)
        ③ G07 (injection_shield)

        Args:
            msg: The client message.
            ctx: Episode context.

        Returns:
            List of actions (Forward or ReplyToClient).
        """
        if (
            not isinstance(msg, Request)
            or msg.method != TOOLS_CALL
            or not isinstance(msg.params, dict)
        ):
            return [Forward(msg)]

        tool_name = msg.params.get("name")
        if not isinstance(tool_name, str):
            return [Forward(msg)]

        scenario = ctx.scenario if ctx.scenario is not None else self.scenario
        current_msg: Request = msg

        for guard_id in C2S_GUARD_ORDER:
            guard = self._guards_by_id.get(guard_id)
            if guard is None or not guard.enabled or "c2s" not in guard.hooks:
                continue
            if not guard.matches_tool(tool_name, scenario):
                continue

            res = guard.on_c2s(current_msg, ctx)
            if inspect.isawaitable(res):
                res = await res
            if res is None:
                continue

            if res.note is not None:
                self._note_guard(res.note)

            if res.action is not None:
                return [res.action]

            if res.msg is not current_msg and isinstance(res.msg, Request):
                current_msg = res.msg.model_copy(update={"raw_bytes": b""})

        return [Forward(current_msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Execute s2c guards on responses according to S4.4.

        For tools/call responses:
        ② G05 (retry_guard)
        ③ G02 (schema_guard), G03 (staleness_guard), G04 (emptiness_guard)
        ④ G01 (evidence_contract)
        ⑤ G07 (injection_shield)

        For tools/list responses:
        ② G08 (drift_lock)

        Args:
            msg: The server response message.
            ctx: Episode context.

        Returns:
            List of actions.
        """
        message_id = msg.id if isinstance(msg, (Response, ErrorResponse)) else None
        if message_id is None:
            return [Forward(msg)]

        pending = ctx.pending.get((C2S, message_id))
        if pending is None:
            return [Forward(msg)]

        scenario = ctx.scenario if ctx.scenario is not None else self.scenario

        if pending.method == TOOLS_LIST:
            # Capture tool definitions seen on the wire into ctx.tool_defs
            if isinstance(msg, Response) and isinstance(msg.result, dict):
                tools = msg.result.get("tools")
                if isinstance(tools, list):
                    for tool in tools:
                        if (
                            isinstance(tool, dict)
                            and "name" in tool
                            and isinstance(tool["name"], str)
                        ):
                            ctx.tool_defs[tool["name"]] = tool

            current_msg: Message = msg
            for guard_id in S2C_LIST_GUARD_ORDER:
                guard = self._guards_by_id.get(guard_id)
                if guard is None or not guard.enabled or "s2c_list" not in guard.hooks:
                    continue
                if not isinstance(current_msg, (Response, ErrorResponse)):
                    continue
                res = guard.on_s2c_list(current_msg, ctx)
                if inspect.isawaitable(res):
                    res = await res
                if res is None:
                    continue
                if res.note is not None:
                    self._note_guard(res.note)
                if res.action is not None:
                    return [res.action]
                if res.msg is not current_msg:
                    current_msg = res.msg.model_copy(update={"raw_bytes": b""})
            return [Forward(current_msg)]

        if pending.method == TOOLS_CALL:
            current_msg = msg
            tool_name = pending.tool_name
            for guard_id in S2C_CALL_GUARD_ORDER:
                guard = self._guards_by_id.get(guard_id)
                if guard is None or not guard.enabled or "s2c_call" not in guard.hooks:
                    continue
                if not guard.matches_tool(tool_name, scenario):
                    continue
                if not isinstance(current_msg, (Response, ErrorResponse)):
                    continue
                res = guard.on_s2c_call(current_msg, ctx, tool_name)
                if inspect.isawaitable(res):
                    res = await res
                if res is None:
                    continue
                if res.note is not None:
                    self._note_guard(res.note)
                if res.action is not None:
                    return [res.action]
                if res.msg is not current_msg:
                    current_msg = res.msg.model_copy(update={"raw_bytes": b""})
            return [Forward(current_msg)]

        return [Forward(msg)]


def build_guard_engine(
    guards: str | Sequence[str] | Sequence[GuardSpec | Guard] | None,
    *,
    scenario: Any = None,
    recorder: Any = None,
) -> GuardEngine:
    """Build a GuardEngine from guard names, specs or presets.

    Args:
        guards: Guard preset name, comma-separated names, sequence of names or specs.
        scenario: Optional scenario object.
        recorder: Optional cassette recorder stage.

    Returns:
        Configured GuardEngine instance.
    """
    if guards is None:
        return GuardEngine([], scenario=scenario, recorder=recorder)

    if isinstance(guards, str):
        return GuardEngine(resolve_guards(guards), scenario=scenario, recorder=recorder)

    if isinstance(guards, Sequence) and all(isinstance(x, str) for x in guards):
        str_guards = [x for x in guards if isinstance(x, str)]
        return GuardEngine(resolve_guards(str_guards), scenario=scenario, recorder=recorder)

    return GuardEngine(guards, scenario=scenario, recorder=recorder)
