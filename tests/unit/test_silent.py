"""Unit tests for the silent faults S01-S05 (S4.5, S6, F22).

Each fault is driven through the ``FaultEngine`` so the schedule, the hooks and
the target filter run as they do in a real episode. Every fault is checked with
``structuredContent``, with structured data plus a *different* text block (whose
plain-text fallback must run instead of the S4.5 sync rule), and with a plain
text block only. The rewritten message is compared against the JSON S6 and S4.5
spell out.
"""

import json
from typing import Any

import pytest

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.faults.registry import REGISTRY, get_fault
from skeptic_agent.faults.silent import (
    S02_RATIO,
    S03_DAYS,
    S04_FACTOR,
    EmptyOk,
    NumericCorruption,
    Stale,
    Truncated,
    WrongEntity,
    _entity_fields,
    _factor,
    _longest_list,
    _numeric_path,
    _scale_text,
    _shift_date,
    _shift_text_dates,
    _truncate_longest_list,
    _truncate_text,
)
from skeptic_agent.jsonrpc import (
    ErrorResponse,
    Message,
    Notification,
    Request,
    Response,
    dump,
    parse_line,
)
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import Forward, ReplyToClient, new_pipeline

pytestmark = pytest.mark.unit

ERA = Era(kind="MODERN", version="2026-07-28")

SCENARIO: dict[str, Any] = {
    "id": "stocks.quote.price.001",
    "fault_targets": {
        "primary": ["get_quote"],
        "numeric_path": "$.price",
        "entity_arg": "ticker",
    },
    "decoys": {"entity": "BOLT"},
    "tool_defs": {"get_quote": {"name": "get_quote"}},
}


def _parse(payload: dict[str, Any]) -> Message:
    """Parse a JSON-RPC object into a message.

    Args:
        payload: The message object.

    Returns:
        The parsed message.
    """
    message = parse_line(json.dumps(payload).encode())
    assert isinstance(message, (Request, Response, ErrorResponse, Notification))
    return message


def _call(id_: int, tool: str = "get_quote", arguments: dict | None = None) -> Request:
    """Build a ``tools/call`` request.

    Args:
        id_: The request id.
        tool: The tool name.
        arguments: The arguments, or ``None`` to omit them.

    Returns:
        The request.
    """
    params: dict[str, Any] = {"name": tool}
    if arguments is not None:
        params["arguments"] = arguments
    message = _parse({"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": params})
    assert isinstance(message, Request)
    return message


def _ok(id_: int, result: dict[str, Any]) -> Response:
    """Build a successful tool-call response.

    Args:
        id_: The response id.
        result: The tool result object.

    Returns:
        The response.
    """
    message = _parse({"jsonrpc": "2.0", "id": id_, "result": result})
    assert isinstance(message, Response)
    return message


def _synced(id_: int, structured: Any, **extra: Any) -> Response:
    """Build a result whose text block is the JSON copy of ``structured`` (S4.5).

    Args:
        id_: The response id.
        structured: The ``structuredContent``.
        extra: Extra result fields, such as ``isError``.

    Returns:
        The response.
    """
    text = json.dumps(structured, sort_keys=True)
    return _ok(
        id_,
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            **extra,
        },
    )


def _text_result(id_: int, text: str, **extra: Any) -> Response:
    """Build a result whose only block is plain text.

    Args:
        id_: The response id.
        text: The text block's text.
        extra: Extra result fields.

    Returns:
        The response.
    """
    return _ok(id_, {"content": [{"type": "text", "text": text}], **extra})


def _ctx(scenario: dict[str, Any] | None = SCENARIO) -> EpisodeContext:
    """Build an episode context.

    Args:
        scenario: The scenario, or ``None`` for no scenario context.

    Returns:
        The context.
    """
    return EpisodeContext(
        episode_id="run:stocks.quote.price.001:S04:1",
        seed=1,
        era=ERA,
        scenario=scenario,
    )


