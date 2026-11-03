"""Unit tests for G51: G02 schema_guard, G03 staleness_guard, G04 emptiness_guard (S4.4, S11)."""

from __future__ import annotations

import os
from typing import Any

import pytest

from skeptic_agent.guards import (
    EMPTINESS_GUARD_TEXT,
    SCHEMA_GUARD_TEXT_TEMPLATE,
    STALENESS_GUARD_TEXT_TEMPLATE,
    EmptinessGuard,
    GuardSpec,
    SchemaGuard,
    StalenessGuard,
    build_guard_engine,
)
from skeptic_agent.guards.emptiness_guard import EmptinessGuard as EmptinessGuardAlias
from skeptic_agent.guards.staleness_guard import StalenessGuard as StalenessGuardAlias
from skeptic_agent.jsonrpc import ErrorObject, ErrorResponse, Response
from skeptic_agent.protocol import UNKNOWN
from skeptic_agent.proxy.context import EpisodeContext, PendingCall
from skeptic_agent.proxy.pipeline import C2S, RecorderStage


def _ctx(episode_id: str = "ep1", seed: int = 1, scenario: Any = None) -> EpisodeContext:
    """Helper to construct an EpisodeContext."""
    return EpisodeContext(episode_id=episode_id, seed=seed, era=UNKNOWN, scenario=scenario)


def _tool_response(
    id_: int | str,
    text: str | None = "ok",
    structured: Any = None,
    result_type: str = "complete",
    meta: dict[str, Any] | None = None,
    is_error: bool = False,
) -> Response:
    """Build a tools/call JSON-RPC Response."""
    res: dict[str, Any] = {"resultType": result_type}
    if is_error:
        res["isError"] = True
    content: list[dict[str, Any]] = []
    if text is not None:
        content.append({"type": "text", "text": text})
    res["content"] = content
    if structured is not None:
        res["structuredContent"] = structured
    if meta is not None:
        res["_meta"] = meta
    return Response(id=id_, result=res)


def _set_pending(
    ctx: EpisodeContext, id_: int | str, tool: str, arguments: dict[str, Any] | None = None
) -> None:
    """Set pending call in ctx."""
    ctx.pending[(C2S, id_)] = PendingCall(
        method="tools/call",
        tool_name=tool,
        arguments=arguments if arguments is not None else {},
        t_start=0.0,
        attempt=1,
    )


# =============================================================================
# 1. Verbatim Text Templates (S11)
# =============================================================================


def test_g02_verbatim_text_template() -> None:
    """G02 template matches S11 verbatim format."""
    expected_prefix = "[skeptic:schema_guard] Tool output failed validation: "
    expected_suffix = (
        ". Treat this result as unusable; retry, use another source, or report failure."
    )
    rendered = SCHEMA_GUARD_TEXT_TEMPLATE.format(detail="$.max_c: 140.0 > maximum 60")
    assert rendered.startswith(expected_prefix)
    assert rendered.endswith(expected_suffix)
    assert "$.max_c: 140.0 > maximum 60" in rendered


def test_g03_verbatim_text_template() -> None:
    """G03 template matches S11 verbatim format."""
    expected = (
        "[skeptic:staleness_guard] Result dates do not match the request or are older than "
        "30 days (2025-09-28). Treat as stale."
    )
    rendered = STALENESS_GUARD_TEXT_TEMPLATE.format(n=30, example_date="2025-09-28")
    assert rendered == expected


def test_g04_verbatim_text() -> None:
    """G04 text matches S11 verbatim format."""
    expected = (
        "[skeptic:emptiness_guard] Result is empty or truncated. "
        "Do not treat missing data as zero or as complete."
    )
    assert expected == EMPTINESS_GUARD_TEXT


# =============================================================================
# 2. G02 SchemaGuard Unit Tests
# =============================================================================


def test_schema_guard_valid_structured_content() -> None:
    """Valid structuredContent against declared outputSchema passes without loudify."""
    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "max_c": {"type": "number", "maximum": 60},
        },
        "required": ["city", "max_c"],
    }
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard", params={"output_schema": schema}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_forecast")

    resp = _tool_response(1, structured={"city": "Paris", "max_c": 14.5})
    res = guard.on_s2c_call(resp, ctx, "get_forecast")
    assert res is None


