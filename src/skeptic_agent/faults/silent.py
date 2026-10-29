"""Silent faults S01-S05 (S4.5, S6).

A silent fault leaves the response looking successful: ``isError`` stays absent
or false and every content block keeps its type. Only the data changes.

The four response faults share one writer. When a result carries both
``structuredContent`` and a text block that parses to the same document, the
writer rewrites the text block as well (S4.5); otherwise the text block follows
the fault's own plain-text fallback. A fault that finds nothing to change
returns the message untouched, and the engine records no firing.
"""

import datetime as dt
import json
import math
import re
from typing import Any

from skeptic_agent.faults.base import Fault, FaultSpec
from skeptic_agent.faults.registry import register
from skeptic_agent.jsonrpc import Message, Request, Response
from skeptic_agent.jsonsel import first_numeric_leaf, get_first, set_first
from skeptic_agent.proxy.context import EpisodeContext

S02_RATIO = 0.3
"""The default S02 ``ratio`` (S6)."""

S03_DAYS = 400
"""The default S03 ``days`` (S6)."""

S04_FACTOR = 10
"""The default S04 ``factor`` (S6)."""

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}(T[\d:.]+(Z|[+-]\d{2}:\d{2})?)?")
"""The S03 date format; it is anchored where S6 anchors it (see ``_shift_dates``)."""

_NUMBER_PATTERN = re.compile(r"-?\d+(\.\d+)?")
"""The first number S04 scales in plain text (S6)."""


def _params(spec: FaultSpec) -> dict[str, Any]:
    """Return the fault-specific parameters, never ``None``.

    Args:
        spec: The scheduled fault.

    Returns:
        The parameters mapping.
    """
    return spec.params or {}


def _result_of(msg: Message) -> dict[str, Any] | None:
    """Return a mutable copy of a successful response's ``result`` object.

    A ``resultType`` other than ``"complete"`` is left alone (S4.5), as is a
    response that is already an error or whose result is not an object.

    Args:
        msg: The message a fault is about to rewrite.

    Returns:
        A fresh ``result`` dict to edit, or ``None`` when S4.5 skips the message.
    """
    if not isinstance(msg, Response) or not isinstance(msg.result, dict):
        return None
    if msg.result.get("resultType", "complete") != "complete":
        return None
    return dict(msg.result)


def _with_result(msg: Response, result: dict[str, Any]) -> Response:
    """Return a copy of a response carrying a new result.

    Args:
        msg: The original response.
        result: The new ``result`` object.

    Returns:
        The rewritten response.
    """
    return msg.model_copy(update={"result": result})


