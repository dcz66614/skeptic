"""Per-episode proxy state (S4.3).

An ``EpisodeContext`` is the one object every pipeline stage sees. It carries the
episode identity, the protocol era, and the proxy's own bookkeeping: the pending
requests keyed by direction, the per-tool attempt counter and current attempt
(ADR-0007), the taint set, and the messages a stage asks the proxy to send after
the ones it already produced.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from skeptic_agent.protocol import Era

INTERNAL_ID_PREFIX: str = "skeptic-"
"""Every request the proxy sends upstream uses an id with this prefix (S4.3)."""


def new_internal_id() -> str:
    """Return a fresh id for a request the proxy itself sends upstream.

    Returns:
        ``"skeptic-<uuid4>"``.
    """
    return f"{INTERNAL_ID_PREFIX}{uuid.uuid4()}"


@dataclass(frozen=True)
class PendingCall:
    """A request sent upstream whose response has not arrived yet.

    Attributes:
        method: The JSON-RPC method, for example ``tools/call``.
        tool_name: The tool name, or ``None`` for a message without one.
        arguments: The tool arguments, or ``None``.
        t_start: The monotonic start time in seconds.
        attempt: The tool's attempt number, starting at 1; 0 when not counted.
    """

    method: str
    tool_name: str | None
    arguments: dict[str, Any] | None
    t_start: float
    attempt: int
    original_id: int | str | None = None
    retry_count: int = 0
    meta: dict[str, Any] | None = None


@dataclass
class EpisodeContext:
    """State shared by every stage for one episode.

    Attributes:
        episode_id: The episode identifier.
        seed: The random seed for this episode.
        era: The protocol era the client speaks.
        scenario: The scenario under test, when one is loaded.
        pending: Requests awaiting a response, keyed by ``(direction, id)``.
        call_counts: Counted ``tools/call`` attempts per tool name.
        current_call_index: The attempt number of the call being handled, per
            tool name; set before the fault pre hooks (ADR-0007).
        taint: Values marked by the Guard as untrusted.
        tool_defs: Tool definitions seen in ``tools/list`` responses.
        control: Actions a stage asks the proxy to send after its own actions,
            such as A03's ``notifications/tools/list_changed``.
    """

    episode_id: str
    seed: int
    era: Era
    scenario: Any = None
    pending: dict[tuple[str, int | str], PendingCall] = field(default_factory=dict)
    call_counts: dict[str, int] = field(default_factory=dict)
    current_call_index: dict[str, int] = field(default_factory=dict)
    taint: set[str] = field(default_factory=set)
    tool_defs: dict[str, Any] = field(default_factory=dict)
    control: list[Any] = field(default_factory=list)

    def next_call_index(self, tool: str) -> int:
        """Increment and return the attempt counter for a tool.

        The first attempt is 1, and the counter is shared by the whole episode,
        including retries the Guard starts. The pipeline calls this once per
        attempt before the fault pre hooks run (ADR-0007).

        Args:
            tool: The tool name.

        Returns:
            The new attempt number.
        """
        index = self.call_counts.get(tool, 0) + 1
        self.call_counts[tool] = index
        return index