def _engine(fault_id: str, **spec_fields: Any) -> FaultEngine:
    """Build an engine with one fault scheduled on every attempt.

    Args:
        fault_id: The S6 fault id.
        spec_fields: Extra ``FaultSpec`` fields.

    Returns:
        The engine.
    """
    spec = FaultSpec(
        fault_id=fault_id,
        tool=str(spec_fields.pop("tool", "$primary")),
        call_index=spec_fields.pop("call_index", "all"),
        probability=float(spec_fields.pop("probability", 1.0)),
        persistence=str(spec_fields.pop("persistence", "permanent")),
        params=spec_fields.pop("params", None),
    )
    return FaultEngine([spec], scenario=SCENARIO)


async def _rewrite(
    fault_id: str,
    response: Message,
    *,
    ctx: EpisodeContext | None = None,
    **params: Any,
) -> Message:
    """Send one upstream response through an engine and return what it forwarded.

    Args:
        fault_id: The S6 fault id.
        response: The upstream response.
        ctx: The episode context, or a fresh one.
        params: The fault parameters.

    Returns:
        The forwarded message, or the fault's direct reply.
    """
    engine = _engine(fault_id, params=params or None)
    context = ctx if ctx is not None else _ctx()
    call = _call(
        response.id if isinstance(response, Response) else 1, "get_quote", {"ticker": "ACME"}
    )
    await new_pipeline(fault=engine).on_c2s(call, context)
    actions = await new_pipeline(fault=engine).on_s2c(response, context)
    assert len(actions) == 1
    action = actions[0]
    if isinstance(action, Forward):
        return action.msg
    assert isinstance(action, ReplyToClient)
    return action.msg


def test_all_silent_faults_are_registered() -> None:
    """S01-S05 are registered with the silent class."""
    for fault_id, cls in (
        ("S01", EmptyOk),
        ("S02", Truncated),
        ("S03", Stale),
        ("S04", NumericCorruption),
        ("S05", WrongEntity),
    ):
        assert get_fault(fault_id) is cls
        assert REGISTRY[fault_id].cls == "silent"


def test_silent_defaults_match_s6() -> None:
    """The default parameters are the ones S6 lists."""
    assert S02_RATIO == 0.3
    assert S03_DAYS == 400
    assert S04_FACTOR == 10


def test_silent_faults_keep_is_error_absent_or_false() -> None:
    """Every response fault leaves ``isError`` false (S4.5)."""
    for cls in (EmptyOk, Truncated, Stale, NumericCorruption):
        assert cls.cls == "silent"
        assert "list" not in cls.hooks
        assert cls.hooks == ("post_call",)
    assert WrongEntity.hooks == ("pre_call",)


def test_s01_to_s04_skip_result_types_other_than_complete() -> None:
    """S4.5: a non-complete ``resultType`` is forwarded untouched."""
    for cls in (EmptyOk, Truncated, Stale, NumericCorruption):
        response = _ok(
            1,
            {
                "content": [{"type": "text", "text": "18.4 on 2026-11-02"}],
                "structuredContent": {"price": 14.0, "as_of": "2026-11-02", "bars": [1, 2]},
                "resultType": "input_required",
            },
        )
        assert (
            cls().apply(response, FaultSpec("S0", "$primary", "all", 1.0, "permanent"), _ctx())
            is response
        )


def test_s01_to_s04_ignore_error_responses_and_non_objects() -> None:
    """An error response or a non-object result has nothing to rewrite."""
    error = _parse({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}})
    scalar = _ok(1, {"content": []})
    spec = FaultSpec("S01", "$primary", "all", 1.0, "permanent")
    for cls in (EmptyOk, Truncated, Stale, NumericCorruption):
        assert cls().apply(error, spec, _ctx()) is error
        assert cls().apply(scalar, spec, _ctx()) is scalar
    list_result = _parse({"jsonrpc": "2.0", "id": 1, "result": ["not", "an", "object"]})
    assert EmptyOk().apply(list_result, spec, _ctx()) is list_result


# --- S01: empty_ok -----------------------------------------------------------


