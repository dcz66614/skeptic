"""G03 Staleness Guard (S11).

Detects outdated dates in tool responses:
- Parameter ``max_age_days``=30 (default 30).
- Identifies all date leaves in the tool output:
  (a) If calling arguments contain date D, and no date in the result is within <= 1 day of D,
      loudify.
  (b) If all dates in the result are older than now (SKEPTIC_FROZEN_NOW or wall clock) by more
      than ``max_age_days`` days, loudify.
- Verbatim loud text format:
  "[skeptic:staleness_guard] Result dates do not match the request or are older than
   <N> days (<example_date>). Treat as stale."
"""

from __future__ import annotations

import contextlib
import datetime as dt
import os
import re
from typing import Any

from skeptic_agent.guards.base import Guard, GuardResult, GuardSpec, loudify, register
from skeptic_agent.jsonrpc import ErrorResponse, Response
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import C2S

STALENESS_GUARD_TEXT_TEMPLATE: str = (
    "[skeptic:staleness_guard] Result dates do not match the request or are older than "
    "{n} days ({example_date}). Treat as stale."
)
"""The exact verbatim G03 text template specified in S11."""

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.]+(Z|[+-]\d{2}:\d{2})?)?")
"""ISO date pattern matching standard ISO 8601 dates and timestamps (S6 S03)."""

_EXCLUDED_DATE_KEYS = frozenset({"created_at", "updated_at", "registered_at"})
"""Keys representing historical entity creation/modification rather than freshness dates."""


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


def _extract_dates(structured: Any, text: str | None) -> list[tuple[str, dt.date]]:
    """Extract all date strings and their parsed date objects from data and text."""
    dates: list[tuple[str, dt.date]] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        if raw in seen:
            return
        seen.add(raw)
        try:
            parsed = dt.date.fromisoformat(raw[:10])
            dates.append((raw, parsed))
        except ValueError:
            pass

    def _walk(curr: Any, key_name: str | None = None) -> None:
        if isinstance(curr, dict):
            for k, v in curr.items():
                _walk(v, str(k))
        elif isinstance(curr, list):
            for item in curr:
                _walk(item, key_name)
        elif isinstance(curr, str):
            if key_name and key_name.lower() in _EXCLUDED_DATE_KEYS:
                return
            if _DATE_PATTERN.fullmatch(curr.strip()):
                _add(curr.strip())

    import json

    data = structured
    if data is None and text:
        with contextlib.suppress(Exception):
            data = json.loads(text)

    if data is not None:
        _walk(data)
    elif text is not None:
        for m in _DATE_PATTERN.finditer(text):
            _add(m.group(0))

    return dates


def _extract_arg_dates(arguments: Any) -> list[dt.date]:
    """Extract any dates present in calling arguments."""
    arg_dates: list[dt.date] = []
    seen: set[str] = set()

    def _walk(curr: Any) -> None:
        if isinstance(curr, dict):
            for v in curr.values():
                _walk(v)
        elif isinstance(curr, list):
            for item in curr:
                _walk(item)
        elif isinstance(curr, str):
            for m in _DATE_PATTERN.finditer(curr):
                raw = m.group(0)
                if raw not in seen:
                    seen.add(raw)
                    with contextlib.suppress(ValueError):
                        arg_dates.append(dt.date.fromisoformat(raw[:10]))

    if isinstance(arguments, (dict, list)):
        _walk(arguments)
    return arg_dates


def _get_now_date(ctx: EpisodeContext) -> dt.date:
    """Determine 'now' date from environment, scenario frozen_now, or wall clock."""
    env_now = os.environ.get("SKEPTIC_FROZEN_NOW")
    if env_now:
        try:
            return dt.datetime.fromisoformat(env_now.replace("Z", "+00:00")).date()
        except ValueError:
            pass

    scenario = ctx.scenario
    if scenario is not None:
        frozen = getattr(scenario, "frozen_now", None)
        if frozen is None and isinstance(scenario, dict):
            frozen = scenario.get("frozen_now")
        if isinstance(frozen, str):
            try:
                return dt.datetime.fromisoformat(frozen.replace("Z", "+00:00")).date()
            except ValueError:
                pass

    return dt.datetime.now(dt.UTC).date()


@register
class StalenessGuard(Guard):
    """G03 staleness_guard Guard (S11, s2c step ③).

    Checks result dates against requested dates and age threshold (default 30 days).
    """

    id: str = "staleness_guard"
    hooks: tuple[str, ...] = ("s2c_call",)

    def __init__(self, spec: GuardSpec | None = None) -> None:
        """Initialize StalenessGuard."""
        super().__init__(spec)
        self.max_age_days: int = int(self.params.get("max_age_days", 30))

    def on_s2c_call(
        self, msg: Response | ErrorResponse, ctx: EpisodeContext, tool_name: str | None
    ) -> GuardResult | None:
        """Check server response dates for staleness or request mismatch.

        Args:
            msg: Server response.
            ctx: Episode context.
            tool_name: Name of tool called.

        Returns:
            GuardResult with loudified error response and note if stale, None otherwise.
        """
        del tool_name
        if not isinstance(msg, Response) or not isinstance(msg.result, dict):
            return None

        # S4.5: resultType other than "complete" is left alone
        if msg.result.get("resultType", "complete") != "complete":
            return None

        # Already an error result: do not overwrite
        if msg.result.get("isError") is True:
            return None

        result = msg.result
        structured = result.get("structuredContent")
        text = _first_text(result)

        result_dates = _extract_dates(structured, text)
        if not result_dates:
            return None

        pending = ctx.pending.get((C2S, msg.id)) if msg.id is not None else None
        arguments = pending.arguments if pending is not None else None
        arg_dates = _extract_arg_dates(arguments)
        now_date = _get_now_date(ctx)

        triggered = False
        example_date = result_dates[0][0]

        # (a) If calling arguments contain date D, and no date in result is within <= 1 day of D
        if arg_dates:
            matches_any_arg = any(
                any(abs((r_date - a_date).days) <= 1 for _, r_date in result_dates)
                for a_date in arg_dates
            )
            if not matches_any_arg:
                triggered = True
                example_date = result_dates[0][0]

        # (b) If all dates in result are older than now_date by more than max_age_days
        if not triggered:
            all_older = all(
                (now_date - r_date).days > self.max_age_days for _, r_date in result_dates
            )
            if all_older:
                triggered = True
                oldest = min(result_dates, key=lambda x: x[1])
                example_date = oldest[0]

        if not triggered:
            return None

        loud_text = STALENESS_GUARD_TEXT_TEMPLATE.format(
            n=self.max_age_days,
            example_date=example_date,
        )
        loud_res = loudify(loud_text, meta=result.get("_meta"))
        rewritten = msg.model_copy(update={"result": loud_res, "raw_bytes": b""})
        note = {
            "id": self.id,
            "action": "loudify",
            "detail": f"stale date: {example_date}",
        }
        return GuardResult(msg=rewritten, note=note)