def test_schema_guard_valid_parsed_json_text() -> None:
    """Valid parsed JSON text when structuredContent is absent passes."""
    schema = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard", params={"output_schema": schema}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_forecast")

    resp = _tool_response(1, text='{"city": "Paris"}', structured=None)
    res = guard.on_s2c_call(resp, ctx, "get_forecast")
    assert res is None


def test_schema_guard_violating_constraint_loudified() -> None:
    """Exceeding outputSchema range (e.g. maximum constraint from S04) loudifies result."""
    schema = {
        "type": "object",
        "properties": {
            "max_c": {"type": "number", "maximum": 60},
        },
        "required": ["max_c"],
    }
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard", params={"output_schema": schema}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_forecast")

    # max_c is 145.0 (> maximum 60)
    resp = _tool_response(1, structured={"max_c": 145.0}, meta={"foo": "bar"})
    res = guard.on_s2c_call(resp, ctx, "get_forecast")
    assert res is not None

    # Check loudify format
    rewritten = res.msg
    assert isinstance(rewritten, Response)
    assert rewritten.result["isError"] is True
    assert rewritten.result["_meta"] == {"foo": "bar"}
    text = rewritten.result["content"][0]["text"]
    assert "[skeptic:schema_guard] Tool output failed validation:" in text
    assert "maximum" in text
    assert text.endswith(
        ". Treat this result as unusable; retry, use another source, or report failure."
    )

    # Check note
    assert res.note is not None
    assert res.note["id"] == "schema_guard"
    assert res.note["action"] == "loudify"


def test_schema_guard_missing_structured_and_unparseable_text() -> None:
    """When outputSchema is declared but output is neither structured nor JSON, loudifies."""
    schema = {"type": "object", "properties": {"status": {"type": "string"}}}
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard", params={"output_schema": schema}))
    ctx = _ctx()
    _set_pending(ctx, 1, "do_action")

    resp = _tool_response(1, text="Not a JSON text at all", structured=None)
    res = guard.on_s2c_call(resp, ctx, "do_action")
    assert res is not None
    text = res.msg.result["content"][0]["text"]  # type: ignore[union-attr]
    assert "[skeptic:schema_guard] Tool output failed validation:" in text
    assert "missing structuredContent and text is not valid JSON" in text


def test_schema_guard_previous_json_then_unparseable() -> None:
    """When same tool previously returned JSON, unparseable text in current call loudifies."""
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard"))  # No schema declared
    ctx = _ctx()

    # First call returns valid JSON
    _set_pending(ctx, 1, "echo")
    resp1 = _tool_response(1, text='{"status": "ok"}', structured=None)
    assert guard.on_s2c_call(resp1, ctx, "echo") is None

    # Second call returns non-JSON
    _set_pending(ctx, 2, "echo")
    resp2 = _tool_response(2, text="Random error text", structured=None)
    res2 = guard.on_s2c_call(resp2, ctx, "echo")
    assert res2 is not None
    text = res2.msg.result["content"][0]["text"]  # type: ignore[union-attr]
    assert "[skeptic:schema_guard] Tool output failed validation:" in text
    assert "previous result was valid JSON" in text


def test_schema_guard_ignores_non_complete_and_errors() -> None:
    """SchemaGuard ignores resultType != complete and responses with isError=True."""
    guard = SchemaGuard(GuardSpec(guard_id="schema_guard"))
    ctx = _ctx()

    incomplete = _tool_response(1, text="err", result_type="input_required")
    assert guard.on_s2c_call(incomplete, ctx, "test") is None

    already_err = _tool_response(2, text="err", is_error=True)
    assert guard.on_s2c_call(already_err, ctx, "test") is None

    rpc_err = ErrorResponse(id=3, error=ErrorObject(code=-32603, message="Internal error"))
    assert guard.on_s2c_call(rpc_err, ctx, "test") is None


# =============================================================================
# 3. G03 StalenessGuard Unit Tests
# =============================================================================