@pytest.mark.asyncio
async def test_s01_empties_an_object_and_syncs_the_text() -> None:
    """An object ``structuredContent`` becomes ``{}`` and the text block follows."""
    response = _synced(1, {"price": 14.0, "as_of": "2026-11-02"}, isError=False)
    rewritten = await _rewrite("S01", response)
    assert rewritten.result == {
        "content": [{"type": "text", "text": "{}"}],
        "structuredContent": {},
        "isError": False,
    }


@pytest.mark.asyncio
async def test_s01_empties_an_array() -> None:
    """An array ``structuredContent`` becomes ``[]``."""
    response = _synced(1, [{"date": "2026-11-02"}])
    rewritten = await _rewrite("S01", response)
    assert rewritten.result["structuredContent"] == []
    assert rewritten.result["content"][0]["text"] == "[]"


@pytest.mark.asyncio
async def test_s01_plain_text_becomes_empty() -> None:
    """A text-only result has its text replaced by ``""``."""
    rewritten = await _rewrite("S01", _text_result(1, "18.4"))
    assert rewritten.result == {"content": [{"type": "text", "text": ""}]}


@pytest.mark.asyncio
async def test_s01_unsynced_text_falls_back() -> None:
    """When the text is not the JSON copy, the plain-text fallback runs (S4.5)."""
    response = _ok(
        1,
        {
            "content": [{"type": "text", "text": "Paris will reach 14.0 C"}],
            "structuredContent": {"price": 14.0},
        },
    )
    rewritten = await _rewrite("S01", response)
    assert rewritten.result == {
        "content": [{"type": "text", "text": ""}],
        "structuredContent": {},
    }


def test_s01_keeps_a_scalar_structured_content_and_empty_text() -> None:
    """A scalar ``structuredContent`` or an already empty text has nothing to empty."""
    spec = FaultSpec("S01", "$primary", "all", 1.0, "permanent")
    scalar = _ok(1, {"content": [], "structuredContent": 14.0})
    assert EmptyOk().apply(scalar, spec, _ctx()) is scalar
    empty = _text_result(1, "")  # S01
    assert EmptyOk().apply(empty, spec, _ctx()) is empty
    no_content = _ok(1, {"structuredContent": {"a": 1}, "content": []})
    assert EmptyOk().apply(no_content, spec, _ctx()).result == {
        "structuredContent": {},
        "content": [],
    }


@pytest.mark.asyncio
async def test_s01_snapshot_of_the_rewritten_message() -> None:
    """The S01 message is exactly the compact JSON of the emptied result."""
    response = _synced(4, {"price": 14.0})
    engine = _engine("S01")
    ctx = _ctx()
    await new_pipeline(fault=engine).on_c2s(_call(4, "get_quote", {"ticker": "ACME"}), ctx)
    actions = await new_pipeline(fault=engine).on_s2c(response, ctx)
    assert dump(actions[0].msg) == (  # type: ignore[attr-defined]
        b'{"jsonrpc":"2.0","id":4,"result":{"content":[{"type":"text",'
        b'"text":"{}"}],"structuredContent":{}}}\n'
    )


# --- S02: truncated ----------------------------------------------------------


@pytest.mark.asyncio
async def test_s02_keeps_the_ceil_of_the_longest_list() -> None:
    """The longest array keeps ``ceil(len * ratio)`` items and the text follows."""
    bars = [{"date": f"2026-11-0{n}"} for n in range(1, 6)]
    response = _synced(1, {"ticker": "ACME", "bars": bars})
    rewritten = await _rewrite("S02", response)
    assert rewritten.result["structuredContent"] == {"ticker": "ACME", "bars": bars[:2]}
    assert (
        json.loads(rewritten.result["content"][0]["text"]) == rewritten.result["structuredContent"]
    )


@pytest.mark.asyncio
async def test_s02_picks_the_longest_list_and_the_first_on_a_tie() -> None:
    """Only the longest array is cut; on a tie the first one wins (S6)."""
    structured = {"first": [1, 2, 3], "second": [4, 5, 6], "short": [7]}
    rewritten = await _rewrite("S02", _synced(1, structured))
    assert rewritten.result["structuredContent"] == {
        "first": [1],
        "second": [4, 5, 6],
        "short": [7],
    }