def _first_text_block(result: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first ``type == "text"`` content block.

    Args:
        result: A tool result object.

    Returns:
        The block, or ``None`` when the content holds none.
    """
    blocks = result.get("content")
    if not isinstance(blocks, list):
        return None
    return next(
        (block for block in blocks if isinstance(block, dict) and block.get("type") == "text"),
        None,
    )


def _text_of(result: dict[str, Any]) -> str | None:
    """Return the text of the first text block.

    Args:
        result: A tool result object.

    Returns:
        The text, or ``None`` when there is no text block or its text is not a
        string.
    """
    block = _first_text_block(result)
    text = block.get("text") if block is not None else None
    return text if isinstance(text, str) else None


def _parse_json(text: str) -> Any:
    """Parse text as JSON.

    Args:
        text: The text of a content block.

    Returns:
        The decoded value, or ``None`` when the text is not JSON.
    """
    try:
        return json.loads(text)
    except ValueError:
        return None


def _text_is_synced(result: dict[str, Any], structured: Any) -> bool:
    """Report whether the first text block is a JSON copy of ``structured``.

    Args:
        result: A tool result object.
        structured: The result's ``structuredContent``.

    Returns:
        ``True`` when the block parses to a document deep-equal to
        ``structured`` (S4.5).
    """
    text = _text_of(result)
    return text is not None and _parse_json(text) == structured


def _set_text(result: dict[str, Any], text: str) -> None:
    """Replace the text of the first text block.

    Args:
        result: The result whose text block is to be rewritten.
        text: The new block text.
    """
    block = _first_text_block(result)
    if block is not None:
        block["text"] = text


def _sync_text(result: dict[str, Any], structured: Any) -> None:
    """Write ``structured`` back into the first text block (S4.5).

    Args:
        result: The result whose text block is to be rewritten.
        structured: The new ``structuredContent``.
    """
    _set_text(result, json.dumps(structured, ensure_ascii=False, sort_keys=True))


def _truncate_text(text: str | None, ratio: float) -> str:
    """Return the leading ``floor(len * ratio)`` characters of a text block (S6, S02).

    Args:
        text: The text block's text, or ``None`` when there is none.
        ratio: The fraction of the text to keep.

    Returns:
        The shortened text; the whole text when the ratio keeps all of it.
    """
    if text is None:
        return ""
    keep = math.floor(len(text) * ratio)
    return text[:keep] if keep < len(text) else text


def _copy(value: Any) -> Any:
    """Return a deep copy through JSON, which is enough for result documents.

    Args:
        value: A JSON-compatible value.

    Returns:
        A structurally equal copy sharing no containers.
    """
    return json.loads(json.dumps(value))


def _walk_lists(value: Any) -> list[list[Any]]:
    """Return every list in a document, in insertion-order depth-first traversal.

    Args:
        value: A JSON-compatible document.

    Returns:
        The lists, parents before children.
    """
    found: list[list[Any]] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            found.append(current)
            stack.extend(reversed(current))
    return found


def _longest_list(value: Any) -> list[Any] | None:
    """Return the longest list in a document, the first one when several tie.

    Args:
        value: A JSON-compatible document.

    Returns:
        The list, or ``None`` when the document holds no list.
    """
    lists = _walk_lists(value)
    if not lists:
        return None
    return max(lists, key=len)


def _truncate_longest_list(value: Any, ratio: float) -> tuple[Any, bool]:
    """Keep only the leading ``ceil(len * ratio)`` items of the longest list (S6, S02).

    Args:
        value: The document whose ``structuredContent`` is rewritten.
        ratio: The fraction of items to keep.

    Returns:
        The edited copy and whether any item was removed.
    """
    lists = _walk_lists(value)
    if not lists:
        return value, False
    target = max(lists, key=len)
    keep = math.ceil(len(target) * ratio)
    if keep >= len(target):
        return value, False
    position = lists.index(target)
    edited = _copy(value)
    _walk_lists(edited)[position][:] = target[:keep]
    return edited, True


def _shorten_strings(value: Any, ratio: float) -> tuple[Any, bool]:
    """Cut every string leaf to ``floor(len * ratio)`` characters (S6, S02).

    A leaf that would keep no character at all is left alone, so a one-letter
    code disappears only when the ratio still leaves it one character.

    Args:
        value: The document whose ``structuredContent`` is rewritten.
        ratio: The fraction of each string to keep.

    Returns:
        The edited copy and whether any string changed.
    """
    changed = False

    def _walk(current: Any) -> Any:
        """Recurse through a value, shortening its string leaves."""
        nonlocal changed
        if isinstance(current, dict):
            return {key: _walk(item) for key, item in current.items()}
        if isinstance(current, list):
            return [_walk(item) for item in current]
        if isinstance(current, str):
            keep = math.floor(len(current) * ratio)
            if 0 < keep < len(current):
                changed = True
                return current[:keep]
        return current

    return _walk(value), changed


def _shift_time(value: str, zone: str) -> str:
    """Return the time-of-day part of an ISO date-time, unchanged.

    Args:
        value: The text after the ``T``, zone suffix included.
        zone: The zone suffix to strip.

    Returns:
        The time part without its zone.
    """
    return value[: -len(zone)] if zone else value


def _zone_of(text: str) -> str:
    """Return the zone suffix of an ISO date-time, or ``""``.

    Args:
        text: A string matching the S03 date pattern.

    Returns:
        ``"Z"``, ``"+HH:MM"``, ``"-HH:MM"`` or ``""``.
    """
    if text.endswith("Z"):
        return "Z"
    match = re.search(r"[+-]\d{2}:\d{2}$", text)
    return match.group(0) if match else ""


def _shift_date(text: str, days: int) -> str:
    """Move an ISO date ``days`` days into the past, keeping its format (S6, S03).

    Args:
        text: A string matching the S03 date pattern.
        days: The number of days to subtract.

    Returns:
        The shifted date in the same format.
    """
    day = dt.date.fromisoformat(text[:10]) - dt.timedelta(days=days)
    if "T" not in text:
        return day.isoformat()
    zone = _zone_of(text)
    return f"{day.isoformat()}T{_shift_time(text[11:], zone)}{zone}"


def _shift_dates(value: Any, days: int) -> tuple[Any, bool]:
    """Move every matching string leaf ``days`` days into the past (S6, S03).

    The pattern is anchored at both ends, as S6 writes it for structured data.

    Args:
        value: The document whose ``structuredContent`` is rewritten.
        days: The number of days to subtract.

    Returns:
        The edited copy and whether any date changed.
    """
    changed = False

    def _walk(current: Any) -> Any:
        """Recurse through a value, shifting its date leaves."""
        nonlocal changed
        if isinstance(current, dict):
            return {key: _walk(item) for key, item in current.items()}
        if isinstance(current, list):
            return [_walk(item) for item in current]
        if isinstance(current, str) and _DATE_PATTERN.fullmatch(current):
            changed = True
            return _shift_date(current, days)
        return current

    return _walk(value), changed


def _shift_text_dates(text: str, days: int) -> tuple[str, bool]:
    """Move every date found in plain text back ``days`` days (S6, S03).

    The S03 pattern is used without its anchors here, as S6 says, so it also
    matches a date embedded in prose.

    Args:
        text: The text block's text.
        days: The number of days to subtract.

    Returns:
        The rewritten text and whether a date matched.
    """
    matches = list(_DATE_PATTERN.finditer(text))
    if not matches:
        return text, False
    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(text[cursor : match.start()])
        parts.append(_shift_date(match.group(0), days))
        cursor = match.end()
    parts.append(text[cursor:])
    return "".join(parts), True


def _number_from_text(text: str) -> int | float:
    """Parse the number S04 found in plain text.

    Args:
        text: A match of ``_NUMBER_PATTERN``.

    Returns:
        An int when the number has no fractional part, a float otherwise.
    """
    return int(text) if "." not in text else float(text)


def _scaled(number: int | float, factor: int | float) -> int | float:
    """Multiply a number by ``factor``, keeping integers integral (S6, S04).

    Args:
        number: The value to scale.
        factor: The multiplier.

    Returns:
        The product; an int when both operands are ints.
    """
    if isinstance(number, int) and isinstance(factor, int):
        return number * factor
    return float(number) * float(factor)


def _scale_text(text: str, factor: int | float) -> tuple[str, bool]:
    """Scale the first number found in plain text (S6, S04).

    Args:
        text: The text block's text.
        factor: The multiplier.

    Returns:
        The rewritten text and whether a number matched.
    """
    match = _NUMBER_PATTERN.search(text)
    if match is None:
        return text, False
    number = _number_from_text(match.group(0))
    return text[: match.start()] + str(_scaled(number, factor)) + text[match.end() :], True


def _scale_structured(
    structured: Any, factor: int | float, numeric_path: str | None
) -> tuple[Any, bool]:
    """Scale the scenario's numeric path, or the first numeric leaf (S6, S04).

    Args:
        structured: The result's ``structuredContent``.
        factor: The multiplier.
        numeric_path: The scenario's ``fault_targets.numeric_path``, if any.

    Returns:
        The edited copy and whether a number changed.
    """
    document = _copy(structured)
    if numeric_path is not None:
        number = get_first(document, numeric_path)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            return structured, False
        path = numeric_path
    else:
        leaf = first_numeric_leaf(document)
        if leaf is None:
            return structured, False
        path, number = leaf
    set_first(document, path, _scaled(number, factor))
    return document, True


def _entity_fields(ctx: EpisodeContext) -> tuple[str, Any] | None:
    """Read the S05 ``entity_arg`` and ``decoys.entity`` of the scenario.

    Args:
        ctx: The episode context.

    Returns:
        ``(entity_arg, decoy)``, or ``None`` when either is missing.
    """
    scenario = ctx.scenario
    if not isinstance(scenario, dict):
        return None
    fault_targets = scenario.get("fault_targets")
    decoys = scenario.get("decoys")
    entity_arg = fault_targets.get("entity_arg") if isinstance(fault_targets, dict) else None
    decoy = decoys.get("entity") if isinstance(decoys, dict) else None
    if not isinstance(entity_arg, str) or entity_arg == "" or decoy is None:
        return None
    return entity_arg, decoy


def _numeric_path(ctx: EpisodeContext) -> str | None:
    """Read the scenario's ``fault_targets.numeric_path``, if it is a string.

    Args:
        ctx: The episode context.

    Returns:
        The JSONPath, or ``None``.
    """
    scenario = ctx.scenario
    if not isinstance(scenario, dict):
        return None
    fault_targets = scenario.get("fault_targets")
    path = fault_targets.get("numeric_path") if isinstance(fault_targets, dict) else None
    return path if isinstance(path, str) and path else None


def _factor(spec: FaultSpec) -> int | float | None:
    """Read the S04 ``factor``, falling back to the default.

    Args:
        spec: The scheduled fault.

    Returns:
        A positive finite number to multiply by, or ``None`` when the parameter
        is not a usable number.
    """
    value = _params(spec).get("factor", S04_FACTOR)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value):
        return None
    return value


@register
class EmptyOk(Fault):
    """S01: empty the result while keeping it a success (S6)."""

    id = "S01"
    cls = "silent"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Replace ``structuredContent`` with an empty value of its type, or the text.

        An object becomes ``{}`` and an array ``[]``; a scalar
        ``structuredContent`` has no empty counterpart, so the fault does not
        apply. A text block that is a JSON copy is updated in step; a text block
        that is not JSON becomes ``""``.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when there is nothing to
            empty.
        """
        del spec, ctx
        result = _result_of(payload)
        if result is None:
            return payload
        assert isinstance(payload, Response)
        if "structuredContent" in result:
            structured = result["structuredContent"]
            if isinstance(structured, dict):
                empty: Any = {}
            elif isinstance(structured, list):
                empty = []
            else:
                return payload
            result["structuredContent"] = empty
            if _text_is_synced(result, structured):
                _sync_text(result, empty)
            elif _text_of(result) is not None:
                _set_text(result, "")
            return _with_result(payload, result)
        block = _first_text_block(result)
        if block is None or block.get("text") == "":
            return payload
        block["text"] = ""
        return _with_result(payload, result)


@register
class Truncated(Fault):
    """S02: cut the longest array, or the strings, or the text (S6)."""

    id = "S02"
    cls = "silent"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Keep only the leading ``ceil(len * ratio)`` items or characters.

        With ``structuredContent``, the longest array loses its tail, or every
        string leaf is cut when there is no array. A plain-text block keeps the
        leading ``floor(len * ratio)`` characters.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when there is nothing to
            truncate.
        """
        del ctx
        result = _result_of(payload)
        if result is None:
            return payload
        assert isinstance(payload, Response)
        ratio = float(_params(spec).get("ratio", S02_RATIO))
        if "structuredContent" in result:
            structured = result["structuredContent"]
            if _walk_lists(structured):
                edited, changed = _truncate_longest_list(structured, ratio)
            else:
                edited, changed = _shorten_strings(structured, ratio)
            if not changed:
                return payload
            result["structuredContent"] = edited
            if _text_is_synced(result, structured):
                _sync_text(result, edited)
            else:
                _set_text(result, _truncate_text(_text_of(result), ratio))
            return _with_result(payload, result)
        text = _text_of(result)
        if text is None:
            return payload
        shortened = _truncate_text(text, ratio)
        if shortened == text:
            return payload
        _set_text(result, shortened)
        return _with_result(payload, result)


@register
class Stale(Fault):
    """S03: move every date ``days`` days into the past (S6)."""

    id = "S03"
    cls = "silent"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Shift every date leaf, or every date in the text, back by ``days``.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when no date is found.
        """
        del ctx
        result = _result_of(payload)
        if result is None:
            return payload
        assert isinstance(payload, Response)
        days = int(_params(spec).get("days", S03_DAYS))
        if "structuredContent" in result:
            structured = result["structuredContent"]
            edited, changed = _shift_dates(structured, days)
            if not changed:
                return payload
            result["structuredContent"] = edited
            if _text_is_synced(result, structured):
                _sync_text(result, edited)
            else:
                _set_text(result, _shift_text_dates(_text_of(result) or "", days)[0])
            return _with_result(payload, result)
        block = _first_text_block(result)
        text = block.get("text") if block is not None else None
        if not isinstance(text, str):
            return payload
        edited_text, changed = _shift_text_dates(text, days)
        if not changed:
            return payload
        assert block is not None
        block["text"] = edited_text
        return _with_result(payload, result)


@register
class NumericCorruption(Fault):
    """S04: multiply the first numeric leaf, or the first number in text (S6)."""

    id = "S04"
    cls = "silent"
    hooks = ("post_call",)

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Scale one number by ``factor``.

        With ``structuredContent``, the scenario's ``numeric_path`` wins when it
        names a number, otherwise the first numeric leaf is used. A plain-text
        block scales its first match of ``-?\\d+(\\.\\d+)?``.

        Args:
            payload: The upstream response.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten response, or ``payload`` when no number is found.
        """
        result = _result_of(payload)
        if result is None:
            return payload
        assert isinstance(payload, Response)
        factor = _factor(spec)
        if factor is None:
            return payload
        if "structuredContent" in result:
            structured = result["structuredContent"]
            edited, changed = _scale_structured(structured, factor, _numeric_path(ctx))
            if not changed:
                return payload
            result["structuredContent"] = edited
            if _text_is_synced(result, structured):
                _sync_text(result, edited)
            else:
                _set_text(result, _scale_text(_text_of(result) or "", factor)[0])
            return _with_result(payload, result)
        block = _first_text_block(result)
        text = block.get("text") if block is not None else None
        if not isinstance(text, str):
            return payload
        edited_text, changed = _scale_text(text, factor)
        if not changed:
            return payload
        assert block is not None
        block["text"] = edited_text
        return _with_result(payload, result)


@register
class WrongEntity(Fault):
    """S05: swap the entity argument for a decoy before forwarding (S6)."""

    id = "S05"
    cls = "silent"
    hooks = ("pre_call",)

    def applicable(self, ctx: EpisodeContext) -> bool:
        """Report whether the scenario names an ``entity_arg`` and a decoy.

        Args:
            ctx: The episode context.

        Returns:
            ``True`` when both fields are present.
        """
        return _entity_fields(ctx) is not None

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Replace the entity argument's value with ``decoys.entity``.

        The response is left untouched; the server simply answers for the decoy.

        Args:
            payload: The ``tools/call`` request.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The rewritten request, or ``payload`` when the argument is absent.
        """
        del spec
        fields = _entity_fields(ctx)
        if fields is None or not isinstance(payload, Request):
            return payload
        entity_arg, decoy = fields
        params = payload.params if isinstance(payload.params, dict) else {}
        arguments = params.get("arguments")
        if not isinstance(arguments, dict) or entity_arg not in arguments:
            return payload
        swapped = {key: value for key, value in arguments.items() if key != entity_arg}
        swapped[entity_arg] = decoy
        return payload.model_copy(update={"params": {**params, "arguments": swapped}})