def test_staleness_guard_fresh_date_matches_request() -> None:
    """Fresh date matching request date within <= 1 day passes without loudify."""
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard", params={"max_age_days": 30}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_forecast", {"city": "Paris", "date": "2026-11-02"})

    os.environ["SKEPTIC_FROZEN_NOW"] = "2026-11-01T09:00:00Z"
    try:
        resp = _tool_response(1, structured={"date": "2026-11-02", "max_c": 14.5})
        assert guard.on_s2c_call(resp, ctx, "get_forecast") is None
    finally:
        os.environ.pop("SKEPTIC_FROZEN_NOW", None)


def test_staleness_guard_condition_a_request_date_mismatch() -> None:
    """When calling args have date D and result has no date within <= 1 day, loudifies."""
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard", params={"max_age_days": 30}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_forecast", {"city": "Paris", "date": "2026-11-02"})

    # Result has date 2026-10-15 (diff > 1 day)
    resp = _tool_response(1, structured={"date": "2026-10-15", "max_c": 14.5})
    res = guard.on_s2c_call(resp, ctx, "get_forecast")
    assert res is not None

    text = res.msg.result["content"][0]["text"]  # type: ignore[union-attr]
    assert "[skeptic:staleness_guard]" in text
    assert "Result dates do not match the request" in text
    assert "(2026-10-15)" in text
    assert text.endswith(". Treat as stale.")


def test_staleness_guard_condition_b_all_dates_older_than_max_age_days() -> None:
    """When all dates in result are older than now by > max_age_days (e.g. S03), loudifies."""
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard", params={"max_age_days": 30}))
    ctx = _ctx()
    # Call without explicit date argument
    _set_pending(ctx, 1, "get_latest_news")

    os.environ["SKEPTIC_FROZEN_NOW"] = "2026-11-01T09:00:00Z"
    try:
        # Date is 400 days old (2025-09-27)
        resp = _tool_response(1, structured={"date": "2025-09-27T10:00:00Z", "headline": "Old"})
        res = guard.on_s2c_call(resp, ctx, "get_latest_news")
        assert res is not None

        text = res.msg.result["content"][0]["text"]  # type: ignore[union-attr]
        assert "[skeptic:staleness_guard]" in text
        assert "older than 30 days" in text
        assert "2025-09-27" in text
        assert text.endswith(". Treat as stale.")
    finally:
        os.environ.pop("SKEPTIC_FROZEN_NOW", None)


def test_staleness_guard_excluded_entity_metadata_keys_pass() -> None:
    """Historical entity metadata (created_at, updated_at, registered_at) does not
    trigger staleness.
    """
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard", params={"max_age_days": 30}))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_customer")

    os.environ["SKEPTIC_FROZEN_NOW"] = "2026-11-01T09:00:00Z"
    try:
        # created_at and updated_at from 2025 are entity history, not data freshness
        resp = _tool_response(
            1,
            structured={
                "id": "cust_123",
                "name": "Acme",
                "created_at": "2025-05-15T00:00:00Z",
                "updated_at": "2025-06-20T00:00:00Z",
                "registered_at": "2025-05-15T00:00:00Z",
            },
        )
        assert guard.on_s2c_call(resp, ctx, "get_customer") is None
    finally:
        os.environ.pop("SKEPTIC_FROZEN_NOW", None)


def test_staleness_guard_no_dates_in_result_passes() -> None:
    """When result contains no date leaves, staleness_guard returns None."""
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard"))
    ctx = _ctx()
    _set_pending(ctx, 1, "calculate", {"a": 1, "b": 2})

    resp = _tool_response(1, structured={"result": 3}, text="3")
    assert guard.on_s2c_call(resp, ctx, "calculate") is None


# =============================================================================
# 4. G04 EmptinessGuard Unit Tests
# =============================================================================