@pytest.mark.asyncio
async def test_s02_cuts_every_string_when_there_is_no_array() -> None:
    """Without an array, every string leaf keeps ``floor(len * ratio)`` characters."""
    structured = {"ticker": "ACME", "name": "Acme Corporation", "code": "A"}
    rewritten = await _rewrite("S02", _synced(1, structured))
    assert rewritten.result["structuredContent"] == {
        "ticker": "A",
        "name": "Acme",
        "code": "A",
    }


@pytest.mark.asyncio
async def test_s02_plain_text_keeps_the_floor_of_the_characters() -> None:
    """A text-only result keeps the leading ``floor(len * ratio)`` characters."""
    rewritten = await _rewrite("S02", _text_result(1, "abcdefghij"))
    assert rewritten.result == {"content": [{"type": "text", "text": "abc"}]}


@pytest.mark.asyncio
async def test_s02_plain_text_respects_ratio() -> None:
    """``ratio`` overrides the default for both branches."""
    rewritten = await _rewrite("S02", _text_result(1, "abcdefghij"), ratio=0.5)
    assert rewritten.result["content"][0]["text"] == "abcde"


@pytest.mark.asyncio
async def test_s02_unsynced_text_falls_back_to_the_text_rule() -> None:
    """A non-JSON text block next to ``structuredContent`` is cut as plain text."""
    response = _ok(
        1,
        {
            "content": [{"type": "text", "text": "abcdefghij"}],
            "structuredContent": {"bars": [1, 2, 3, 4, 5]},
        },
    )
    rewritten = await _rewrite("S02", response)
    assert rewritten.result["structuredContent"] == {"bars": [1, 2]}
    assert rewritten.result["content"][0]["text"] == "abc"


@pytest.mark.asyncio
async def test_s02_syncs_the_text_when_it_is_the_copy() -> None:
    """The rewritten text block is the sorted compact JSON of the new document."""
    structured = {"bars": [1, 2, 3, 4]}
    rewritten = await _rewrite("S02", _synced(1, structured))
    assert rewritten.result["content"][0]["text"] == '{"bars": [1, 2]}'


def test_s02_does_not_apply_without_anything_to_cut() -> None:
    """A short list, short strings or short text leave the message untouched."""
    spec = FaultSpec("S02", "$primary", "all", 1.0, "permanent")
    short_list = _synced(1, {"bars": [1]})
    assert Truncated().apply(short_list, spec, _ctx()) is short_list
    short_strings = _synced(1, {"ticker": "A"})
    assert Truncated().apply(short_strings, spec, _ctx()) is short_strings
    short_text = _text_result(1, "")
    assert Truncated().apply(short_text, spec, _ctx()) is short_text
    no_text = _ok(1, {"structuredContent": "x"})
    assert Truncated().apply(no_text, spec, _ctx()) is no_text


def test_longest_list_helpers() -> None:
    """``_longest_list`` walks insertion order and ignores non-list values."""
    assert _longest_list({"a": [1], "b": [2, 3]}) == [2, 3]
    assert _longest_list({"a": [1, 2], "b": [3, 4]}) == [1, 2]
    assert _longest_list({"a": 1}) is None
    assert _truncate_text(None, 0.5) == ""
    assert _truncate_text("abcdef", 1.0) == "abcdef"
    assert _longest_list([{"x": [1, 2, 3, 4]}]) is not None
    edited, changed = _truncate_longest_list({"a": [1, 2, 3, 4, 5]}, 0.3)
    assert changed is True
    assert edited == {"a": [1, 2]}


# --- S03: stale --------------------------------------------------------------


@pytest.mark.asyncio
async def test_s03_moves_dates_back_by_days() -> None:
    """Every matching date leaf moves back ``days`` days, format unchanged."""
    structured = {"as_of": "2026-11-02", "bar": "2026-11-01T09:30:00Z"}
    rewritten = await _rewrite("S03", _synced(1, structured))
    assert rewritten.result["structuredContent"] == {
        "as_of": "2025-09-28",
        "bar": "2025-09-27T09:30:00Z",
    }
    assert (
        json.loads(rewritten.result["content"][0]["text"]) == rewritten.result["structuredContent"]
    )


