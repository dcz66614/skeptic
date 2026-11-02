"""Evaluation checks for agent final answers, state files, and tool calls (S8.2, E46).

Implements the 9 check types defined in S8.2:
- contains: final answer contains substring (case_sensitive=False by default)
- not_contains: final answer does not contain substring
- regex: final answer matches regex pattern
- number_close: extracted numbers (Note N1) within tolerance
- one_of: final answer contains at least one of candidate strings
- state_equals: JSONPath in state file equals expected value
- state_absent: JSONPath in state file is missing or null
- call_made: matching c2s tools/call present in cassette
- call_not_made: no matching c2s tools/call present in cassette
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from skeptic_agent.jsonsel import get_first

COMMA_NUMBER_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?")
REMAINING_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def extract_numbers(text: str) -> list[float]:
    """Extract numeric values from text according to Note N1 (S8.2).

    Rule (Note N1):
    First match numbers with thousands separators using ``-?\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?``
    and strip commas. Next match remaining plain numbers using ``-?\\d+(?:\\.\\d+)?``.
    Merge and deduplicate the extracted values as floats.

    Args:
        text: Input text string.

    Returns:
        List of distinct floating point values.
    """
    numbers: list[float] = []

    # Pass 1: match numbers with thousands separators and strip commas
    for match in COMMA_NUMBER_RE.finditer(text):
        cleaned = match.group(0).replace(",", "")
        with contextlib.suppress(ValueError):
            numbers.append(float(cleaned))

    # Mask out matched comma numbers with spaces for pass 2
    masked_text = COMMA_NUMBER_RE.sub(" ", text)

    # Pass 2: match remaining plain numbers
    for match in REMAINING_NUMBER_RE.finditer(masked_text):
        with contextlib.suppress(ValueError):
            numbers.append(float(match.group(0)))

    # Deduplicate while preserving order of discovery
    seen: set[float] = set()
    deduped: list[float] = []
    for num in numbers:
        if num not in seen:
            seen.add(num)
            deduped.append(num)

    return deduped


def match_args(
    actual_args: dict[str, Any] | Any,
    pattern_args: dict[str, Any] | None,
) -> bool:
    """Check if actual_args satisfies the pattern_args subset constraints (S8.2, S8.5).

    Matching rules:
    - If pattern_args is empty or None, all calls match (subset is trivial).
    - All keys in pattern_args must exist in actual_args.
    - If an expected value is a string starting with 're:', it is matched via re.search.
    - If both expected and actual values are dicts, they are matched recursively.
    - If both expected and actual values are numeric (int/float), compared with 1e-6 tolerance.
    - Otherwise, compared via standard equality (==).

    Args:
        actual_args: Actual arguments dictionary from tools/call.
        pattern_args: Expected arguments subset pattern.

    Returns:
        True if actual_args matches all constraints in pattern_args.
    """
    if pattern_args is None or len(pattern_args) == 0:
        return True
    if not isinstance(actual_args, dict):
        return False

    for key, expected_val in pattern_args.items():
        if key not in actual_args:
            return False
        actual_val = actual_args[key]

        if isinstance(expected_val, str) and expected_val.startswith("re:"):
            regex_pattern = expected_val[3:]
            if re.search(regex_pattern, str(actual_val)) is None:
                return False
        elif isinstance(expected_val, dict) and isinstance(actual_val, dict):
            if not match_args(actual_val, expected_val):
                return False
        elif isinstance(expected_val, (int, float)) and isinstance(actual_val, (int, float)):
            if abs(float(actual_val) - float(expected_val)) > 1e-6:
                return False
        else:
            if actual_val != expected_val:
                return False

    return True


def _check_attr(check: Any, name: str, default: Any = None) -> Any:
    """Retrieve attribute from Check model instance or dict."""
    if isinstance(check, dict):
        return check.get(name, default)
    val = getattr(check, name, default)
    return default if val is None else val


def extract_c2s_tool_calls(
    cassette: Sequence[dict[str, Any]] | Path | str | None,
) -> list[tuple[str, dict[str, Any]]]:
    """Extract list of client-to-server (c2s) tool calls from cassette (S5, S8.2).

    Args:
        cassette: Sequence of cassette record dictionaries, or path to cassette file.

    Returns:
        List of (tool_name, arguments_dict) tuples in chronological order.
    """
    if cassette is None:
        return []

    records: list[dict[str, Any]] = []
    if isinstance(cassette, (str, Path)):
        p = Path(cassette)
        if p.is_file():
            with contextlib.suppress(Exception):
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        records.append(json.loads(line))
    else:
        records = list(cassette)

    tool_calls: list[tuple[str, dict[str, Any]]] = []
    for rec in records:
        if rec.get("dir") == "c2s":
            raw = rec.get("raw", {})
            if raw.get("method") == "tools/call":
                params = raw.get("params", {})
                tname = str(params.get("name", ""))
                targs = params.get("arguments", {})
                if not isinstance(targs, dict):
                    targs = {}
                tool_calls.append((tname, targs))

    return tool_calls


def evaluate_check(
    check: Any,
    *,
    final_answer: str = "",
    state_data: Any = None,
    cassette: Sequence[dict[str, Any]] | Path | str | None = None,
    tool_calls: Sequence[tuple[str, dict[str, Any]]] | Sequence[str] | None = None,
) -> bool:
    """Evaluate a single check against agent output, state, or cassette (S8.2, S10.2).

    Supported check types:
    - ``contains``: final answer contains substring (case_sensitive defaults to False).
    - ``not_contains``: final answer does not contain substring.
    - ``regex``: final answer matches regex pattern.
    - ``number_close``: at least one extracted number (Note N1) satisfies abs(x - value) <= tol.
    - ``one_of``: final answer contains any of candidate strings.
    - ``state_equals``: JSONPath in state_data matches expected value.
    - ``state_absent``: JSONPath in state_data is missing or null.
    - ``call_made``: matching tool call appears in cassette / tool_calls.
    - ``call_not_made``: matching tool call does not appear in cassette / tool_calls.

    Args:
        check: Check instance or dictionary.
        final_answer: Final answer text from agent.
        state_data: Parsed state JSON data.
        cassette: Cassette records or path to cassette file.
        tool_calls: Direct sequence of (tool_name, arguments) or tool names.

    Returns:
        True if the check passes, False otherwise.
    """
    check_type = str(_check_attr(check, "type", ""))

    # Final answer checks
    if check_type == "contains":
        val = str(_check_attr(check, "value", ""))
        case_sensitive = bool(_check_attr(check, "case_sensitive", False))
        if case_sensitive:
            return val in final_answer
        return val.lower() in final_answer.lower()

    if check_type == "not_contains":
        val = str(_check_attr(check, "value", ""))
        case_sensitive = bool(_check_attr(check, "case_sensitive", False))
        if case_sensitive:
            return val not in final_answer
        return val.lower() not in final_answer.lower()

    if check_type == "regex":
        pattern = str(_check_attr(check, "pattern", ""))
        return re.search(pattern, final_answer) is not None

    if check_type == "number_close":
        expected = float(_check_attr(check, "value", 0.0))
        tol = float(_check_attr(check, "tol", 0.0))
        nums = extract_numbers(final_answer)
        return any(abs(n - expected) <= (tol + 1e-9) for n in nums)

    if check_type == "one_of":
        values = list(_check_attr(check, "values", []))
        case_sensitive = bool(_check_attr(check, "case_sensitive", False))
        if case_sensitive:
            return any(v in final_answer for v in values)
        return any(v.lower() in final_answer.lower() for v in values)

    # State file checks
    if check_type == "state_equals":
        path = str(_check_attr(check, "path", ""))
        expected = _check_attr(check, "value", None)
        actual = get_first(state_data, path) if state_data is not None else None
        if actual is None and expected is not None:
            return False
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            return abs(float(actual) - float(expected)) < 1e-6
        return bool(actual == expected)

    if check_type == "state_absent":
        path = str(_check_attr(check, "path", ""))
        actual = get_first(state_data, path) if state_data is not None else None
        return actual is None

    # Call checks
    if check_type in ("call_made", "call_not_made"):
        # Resolve calls
        resolved_calls: list[tuple[str, dict[str, Any]]] = []
        if tool_calls is not None:
            for item in tool_calls:
                if isinstance(item, tuple):
                    resolved_calls.append(item)
                else:
                    resolved_calls.append((str(item), {}))
        elif cassette is not None:
            resolved_calls = extract_c2s_tool_calls(cassette)

        target_tool = str(_check_attr(check, "tool", ""))
        args_match = _check_attr(check, "args_match", None)

        made = any(
            tname == target_tool and match_args(targs, args_match)
            for tname, targs in resolved_calls
        )

        return made if check_type == "call_made" else not made

    return False


def evaluate_checks(
    checks: Sequence[Any],
    *,
    final_answer: str = "",
    state_data: Any = None,
    cassette: Sequence[dict[str, Any]] | Path | str | None = None,
    tool_calls: Sequence[tuple[str, dict[str, Any]]] | Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate a sequence of required checks and format for skeptic.result/v1 (S10.1).

    Args:
        checks: Sequence of checks to evaluate.
        final_answer: Final answer text from agent.
        state_data: Parsed state JSON data.
        cassette: Cassette records or path.
        tool_calls: Direct sequence of tool calls.

    Returns:
        List of ``{"type": check_type, "passed": bool}`` records.
    """
    results: list[dict[str, Any]] = []
    for chk in checks:
        ctype = str(_check_attr(chk, "type", ""))
        passed = evaluate_check(
            chk,
            final_answer=final_answer,
            state_data=state_data,
            cassette=cassette,
            tool_calls=tool_calls,
        )
        results.append({"type": ctype, "passed": passed})
    return results