def test_emptiness_guard_condition_1_empty_structured_content() -> None:
    """structuredContent of {} or [] triggers emptiness_guard loudify (S01)."""
    guard = EmptinessGuard(GuardSpec(guard_id="emptiness_guard"))
    ctx = _ctx()
    _set_pending(ctx, 1, "get_data")

    # Case 1a: {}
    resp_obj = _tool_response(1, structured={})
    res_obj = guard.on_s2c_call(resp_obj, ctx, "get_data")
    assert res_obj is not None
    assert res_obj.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT  # type: ignore[union-attr]
    assert res_obj.msg.result["isError"] is True  # type: ignore[union-attr]

    # Case 1b: []
    resp_arr = _tool_response(2, structured=[])
    res_arr = guard.on_s2c_call(resp_arr, ctx, "get_data")
    assert res_arr is not None
    assert res_arr.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT  # type: ignore[union-attr]


def test_emptiness_guard_condition_2_empty_text() -> None:
    """Empty text block triggers emptiness_guard."""
    guard = EmptinessGuard(GuardSpec(guard_id="emptiness_guard"))
    ctx = _ctx()
    _set_pending(ctx, 1, "read_file")

    resp = _tool_response(1, text="", structured=None)
    res = guard.on_s2c_call(resp, ctx, "read_file")
    assert res is not None
    assert res.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT  # type: ignore[union-attr]


def test_emptiness_guard_condition_3_malformed_json_text() -> None:
    """Text starting with { or [ but failing JSON parse triggers emptiness_guard (S07)."""
    guard = EmptinessGuard(GuardSpec(guard_id="emptiness_guard"))
    ctx = _ctx()
    _set_pending(ctx, 1, "fetch_json")

    # Truncated JSON starting with {
    resp = _tool_response(1, text='{"city": "Paris", "temp":', structured=None)
    res = guard.on_s2c_call(resp, ctx, "fetch_json")
    assert res is not None
    assert res.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT  # type: ignore[union-attr]


def test_emptiness_guard_condition_4_array_shrinkage() -> None:
    """Array shrinking to < n/2 for same tool and same arguments triggers emptiness_guard (S02)."""
    guard = EmptinessGuard(GuardSpec(guard_id="emptiness_guard"))
    ctx = _ctx()

    # Call 1: array length 10
    _set_pending(ctx, 1, "list_items", {"category": "books"})
    items_10 = [{"id": i} for i in range(10)]
    resp1 = _tool_response(1, structured={"items": items_10})
    assert guard.on_s2c_call(resp1, ctx, "list_items") is None

    # Call 2: same tool and same args, array length 3 (3 < 10/2)
    _set_pending(ctx, 2, "list_items", {"category": "books"})
    items_3 = [{"id": i} for i in range(3)]
    resp2 = _tool_response(2, structured={"items": items_3})
    res2 = guard.on_s2c_call(resp2, ctx, "list_items")
    assert res2 is not None
    assert res2.msg.result["content"][0]["text"] == EMPTINESS_GUARD_TEXT  # type: ignore[union-attr]


def test_emptiness_guard_allow_empty_tools_bypass() -> None:
    """Tools declared in allow_empty_tools parameter are exempt from emptiness checks."""
    guard = EmptinessGuard(
        GuardSpec(guard_id="emptiness_guard", params={"allow_empty_tools": ["empty_ok_*", "ping"]})
    )
    ctx = _ctx()
    _set_pending(ctx, 1, "empty_ok_search")

    resp = _tool_response(1, structured={}, text="")
    assert guard.on_s2c_call(resp, ctx, "empty_ok_search") is None


# =============================================================================
# 5. Pipeline Integration & S4.4 Order
# =============================================================================


class MockRecorder(RecorderStage):
    """Recorder mock collecting guard notes."""

    def __init__(self) -> None:
        self.notes: list[dict[str, Any]] = []

    def note_guard(self, note: dict[str, Any]) -> None:
        self.notes.append(note)