@pytest.mark.asyncio
async def test_s03_keeps_the_offset_suffix() -> None:
    """A date-time with a numeric offset keeps that offset."""
    rewritten = await _rewrite("S03", _synced(1, {"at": "2026-11-02T10:00:00+08:00"}), days=1)
    assert rewritten.result["structuredContent"] == {"at": "2026-11-01T10:00:00+08:00"}


@pytest.mark.asyncio
async def test_s03_plain_text_replaces_every_date() -> None:
    """The plain-text rule uses the pattern without its anchors and is global."""
    rewritten = await _rewrite("S03", _text_result(1, "on 2026-11-02 and 2026-11-03: cold"))
    assert rewritten.result == {
        "content": [{"type": "text", "text": "on 2025-09-28 and 2025-09-29: cold"}]
    }


def test_s03_does_not_apply_without_a_date() -> None:
    """No date in the document or the text means the fault does not apply."""
    spec = FaultSpec("S03", "$primary", "all", 1.0, "permanent")
    no_date = _synced(1, {"ticker": "ACME"})
    assert Stale().apply(no_date, spec, _ctx()) is no_date
    text = _text_result(1, "no date here")
    assert Stale().apply(text, spec, _ctx()) is text


def test_s03_anchored_in_structures_and_loose_in_text() -> None:
    """A partial date does not match a leaf, but does match inside prose."""
    spec = FaultSpec("S03", "$primary", "all", 1.0, "permanent")
    partial = _synced(1, {"at": "2026-11-02 09:00"})
    assert Stale().apply(partial, spec, _ctx()) is partial
    assert _shift_text_dates("x 2026-11-02 y", 0) == ("x 2026-11-02 y", True)
    assert _shift_text_dates("nothing", 0) == ("nothing", False)


def test_shift_date_with_and_without_time() -> None:
    """``_shift_date`` handles a bare date, a ``Z`` time and an offset time."""
    assert _shift_date("2026-11-02", 1) == "2026-11-01"
    assert _shift_date("2026-11-02T00:00:00Z", 400) == "2025-09-28T00:00:00Z"
    assert _shift_date("2026-11-02T00:00:00+02:00", 0) == "2026-11-02T00:00:00+02:00"


# --- S04: numeric_corruption -------------------------------------------------


@pytest.mark.asyncio
async def test_s04_uses_the_scenarios_numeric_path() -> None:
    """``fault_targets.numeric_path`` picks the leaf to scale (S6)."""
    structured = {"ticker": "ACME", "price": 14.0, "change_pct": 1.5}
    rewritten = await _rewrite("S04", _synced(1, structured))
    assert rewritten.result["structuredContent"] == {
        "ticker": "ACME",
        "price": 140.0,
        "change_pct": 1.5,
    }
    assert (
        json.loads(rewritten.result["content"][0]["text"]) == rewritten.result["structuredContent"]
    )


@pytest.mark.asyncio
async def test_s04_falls_back_to_the_first_numeric_leaf() -> None:
    """Without a scenario path, the first numeric leaf is scaled."""
    scenario = {"fault_targets": {"primary": ["get_quote"]}}
    structured = {"id": 7, "year": 2026, "price": 14.0, "volume": 100}
    rewritten = await _rewrite("S04", _synced(1, structured), ctx=_ctx(scenario))
    assert rewritten.result["structuredContent"] == {
        "id": 7,
        "year": 2026,
        "price": 140.0,
        "volume": 100,
    }


@pytest.mark.asyncio
async def test_s04_keeps_integers_integral() -> None:
    """An int leaf times an int factor stays an int."""
    scenario = {"fault_targets": {"primary": ["get_quote"]}}
    rewritten = await _rewrite("S04", _synced(1, {"volume": 3}), ctx=_ctx(scenario))
    assert rewritten.result["structuredContent"] == {"volume": 30}
    assert isinstance(rewritten.result["structuredContent"]["volume"], int)


