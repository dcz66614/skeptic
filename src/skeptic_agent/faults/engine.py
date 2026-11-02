"""The fault engine stage and the profile loader (S4.4, S7).

The engine schedules the faults of one episode and runs the registered hooks.
With no registered implementations it forwards every message unchanged, so the
pipeline behaves exactly as before F21-F24.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skeptic_agent.faults import adversarial, loud, silent  # noqa: F401  # importing registers the faults
from skeptic_agent.faults.base import Fault, FaultHook, FaultSpec
from skeptic_agent.faults.profiles import FaultEntry, Profile, ProfileError, load_profile
from skeptic_agent.faults.registry import get_fault
from skeptic_agent.faults.schedule import (
    CallIndex,
    Schedule,
    fault_rng,
    resolve_targets,
    tool_matches,
)
from skeptic_agent.jsonrpc import ErrorResponse, Message, Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import (
    C2S,
    TOOLS_CALL,
    TOOLS_LIST,
    Action,
    FaultStage,
    Forward,
    Hold,
    ReplyToClient,
    ReplyWithStatus,
)

FaultAction = Hold | ReplyToClient | ReplyWithStatus
"""An action a fault returns instead of a rewritten message."""

PROFILES_DIR = Path(__file__).resolve().parents[1] / "data" / "profiles"
"""Where the built-in profiles live; F25 fills it."""


@dataclass
class ScheduledFault:
    """One fault of the episode plan with its state.

    Attributes:
        spec: The scheduled fault.
        fault: The implementation, or ``None`` when the id is not registered.
        schedule: The trigger state for this (episode, fault, tool).
    """

    spec: FaultSpec
    fault: Fault | None
    schedule: Schedule


def spec_from_entry(entry: FaultEntry) -> FaultSpec:
    """Build a ``FaultSpec`` from a profile entry.

    Args:
        entry: A profile fault entry.

    Returns:
        The scheduled fault.
    """
    call_index: CallIndex = entry.call_index
    return FaultSpec(
        fault_id=entry.id,
        tool=entry.target,
        call_index=call_index,
        probability=entry.probability,
        persistence=entry.persistence,
        n=entry.n,
        p=entry.p,
        permanent_p=entry.permanent_p,
        params=entry.params,
    )


class FaultEngine(FaultStage):
    """Schedule and apply the faults of one episode (S4.4, S7).

    Attributes:
        scenario: The scenario used to resolve ``$primary`` and friends.
        planned: One entry per scheduled fault, with its trigger state.
    """

    def __init__(
        self,
        specs: Iterable[FaultSpec] = (),
        *,
        scenario: object | None = None,
        recorder: Any = None,
    ) -> None:
        """Prepare one schedule per scheduled fault.

        Args:
            specs: The faults to schedule.
            scenario: The scenario used to resolve ``$primary`` and friends.
        """
        self.scenario = scenario
        self.recorder = recorder
        self.specs = tuple(specs)
        self._bound = False
        self.planned: list[ScheduledFault] = [
            ScheduledFault(
                spec=spec,
                fault=(fault_cls() if (fault_cls := get_fault(spec.fault_id)) else None),
                schedule=Schedule(
                    call_index=spec.call_index,
                    probability=spec.probability,
                    persistence=spec.persistence,  # type: ignore[arg-type]
                    n=spec.n,
                    p=spec.p,
                    permanent_p=spec.permanent_p,
                ),
            )
            for spec in self.specs
        ]

    def bind(self, ctx: EpisodeContext) -> None:
        """Seed every schedule with the RNG of this episode and tool (S7.3).

        The key uses the tool name of the call the fault fires in, from
        ``ctx.current_call_index`` when it has one, otherwise the first
        resolved target, otherwise the target expression itself.

        Args:
            ctx: The episode context.
        """
        if ctx.scenario is None and self.scenario is not None:
            ctx.scenario = self.scenario
        scenario = ctx.scenario if ctx.scenario is not None else self.scenario
        for planned in self.planned:
            patterns = resolve_targets(planned.spec.tool, scenario)
            tool = next(
                (name for name in ctx.current_call_index if tool_matches(name, patterns)),
                patterns[0] if patterns else planned.spec.tool,
            )
            planned.schedule.rng = fault_rng(ctx.seed, ctx.episode_id, planned.spec.fault_id, tool)
        self._bound = True

    def set_recorder(self, recorder: Any) -> None:
        """Attach a recorder stage to receive fault notes."""
        self.recorder = recorder

    def _ensure_bound(self, ctx: EpisodeContext) -> None:
        """Seed schedules on the first message when ``bind`` was not called.

        Args:
            ctx: The episode context.
        """
        if not self._bound:
            self.bind(ctx)

    def _apply(
        self,
        hook: FaultHook,
        tool: str | None,
        index: int | None,
        ctx: EpisodeContext,
        payload: Message,
    ) -> tuple[Message, FaultAction | None]:
        """Run the faults whose hook and target match, in profile order.

        ``applicable`` is checked before the schedule rolls, so a fault that
        cannot run does not consume a firing. ``index is None`` is a
        ``tools/list`` event and ignores ``when.call_index``. A firing fault may
        return an action instead of a message (L01 holds its reply); the first
        such action ends the chain and is returned with the message that was
        current at that point.

        Only a ``list`` hook rolls ``next_event``. A target-less fault that
        implements ``post_call`` is listed on a ``tools/list`` response too, but
        a list event is not its hook, so it does not use up one of its firings.

        Args:
            hook: The hook being run.
            tool: The tool name, or ``None`` for ``tools/list``.
            index: The attempt number, or ``None`` for a list event.
            ctx: The episode context.
            payload: The message handed to ``apply``.

        Returns:
            The message after every firing fault has rewritten it, and the hold
            a fault asked for, if any.
        """
        if ctx.scenario is None and self.scenario is not None:
            ctx.scenario = self.scenario
        scenario = ctx.scenario if ctx.scenario is not None else self.scenario
        current = payload
        for planned in self.planned:
            fault = planned.fault
            if fault is None or hook not in fault.hooks or not fault.applicable(ctx):
                continue
            if tool is not None and not tool_matches(
                tool, resolve_targets(planned.spec.tool, scenario)
            ):
                continue
            if index is not None:
                fired = planned.schedule.next_trigger(index)
            elif hook == "list":
                # S4.4 puts every list-hook fault before any Guard, so no Guard
                # can block the rewrite: the list event counts as a firing.
                fired = planned.schedule.next_event()
            else:
                # ``index is None`` here only happens on a ``tools/list``: a
                # post_call fault that is never reached keeps its firings.
                continue
            if not fired:
                continue
            rewritten = fault.apply(current, planned.spec, ctx)
            if self.recorder is not None and hasattr(self.recorder, "note_fault"):
                self.recorder.note_fault(
                    {
                        "id": planned.spec.fault_id,
                        "params": dict(planned.spec.params) if planned.spec.params else {},
                        "call_index": index or 1,
                    }
                )
            if isinstance(rewritten, (Hold, ReplyToClient, ReplyWithStatus)):
                return current, rewritten
            if isinstance(rewritten, Message):
                if rewritten is not current:
                    # S4.1: a modified message is serialized in the compact form,
                    # never forwarded with the upstream bytes it was copied from.
                    rewritten = rewritten.model_copy(update={"raw_bytes": b""})
                current = rewritten
        return current, None

    def _drain_control(self, ctx: EpisodeContext, actions: list[Action]) -> list[Action]:
        """Append the actions a fault queued on ``ctx.control``.

        Only ``tools/list`` responses are followed this way, which is the one
        place a fault may ask the proxy to speak on its own (A03's list-changed
        notification).

        Args:
            ctx: The episode context.
            actions: The actions built so far.

        Returns:
            The actions, with the queued ones last.
        """
        if not ctx.control:
            return actions
        queued = list(ctx.control)
        ctx.control.clear()
        return [*actions, *queued]

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the pre_call hooks of a ``tools/call``.

        The pipeline has already stored this attempt on
        ``ctx.current_call_index`` (ADR-0007). With no implementation
        registered, the message is forwarded unchanged.

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``, possibly rewritten by a firing fault.
        """
        self._ensure_bound(ctx)
        if isinstance(msg, Request) and msg.method == TOOLS_CALL and isinstance(msg.params, dict):
            name = msg.params.get("name")
            if isinstance(name, str):
                msg, action = self._apply(
                    "pre_call", name, ctx.current_call_index.get(name, 0), ctx, msg
                )
                if action is not None:
                    return [action]
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Run the post_call or list hook of the matching request.

        The pipeline still holds the pending call, so a post hook reads that
        call's ``attempt`` and writes it back onto ``current_call_index``.
        A ``tools/list`` response is not a counted attempt. With no
        implementation registered, the message is forwarded unchanged.

        Args:
            msg: The message as the server sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``, possibly rewritten by a firing fault.
        """
        self._ensure_bound(ctx)
        message_id = msg.id if isinstance(msg, (Response, ErrorResponse)) else None
        if message_id is None:
            return [Forward(msg)]
        pending = ctx.pending.get((C2S, message_id))
        if pending is None:
            return [Forward(msg)]
        action: FaultAction | None = None
        if pending.method == TOOLS_LIST:
            msg, action = self._apply("list", None, None, ctx, msg)
            if action is not None:
                return self._drain_control(ctx, [action])
            return self._drain_control(ctx, [Forward(msg)])
        if pending.tool_name is not None:
            ctx.current_call_index[pending.tool_name] = pending.attempt
            msg, action = self._apply("post_call", pending.tool_name, pending.attempt, ctx, msg)
        if action is not None:
            return [action]
        return [Forward(msg)]


def load_profile_source(source: str | Path) -> Profile:
    """Resolve the CLI ``--profile`` value to a profile.

    A YAML path loads that file; a name loads ``PROFILES_DIR/<name>.yaml``.

    Args:
        source: A YAML path or a built-in profile name.

    Returns:
        The profile.

    Raises:
        ProfileError: When neither the path nor the built-in profile exists or
            when the file does not match ``skeptic.profile/v1``.
    """
    path = Path(source)
    if path.suffix in {".yaml", ".yml"} or path.exists():
        return load_profile(path)
    built_in = PROFILES_DIR / f"{source}.yaml"
    if built_in.is_file():
        return load_profile(built_in)
    raise ProfileError(f"unknown profile: {source!r}")