@pytest.mark.asyncio
async def test_guard_engine_populates_ctx_tool_defs_and_validates() -> None:
    """GuardEngine populates tool_defs on tools/list response and validates on tools/call."""
    schema = {
        "type": "object",
        "properties": {"val": {"type": "number", "maximum": 50}},
        "required": ["val"],
    }
    engine = build_guard_engine(["schema_guard"])
    ctx = _ctx()

    # 1. Server returns tools/list response
    ctx.pending[(C2S, 10)] = PendingCall(
        method="tools/list", tool_name=None, arguments=None, t_start=0.0, attempt=0
    )
    list_resp = Response(
        id=10,
        result={"tools": [{"name": "compute", "outputSchema": schema}]},
    )
    actions = await engine.on_s2c(list_resp, ctx)
    assert len(actions) == 1
    assert "compute" in ctx.tool_defs
    assert ctx.tool_defs["compute"]["outputSchema"] == schema

    # 2. tools/call response with invalid value (100 > maximum 50)
    ctx.pending[(C2S, 11)] = PendingCall(
        method="tools/call", tool_name="compute", arguments={}, t_start=0.0, attempt=1
    )
    call_resp = Response(
        id=11,
        result={
            "content": [{"type": "text", "text": '{"val": 100}'}],
            "structuredContent": {"val": 100},
        },
    )
    actions_call = await engine.on_s2c(call_resp, ctx)
    assert len(actions_call) == 1
    forwarded = actions_call[0].msg  # type: ignore[attr-defined]
    assert isinstance(forwarded, Response)
    assert forwarded.result["isError"] is True
    assert "maximum" in forwarded.result["content"][0]["text"]


# =============================================================================
# 6. Re-export Aliases and Coverage Edge Cases
# =============================================================================


def test_aliases_reexport() -> None:
    """Re-export alias modules import and match original classes."""
    assert EmptinessGuardAlias is EmptinessGuard
    assert StalenessGuardAlias is StalenessGuard


def test_schema_guard_scenario_and_params_schemas() -> None:
    """SchemaGuard retrieves schemas from params schemas dict or scenario tool_defs."""
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}

    # 1. From params['schemas'][tool_name]
    g1 = SchemaGuard(GuardSpec(guard_id="schema_guard", params={"schemas": {"my_tool": schema}}))
    ctx1 = _ctx()
    _set_pending(ctx1, 1, "my_tool")
    res1 = g1.on_s2c_call(_tool_response(1, structured={"x": "not_an_int"}), ctx1, "my_tool")
    assert res1 is not None

    # 2. From scenario tool_defs
    ctx2 = _ctx(scenario={"tool_defs": {"my_scen_tool": {"outputSchema": schema}}})
    g2 = SchemaGuard(GuardSpec(guard_id="schema_guard"))
    _set_pending(ctx2, 2, "my_scen_tool")
    res2 = g2.on_s2c_call(_tool_response(2, structured={"x": 10}), ctx2, "my_scen_tool")
    assert res2 is None

    # 3. From scenario tools list
    ctx3 = _ctx(scenario={"tools": [{"name": "my_list_tool", "output_schema": schema}]})
    _set_pending(ctx3, 3, "my_list_tool")
    res3 = g2.on_s2c_call(_tool_response(3, structured={"x": 10}), ctx3, "my_list_tool")
    assert res3 is None


def test_staleness_guard_scenario_frozen_now_and_edge_cases() -> None:
    """StalenessGuard reads frozen_now from scenario and handles edge cases."""
    ctx = _ctx(scenario={"frozen_now": "2026-11-01T09:00:00Z"})
    guard = StalenessGuard(GuardSpec(guard_id="staleness_guard", params={"max_age_days": 10}))
    _set_pending(ctx, 1, "check_news")

    resp = _tool_response(1, text="Report dated 2026-10-10.", structured=None)
    res = guard.on_s2c_call(resp, ctx, "check_news")
    assert res is not None
    assert "2026-10-10" in res.msg.result["content"][0]["text"]  # type: ignore[union-attr]


def test_emptiness_guard_string_allow_and_reset() -> None:
    """EmptinessGuard handles allow_empty_tools string and reset()."""
    guard = EmptinessGuard(
        GuardSpec(guard_id="emptiness_guard", params={"allow_empty_tools": "exempt_*"})
    )
    assert guard._is_tool_allowed_empty("exempt_tool") is True
    assert guard._is_tool_allowed_empty("other_tool") is False

    ctx = _ctx()
    _set_pending(ctx, 1, "query", {"arg": 1})
    resp = _tool_response(1, structured={"data": [1, 2, 3, 4]})
    assert guard.on_s2c_call(resp, ctx, "query") is None
    assert len(guard._max_array_lens) == 1
    guard.reset()
    assert len(guard._max_array_lens) == 0
