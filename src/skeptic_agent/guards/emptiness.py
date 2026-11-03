"""G04 Emptiness Guard (S11).

Detects empty, malformed, or truncated results:
- Conditions for loudification:
  1. structuredContent is {} or [].
  2. Text is empty (or both structuredContent and text are missing/empty).
  3. Text starts with '{' or '[' but fails to parse as JSON.
  4. For the same tool and same arguments in earlier calls of this episode,
     the maximum array length was n, and in this call it shrank to less than n/2.
- Parameter ``allow_empty_tools``=[]: Tool name globs exempt from emptiness checks.
- Verbatim loud text format:
  "[skeptic:emptiness_guard] Result is empty or truncated.
   Do not treat missing data as zero or as complete."
"""

from __future__ import annotations

import fnmatch
import json
from typing import Any

from skeptic_agent.canonical import canonical_json
from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import ErrorResponse, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import C2S

EMPTINESS_GUARD_TEXT: str = (
    "[skeptic:emptiness_guard] Result is empty or truncated. "
    "Do not treat missing data as zero or as complete."
)
"""The exact verbatim G04 text specified in S11."""


def _first_text(result: dict[str, Any]) -> str | None:
    """Extract text from the first type=='text' block in result['content']."""
    content = result.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                return text
    return None


def _find_array_lengths(obj: Any) -> list[int]:
    """Find lengths of all arrays present in a JSON-like data structure."""
    lengths: list[int] = []

    def _walk(curr: Any) -> None:
        if isinstance(curr, list):
            lengths.append(len(curr))
            for item in curr:
                _walk(item)
        elif isinstance(curr, dict):
            for val in curr.values():
                _walk(val)

    if obj is not None:
        _walk(obj)
    return lengths


@register
class EmptinessGuard(Guard):
    """G04 emptiness_guard Guard (S11, s2c step ③).

    Detects empty results, malformed JSON text, and truncated array data.
    """

    id: str = "emptiness_guard"
    hooks: tuple[str, ...] = ("s2c_call",)

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize EmptinessGuard."""
        super().__init__(spec)
        raw_allow = self.params.get("allow_empty_tools", [])
        if isinstance(raw_allow, str):
            self.allow_empty_tools: list[str] = [raw_allow]
        elif isinstance(raw_allow, (list, tuple, set)):
            self.allow_empty_tools = [str(x) for x in raw_allow]
        else:
            self.allow_empty_tools = []

        self._episode_id: str | None = None
        self._max_array_lens: dict[tuple[str, str], int] = {}

    def reset(self) -> None:
        """Reset per-episode array length tracking."""
        self._max_array_lens.clear()

    def _is_tool_allowed_empty(self, tool_name: str | None) -> bool:
        """Check if a tool is exempt from emptiness checks via allow_empty_tools."""
        if not tool_name or not self.allow_empty_tools:
            return False
        return any(fnmatch.fnmatch(tool_name, pattern) for pattern in self.allow_empty_tools)

    def on_s2c_call(
        self, msg: Response | ErrorResponse, ctx: EpisodeContext, tool_name: str | None
    ) -> GuardResult | None:
        """Check server response for emptiness, truncation, or malformed JSON.

        Args:
            msg: Server response.
            ctx: Episode context.
            tool_name: Name of tool called.

        Returns:
            GuardResult with loudified error response and note if empty/truncated,
            None otherwise.
        """
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        # S4.5: resultType other than "complete" is left alone
        if msg.result.get("resultType", "complete") != "complete":
            return None

        # Already an error result: do not overwrite
        if msg.result.get("isError") is True:
            return None

        # Exempt tools
        if self._is_tool_allowed_empty(tool_name):
            return None

        # Reset state on new episode
        if self._episode_id != ctx.episode_id:
            self._episode_id = ctx.episode_id
            self.reset()

        result = msg.result
        structured = result.get("structuredContent")
        text = _first_text(result)

        triggered = False
        reason = ""

        # Condition 1: structuredContent is {} or []
        if structured == {} or structured == []:
            triggered = True
            reason = "structuredContent is empty"

        # Condition 2: text is empty
        elif text is not None and text.strip() == "":
            triggered = True
            reason = "text block is empty"
        elif structured is None and (text is None or text.strip() == ""):
            triggered = True
            reason = "both structuredContent and text are missing or empty"

        # Condition 3: text starts with '{' or '[' but JSON parsing fails
        elif text is not None and (text.strip().startswith("{") or text.strip().startswith("[")):
            try:
                json.loads(text)
            except (ValueError, TypeError):
                triggered = True
                reason = "text starts with { or [ but failed to parse as JSON"

        # Condition 4: array length shrank to < n/2 for same tool and same arguments
        if not triggered:
            pending = ctx.pending.get((C2S, msg.id)) if msg.id is not None else None
            arguments = pending.arguments if pending is not None else None
            args_norm = canonical_json(arguments if isinstance(arguments, dict) else {})
            key = (tool_name or "", args_norm)

            data = structured
            if data is None and text:
                try:
                    data = json.loads(text)
                except (ValueError, TypeError):
                    data = None

            lengths = _find_array_lengths(data)
            curr_max = max(lengths) if lengths else 0

            prev_max = self._max_array_lens.get(key)
            if prev_max is not None and prev_max > 0:
                if curr_max < (prev_max / 2.0):
                    triggered = True
                    reason = (
                        f"array length shrank from {prev_max} to {curr_max} (< {prev_max / 2.0})"
                    )
                elif curr_max > prev_max:
                    self._max_array_lens[key] = curr_max
            else:
                if lengths:
                    self._max_array_lens[key] = curr_max

        if not triggered:
            return None

        loud_res = loudify(EMPTINESS_GUARD_TEXT, meta=result.get("_meta"))
        rewritten = msg.model_copy(update={"result": loud_res, "raw_bytes": b""})
        note = {
            "id": self.id,
            "action": "loudify",
            "detail": f"empty or truncated: {reason}",
        }
        return GuardResult(msg=rewritten, note=note)
