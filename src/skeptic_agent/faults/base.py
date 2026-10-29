"""Fault base class and the hook contract (S4.4, S6).

A fault subclass decides where it runs with ``hooks`` and whether it can run at
all with ``applicable``. This module only defines the shape; the concrete faults
arrive in F21-F24.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from skeptic_agent.faults.schedule import CallIndex
from skeptic_agent.proxy.context import EpisodeContext

FaultClass = Literal["loud", "silent", "adversarial"]
"""The three fault classes of S6."""

FaultHook = Literal["pre_call", "post_call", "list"]
"""Where a fault runs: before forwarding a call, on its response, or on tools/list."""


@dataclass(frozen=True)
class FaultSpec:
    """One scheduled fault as expanded for an episode (S7.1, S7.4).

    Attributes:
        fault_id: The fault id, for example ``S04``.
        tool: The resolved tool target, a glob or the scenario tool name.
        call_index: The attempts to fire on.
        probability: The chance of firing when an attempt qualifies.
        persistence: The persistence mode.
        n: The run length of ``transient``.
        p: The per-attempt chance of ``intermittent``.
        permanent_p: The permanent branch chance of ``mixed``.
        params: The fault-specific parameters.
    """

    fault_id: str
    tool: str
    call_index: CallIndex
    probability: float
    persistence: str
    n: int = 1
    p: float = 0.5
    permanent_p: float = 0.6
    params: dict[str, Any] | None = None


class Fault(ABC):
    """One fault implementation.

    Attributes:
        id: The fault id from S6, for example ``S04``.
        cls: The fault class: loud, silent or adversarial.
        hooks: The hooks the fault implements.
    """

    id: str
    cls: FaultClass
    hooks: tuple[FaultHook, ...]

    def applicable(self, ctx: EpisodeContext) -> bool:
        """Report whether the runtime context carries everything the fault needs.

        Args:
            ctx: The episode context.

        Returns:
            ``True`` when the fault can run against this context.
        """
        return True

    def on_request(self, spec: FaultSpec, ctx: EpisodeContext) -> None:
        """Notice a ``tools/call`` the client is about to send.

        The engine calls this after the pipeline assigned the attempt number and
        before the pre hooks run, for every planned fault, whichever tools it
        targets. A fault that does not run on the call but must count calls to
        the whole scenario (A03) counts them here.

        Args:
            spec: The scheduled fault.
            ctx: The episode context.
        """
        del spec, ctx

    @abstractmethod
    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Inject the fault into the payload of the hook that fired.

        A fault normally returns the rewritten payload. It may instead return a
        ``ReplyToClient`` to answer the client itself, or a ``Hold`` to delay
        that answer (L01). The engine ends the chain at the first such action.

        Args:
            payload: The message fields the hook handed over.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten payload, or a ``ReplyToClient`` or ``Hold`` action.
        """
        ...