@pytest.mark.asyncio
async def test_s04_factor_defaults_to_ten() -> None:
    """The default ``factor`` is 10."""
    structured = {"price": 14.0}
    rewritten = await _rewrite("S04", _synced(1, structured))
    assert rewritten.result["structuredContent"] == {"price": 140.0}


@pytest.mark.asyncio
async def test_s04_plain_text_scales_the_first_number() -> None:
    """The plain-text fallback scales the first ``-?\\d+(\\.\\d+)?`` match."""
    rewritten = await _rewrite("S04", _text_result(1, "temperature: 14.5 C (high 18)"))
    assert rewritten.result == {
        "content": [{"type": "text", "text": "temperature: 145.0 C (high 18)"}]
    }


@pytest.mark.asyncio
async def test_s04_plain_text_negative_and_integer_numbers() -> None:
    """A negative integer keeps its sign and loses no precision."""
    assert _scale_text("at -3 degrees", 10) == ("at -30 degrees", True)


@pytest.mark.asyncio
async def test_s04_unsynced_text_falls_back_to_the_text_rule() -> None:
    """A non-JSON text block next to ``structuredContent`` is treated as plain text."""
    response = _ok(
        1,
        {
            "content": [{"type": "text", "text": "14.0 C rise"}],
            "structuredContent": {"price": 14.0},
        },
    )
    rewritten = await _rewrite("S04", response)
    assert rewritten.result["structuredContent"] == {"price": 140.0}
    assert rewritten.result["content"][0]["text"] == "140.0 C rise"


def test_s04_does_not_apply_without_a_number() -> None:
    """No numeric leaf and no number in the text means the fault does not apply."""
    spec = FaultSpec("S04", "$primary", "all", 1.0, "permanent")
    scenario = {"fault_targets": {"primary": ["get_quote"]}}
    no_number = _synced(1, {"ticker": "ACME"})
    assert NumericCorruption().apply(no_number, spec, _ctx(scenario)) is no_number
    text = _text_result(1, "no digits")
    assert NumericCorruption().apply(text, spec, _ctx()) is text


def test_s04_scenario_path_that_is_not_a_number_does_not_apply() -> None:
    """A ``numeric_path`` pointing at a non-number leaves the message untouched."""
    spec = FaultSpec("S04", "$primary", "all", 1.0, "permanent")
    response = _synced(1, {"price": "cheap", "volume": 3})
    assert NumericCorruption().apply(response, spec, _ctx()) is response


def test_s04_rejects_unusable_factors() -> None:
    """A missing, boolean or non-finite factor is ignored."""
    assert _factor(FaultSpec("S04", "$primary", "all", 1.0, "permanent")) == 10
    assert _factor(FaultSpec("S04", "$primary", "all", 1.0, "permanent", params={"factor": 2})) == 2
    assert (
        _factor(FaultSpec("S04", "$primary", "all", 1.0, "permanent", params={"factor": "x"}))
        is None
    )
    assert (
        _factor(FaultSpec("S04", "$primary", "all", 1.0, "permanent", params={"factor": True}))
        is None
    )
    assert (
        _factor(
            FaultSpec("S04", "$primary", "all", 1.0, "permanent", params={"factor": float("inf")})
        )
        is None
    )


def test_numeric_path_helper() -> None:
    """``_numeric_path`` only reads a string path from a scenario."""
    assert _numeric_path(_ctx()) == "$.price"
    assert _numeric_path(_ctx(None)) is None
    assert _numeric_path(_ctx({"fault_targets": {"numeric_path": 3}})) is None
    assert _numeric_path(_ctx({"fault_targets": "nope"})) is None


# --- S05: wrong_entity -------------------------------------------------------


@pytest.mark.asyncio
async def test_s05_swaps_the_entity_argument_before_forwarding() -> None:
    """The argument is replaced with ``decoys.entity`` and the call is forwarded."""
    engine = _engine("S05")
    ctx = _ctx()
    call = _call(2, "get_quote", {"ticker": "ACME", "market": "US"})
    actions = await new_pipeline(fault=engine).on_c2s(call, ctx)
    forwarded = actions[0]
    assert isinstance(forwarded, Forward)
    assert forwarded.msg.params["arguments"] == {"ticker": "BOLT", "market": "US"}  # type: ignore[index]
    assert forwarded.msg.model_dump()["raw_bytes"] == b""