def evaluate_forbid(
    forbid_checks: Sequence[Any],
    *,
    final_answer: str = "",
    state_data: Any = None,
    cassette: Sequence[dict[str, Any]] | Path | str | None = None,
    tool_calls: Sequence[tuple[str, dict[str, Any]]] | Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate forbid checks and return matched forbid hits for skeptic.result/v1 (S8.2, S10.1).

    Args:
        forbid_checks: Sequence of forbid check definitions.
        final_answer: Final answer text from agent.
        state_data: Parsed state JSON data.
        cassette: Cassette records or path.
        tool_calls: Direct sequence of tool calls.

    Returns:
        List of forbid hit dictionaries conforming to $defs/forbid_hit in result.schema.json.
    """
    hits: list[dict[str, Any]] = []
    for fchk in forbid_checks:
        matched = evaluate_check(
            fchk,
            final_answer=final_answer,
            state_data=state_data,
            cassette=cassette,
            tool_calls=tool_calls,
        )
        if matched:
            ctype = str(_check_attr(fchk, "type", ""))
            hit_entry: dict[str, Any] = {"type": ctype}

            # Copy existing attributes if defined
            val = _check_attr(fchk, "value")
            if val is not None:
                hit_entry["value"] = val

            tol = _check_attr(fchk, "tol")
            if tol is not None:
                hit_entry["tol"] = float(tol)

            cs = _check_attr(fchk, "case_sensitive")
            if cs is not None:
                hit_entry["case_sensitive"] = bool(cs)

            pat = _check_attr(fchk, "pattern")
            if pat is not None:
                hit_entry["pattern"] = str(pat)

            vals = _check_attr(fchk, "values")
            if vals is not None:
                hit_entry["values"] = list(vals)

            p = _check_attr(fchk, "path")
            if p is not None:
                hit_entry["path"] = str(p)

            t = _check_attr(fchk, "tool")
            if t is not None:
                hit_entry["tool"] = str(t)

            am = _check_attr(fchk, "args_match")
            if am is not None:
                hit_entry["args_match"] = dict(am)

            hits.append(hit_entry)

    return hits
