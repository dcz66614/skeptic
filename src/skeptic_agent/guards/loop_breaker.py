"""G06 Loop Breaker Guard (S11).

Intercepts repeated identical calls in the same episode:
In the same episode, when (tool, canonical args) appears
consecutively for threshold=3 times, block and reply with loud error:
[skeptic:loop_breaker] This exact call was already made <N> times with the same result.
Change your approach or report that the task cannot be completed.
"""

from typing import Any

from skeptic_agent.canonical import canonical_json
from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import Request, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import ReplyToClient

LOOP_BREAKER_TEXT_TEMPLATE: str = (
    "[skeptic:loop_breaker] This exact call was already made {n} times with the same result. "
    "Change your approach or report that the task cannot be completed."
)
"""The exact verbatim G06 text template specified in S11."""


@register
class LoopBreaker(Guard):
    """G06 loop_breaker Guard (S11, c2s step ②).

    Detects consecutive identical calls to the same tool with canonicalized arguments.
    Upon reaching threshold (default 3), the call is blocked and answered directly
    with a loudified error response.
    """

    id: str = "loop_breaker"
    hooks: tuple[str, ...] = ("c2s",)

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize LoopBreaker.

        Args:
            spec: Guard specification; threshold defaults to 3 if not specified.
        """
        super().__init__(spec)
        self.threshold: int = int(self.params.get("threshold", 3))
        self._episode_id: str | None = None
        self._prev_sig: tuple[str, str] | None = None
        self._consecutive: int = 0

    def reset(self) -> None:
        """Reset consecutive call counters."""
        self._prev_sig = None
        self._consecutive = 0

    def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
        """Inspect client request; intercept if consecutive identical call limit is reached.

        Args:
            msg: The client request.
            ctx: Episode context.

        Returns:
            GuardResult with ReplyToClient and note if tripped, None otherwise.
        """
        if not isinstance(msg.params, dict):
            return None

        tool_name = msg.params.get("name")
        if not isinstance(tool_name, str):
            return None

        # Reset state if context switched to a new episode
        if self._episode_id != ctx.episode_id:
            self._episode_id = ctx.episode_id
            self.reset()

        arguments: Any = msg.params.get("arguments")
        norm_args = canonical_json(arguments if isinstance(arguments, dict) else {})
        sig = (tool_name, norm_args)

        if sig == self._prev_sig:
            self._consecutive += 1
        else:
            self._consecutive = 1
            self._prev_sig = sig

        if self._consecutive >= self.threshold:
            err_text = LOOP_BREAKER_TEXT_TEMPLATE.format(n=self.threshold)
            err_result = loudify(err_text)
            reply = ReplyToClient(Response(id=msg.id, result=err_result))
            note = {
                "id": self.id,
                "action": "blocked",
                "detail": (
                    f"tool '{tool_name}' consecutive call {self._consecutive} "
                    f">= threshold {self.threshold}"
                ),
            }
            return GuardResult(msg=msg, action=reply, note=note)

        return None