@pytest.mark.asyncio
async def test_s05_leaves_the_response_alone() -> None:
    """S05 modifies the request only; the response passes through unchanged (S6)."""
    engine = _engine("S05")
    ctx = _ctx()
    await new_pipeline(fault=engine).on_c2s(_call(2, "get_quote", {"ticker": "ACME"}), ctx)
    response = _synced(2, {"price": 14.0})
    assert await new_pipeline(fault=engine).on_s2c(response, ctx) == [Forward(response)]


@pytest.mark.asyncio
async def test_s05_without_the_entity_argument_forwards_unchanged() -> None:
    """A call that omits the entity argument has nothing to swap."""
    engine = _engine("S05")
    call = _call(2, "get_quote", {"market": "US"})
    assert await new_pipeline(fault=engine).on_c2s(call, _ctx()) == [Forward(call)]


@pytest.mark.asyncio
async def test_s05_without_arguments_forwards_unchanged() -> None:
    """A call with no ``arguments`` object is forwarded."""
    engine = _engine("S05")
    call = _call(2)
    assert await new_pipeline(fault=engine).on_c2s(call, _ctx()) == [Forward(call)]


@pytest.mark.asyncio
async def test_s05_ignores_other_tools() -> None:
    """The target filter keeps S05 away from a non-target tool."""
    engine = _engine("S05")
    call = _call(2, "get_history", {"ticker": "ACME"})
    assert await new_pipeline(fault=engine).on_c2s(call, _ctx()) == [Forward(call)]


def test_s05_is_applicable_only_with_the_scenario_fields() -> None:
    """S05 needs both ``entity_arg`` and ``decoys.entity`` (S7.4)."""
    assert WrongEntity().applicable(_ctx()) is True
    assert WrongEntity().applicable(_ctx(None)) is False
    assert WrongEntity().applicable(_ctx({"fault_targets": {"primary": ["get_quote"]}})) is False
    assert (
        WrongEntity().applicable(_ctx({"fault_targets": {"entity_arg": "ticker"}, "decoys": {}}))
        is False
    )
    assert (
        WrongEntity().applicable(
            _ctx({"fault_targets": {"entity_arg": ""}, "decoys": {"entity": "BOLT"}})
        )
        is False
    )


@pytest.mark.asyncio
async def test_s05_does_not_fire_when_not_applicable() -> None:
    """``applicable`` false keeps S05 silent even when the schedule would fire."""
    engine = FaultEngine([_engine_spec("S05")], scenario=None)
    call = _call(2, "get_quote", {"ticker": "ACME"})
    assert await new_pipeline(fault=engine).on_c2s(call, _ctx(None)) == [Forward(call)]


def _engine_spec(fault_id: str) -> FaultSpec:
    """Build a permanent spec on every attempt.

    Args:
        fault_id: The S6 fault id.

    Returns:
        The scheduled fault.
    """
    return FaultSpec(fault_id, "$primary", "all", 1.0, "permanent")


def test_entity_fields_helper() -> None:
    """``_entity_fields`` requires both fields to be present and well typed."""
    assert _entity_fields(_ctx()) == ("ticker", "BOLT")
    assert _entity_fields(_ctx({"decoys": {"entity": "BOLT"}})) is None
    assert _entity_fields(_ctx({"fault_targets": {"entity_arg": 3}})) is None
    assert _entity_fields(_ctx({"fault_targets": {"entity_arg": "ticker"}})) is None


def test_s01_to_s05_shapes() -> None:
    """A fault never claims a hook it does not implement (S4.4)."""
    for fault_id in ("S01", "S02", "S03", "S04"):
        assert get_fault(fault_id).hooks == ("post_call",)  # type: ignore[union-attr]
    assert get_fault("S05").hooks == ("pre_call",)  # type: ignore[union-attr]
    assert all(get_fault(f).cls == "silent" for f in ("S01", "S02", "S03", "S04", "S05"))  # type: ignore[union-attr]
