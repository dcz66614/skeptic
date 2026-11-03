"""Unit tests for Guard framework, presets, G01 and G06 (G50, S4.4, S11)."""

import time
from typing import Any

import pytest

from skeptic_agent.guards import (
    ALL_GUARDS,
    EVIDENCE_CONTRACT_TEXT,
    LOOP_BREAKER_TEXT_TEMPLATE,
    PRESETS,
    EvidenceContract,
    Guard,
    GuardEngine,
    GuardResult,
    GuardSpec,
    LoopBreaker,
    build_guard_engine,
    loudify,
    resolve_guards,
)
from skeptic_agent.jsonrpc import ErrorObject, ErrorResponse, Message, Request, Response
from skeptic_agent.protocol import UNKNOWN
from skeptic_agent.proxy.context import EpisodeContext, PendingCall
from skeptic_agent.proxy.pipeline import (
    C2S,
    FaultStage,
    Forward,
    RecorderStage,
    ReplyToClient,
    new_pipeline,
)


def _ctx(episode_id: str = "ep1", seed: int = 1) -> EpisodeContext:
    """Helper to construct an EpisodeContext."""
    return EpisodeContext(episode_id=episode_id, seed=seed, era=UNKNOWN)


def _call(id_: int | str, tool: str, arguments: dict[str, Any] | None = None) -> Request:
    """Build a tools/call request."""
    return Request(
        id=id_,
        method="tools/call",
        params={"name": tool, "arguments": arguments if arguments is not None else {}},
    )


def _tool_response(
    id_: int | str,
    text: str = "ok",
    structured: dict[str, Any] | None = None,
    result_type: str = "complete",
    meta: dict[str, Any] | None = None,
) -> Response:
    """Build a tools/call JSON-RPC Response."""
    res: dict[str, Any] = {
        "content": [{"type": "text", "text": text}],
        "resultType": result_type,
    }
    if structured is not None:
        res["structuredContent"] = structured
    if meta is not None:
        res["_meta"] = meta
    return Response(id=id_, result=res)


# =============================================================================
# 1. Presets and Name Resolution (S11)
# =============================================================================


def test_all_guards_catalogue() -> None:
    """ALL_GUARDS must define the exact 8 guards from S11."""
    assert len(ALL_GUARDS) == 8
    expected = (
        "evidence_contract",
        "schema_guard",
        "staleness_guard",
        "emptiness_guard",
        "retry_guard",
        "loop_breaker",
        "injection_shield",
        "drift_lock",
    )
    assert expected == ALL_GUARDS


def test_presets_definitions() -> None:
    """Presets 'none', 'all', and 'recommended' conform to S11."""
    assert PRESETS["none"] == []
    assert PRESETS["all"] == list(ALL_GUARDS)
    # Recommended must NOT contain G01 evidence_contract before G53
    assert "evidence_contract" not in PRESETS["recommended"]
    assert "schema_guard" in PRESETS["recommended"]
    assert "loop_breaker" in PRESETS["recommended"]
    assert len(PRESETS["recommended"]) == 7


def test_resolve_guards() -> None:
    """resolve_guards parses preset names, strings, sequences, and checks valid names."""
    assert resolve_guards(None) == []
    assert resolve_guards("none") == []
    assert resolve_guards("all") == list(ALL_GUARDS)
    assert resolve_guards("recommended") == PRESETS["recommended"]
    assert resolve_guards("evidence_contract, loop_breaker") == [
        "evidence_contract",
        "loop_breaker",
    ]
    assert resolve_guards(["loop_breaker"]) == ["loop_breaker"]

    with pytest.raises(ValueError, match="unknown guard"):
        resolve_guards("non_existent_guard")


# =============================================================================
# 2. Unified Loudify (S4.5)
# =============================================================================


def test_loudify() -> None:
    """loudify produces unified S4.5 shape: content with text, isError=True, optional _meta."""
    res1 = loudify("Something failed")
    assert res1 == {
        "content": [{"type": "text", "text": "Something failed"}],
        "isError": True,
    }

    meta = {"timestamp": "2026-11-03T00:00:00Z"}
    res2 = loudify("Something failed", meta=meta)
    assert res2 == {
        "content": [{"type": "text", "text": "Something failed"}],
        "isError": True,
        "_meta": meta,
    }


# =============================================================================
# 3. G01 Evidence Contract (S11)
# =============================================================================


def test_g01_verbatim_text() -> None:
    """Verbatim text check for G01 evidence_contract (S11)."""
    expected = (
        "[skeptic:evidence] Before relying on this result, check that it answers the request "
        "(right entity, date, units, completeness). If it is empty, truncated, stale, inconsistent "
        'or an error, reply with "RETRIEVAL_STATUS: FAILED" and do not invent values.'
    )
    assert expected == EVIDENCE_CONTRACT_TEXT


def test_g01_appends_text_block_to_content() -> None:
    """G01 appends evidence contract block to tools/call content."""
    guard = EvidenceContract()
    ctx = _ctx()

    resp = _tool_response(1, text="The temperature is 21C.")
    res = guard.on_s2c_call(resp, ctx, "get_weather")
    assert res is not None
    assert isinstance(res.msg, Response)
    assert isinstance(res.msg.result, dict)

    content = res.msg.result["content"]
    assert len(content) == 2
    assert content[0] == {"type": "text", "text": "The temperature is 21C."}
    assert content[1] == {"type": "text", "text": EVIDENCE_CONTRACT_TEXT}

    # Verify cassette note
    assert res.note == {
        "id": "evidence_contract",
        "action": "contract_appended",
        "detail": "tool 'get_weather' result appended evidence contract",
    }


def test_g01_handles_empty_initial_content() -> None:
    """G01 works even when initial content is empty."""
    guard = EvidenceContract()
    ctx = _ctx()
    resp = Response(id=1, result={"resultType": "complete"})
    res = guard.on_s2c_call(resp, ctx, "ping")
    assert res is not None
    assert isinstance(res.msg, Response)
    assert isinstance(res.msg.result, dict)
    assert res.msg.result["content"] == [{"type": "text", "text": EVIDENCE_CONTRACT_TEXT}]


def test_g01_leaves_non_complete_result_type_alone() -> None:
    """S4.5: Any resultType other than 'complete' is untouched."""
    guard = EvidenceContract()
    ctx = _ctx()
    resp = _tool_response(1, text="Please confirm", result_type="input_required")
    res = guard.on_s2c_call(resp, ctx, "ask_user")
    assert res is None


def test_g01_matches_tool_glob() -> None:
    """G01 respects tool target glob."""
    guard = EvidenceContract(GuardSpec(guard_id="evidence_contract", tools="get_*"))
    assert guard.matches_tool("get_weather") is True
    assert guard.matches_tool("set_weather") is False


# =============================================================================
# 4. G06 Loop Breaker (S11)
# =============================================================================


def test_g06_verbatim_text_template() -> None:
    """Verbatim text template check for G06 loop_breaker (S11)."""
    expected = (
        "[skeptic:loop_breaker] This exact call was already made 3 times with the same result. "
        "Change your approach or report that the task cannot be completed."
    )
    assert LOOP_BREAKER_TEXT_TEMPLATE.format(n=3) == expected


def test_g06_trips_on_third_consecutive_call() -> None:
    """G06 allows first 2 identical calls, intercepts the 3rd with loud error."""
    guard = LoopBreaker(GuardSpec(guard_id="loop_breaker", params={"threshold": 3}))
    ctx = _ctx()

    call1 = _call(1, "get_weather", {"city": "Paris", "units": "C"})
    call2 = _call(2, "get_weather", {"units": "C", "city": "Paris"})  # canonical json match
    call3 = _call(3, "get_weather", {"city": "Paris", "units": "C"})

    assert guard.on_c2s(call1, ctx) is None
    assert guard.on_c2s(call2, ctx) is None

    res3 = guard.on_c2s(call3, ctx)
    assert res3 is not None
    assert isinstance(res3.action, ReplyToClient)
    assert isinstance(res3.action.msg, Response)
    assert res3.action.msg.id == 3

    result = res3.action.msg.result
    assert isinstance(result, dict)
    assert result["isError"] is True
    expected_msg = (
        "[skeptic:loop_breaker] This exact call was already made 3 times with the same result. "
        "Change your approach or report that the task cannot be completed."
    )
    assert result["content"] == [{"type": "text", "text": expected_msg}]

    assert res3.note is not None
    assert res3.note["id"] == "loop_breaker"
    assert res3.note["action"] == "blocked"

    # 4th call is also blocked
    call4 = _call(4, "get_weather", {"city": "Paris", "units": "C"})
    res4 = guard.on_c2s(call4, ctx)
    assert res4 is not None
    assert isinstance(res4.action, ReplyToClient)


def test_g06_different_call_resets_counter() -> None:
    """An intervening different call resets the consecutive counter."""
    guard = LoopBreaker()
    ctx = _ctx()

    c_paris = _call(1, "get_weather", {"city": "Paris"})
    c_london = _call(2, "get_weather", {"city": "London"})

    assert guard.on_c2s(c_paris, ctx) is None  # count = 1
    assert guard.on_c2s(c_paris, ctx) is None  # count = 2
    assert guard.on_c2s(c_london, ctx) is None  # reset, count = 1
    assert guard.on_c2s(c_paris, ctx) is None  # reset, count = 1
    assert guard.on_c2s(c_paris, ctx) is None  # count = 2
    # 3rd consecutive Paris call
    res = guard.on_c2s(c_paris, ctx)
    assert res is not None
    assert isinstance(res.action, ReplyToClient)


def test_g06_resets_on_new_episode() -> None:
    """Context episode_id change triggers reset."""
    guard = LoopBreaker()
    ctx1 = _ctx(episode_id="ep1")
    ctx2 = _ctx(episode_id="ep2")

    c = _call(1, "echo", {"msg": "hi"})
    assert guard.on_c2s(c, ctx1) is None
    assert guard.on_c2s(c, ctx1) is None

    # New episode begins
    assert guard.on_c2s(c, ctx2) is None
    assert guard.on_c2s(c, ctx2) is None
    # 3rd in ep2 trips
    res = guard.on_c2s(c, ctx2)
    assert res is not None
    assert isinstance(res.action, ReplyToClient)


# =============================================================================
# 5. Guard Pipeline & S4.4 Execution Order
# =============================================================================


@pytest.mark.asyncio
async def test_guard_order_s4_4_conformance() -> None:
    """Verify execution order conforming strictly to S4.4.

    c2s: recorder -> G06 -> G07 -> fault stage
    s2c: fault stage -> G05 -> G02/03/04 -> G01 -> G07 -> recorder
    """
    call_log: list[str] = []

    class MockRecorder(RecorderStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Any]:
            call_log.append("recorder_c2s")
            return [Forward(msg)]

        async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Any]:
            call_log.append("recorder_s2c")
            return [Forward(msg)]

    class MockFault(FaultStage):
        async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Any]:
            call_log.append("fault_c2s")
            return [Forward(msg)]

        async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Any]:
            call_log.append("fault_s2c")
            return [Forward(msg)]

    class MockG06(Guard):
        id = "loop_breaker"
        hooks = ("c2s",)

        def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
            call_log.append("g06_c2s")
            return None

    class MockG07(Guard):
        id = "injection_shield"
        hooks = ("c2s", "s2c_call")

        def on_c2s(self, msg: Request, ctx: EpisodeContext) -> GuardResult | None:
            call_log.append("g07_c2s")
            return None

        def on_s2c_call(
            self, msg: Response | Any, ctx: EpisodeContext, tool_name: str | None
        ) -> GuardResult | None:
            call_log.append("g07_s2c")
            return None

    class MockG01(Guard):
        id = "evidence_contract"
        hooks = ("s2c_call",)

        def on_s2c_call(
            self, msg: Response | Any, ctx: EpisodeContext, tool_name: str | None
        ) -> GuardResult | None:
            call_log.append("g01_s2c")
            return None

    class MockG02(Guard):
        id = "schema_guard"
        hooks = ("s2c_call",)

        def on_s2c_call(
            self, msg: Response | Any, ctx: EpisodeContext, tool_name: str | None
        ) -> GuardResult | None:
            call_log.append("g02_s2c")
            return None

    class MockG05(Guard):
        id = "retry_guard"
        hooks = ("s2c_call",)

        def on_s2c_call(
            self, msg: Response | Any, ctx: EpisodeContext, tool_name: str | None
        ) -> GuardResult | None:
            call_log.append("g05_s2c")
            return None

    # Construct engine with all mock guards
    guards = [MockG06(), MockG07(), MockG01(), MockG02(), MockG05()]
    guard_engine = GuardEngine(guards)

    pipeline = new_pipeline(
        fault=MockFault(),
        guard=guard_engine,
        recorder=MockRecorder(),
    )

    ctx = _ctx()
    req = _call(1, "my_tool", {"x": 1})

    # Run c2s
    actions_c2s = await pipeline.on_c2s(req, ctx)
    assert isinstance(actions_c2s[0], Forward)
    # Expected c2s order: recorder -> G06 -> G07 -> fault
    assert call_log == ["recorder_c2s", "g06_c2s", "g07_c2s", "fault_c2s"]

    # Clear log and run s2c
    call_log.clear()
    resp = _tool_response(1, text="answer")
    actions_s2c = await pipeline.on_s2c(resp, ctx)
    assert isinstance(actions_s2c[0], Forward)
    # Expected s2c order: fault -> G05 -> G02 -> G01 -> G07 -> recorder
    assert call_log == [
        "fault_s2c",
        "g05_s2c",
        "g02_s2c",
        "g01_s2c",
        "g07_s2c",
        "recorder_s2c",
    ]


@pytest.mark.asyncio
async def test_guard_engine_records_notes_to_recorder() -> None:
    """GuardEngine passes guard notes to recorder stage."""

    class SpyingRecorder(RecorderStage):
        def __init__(self) -> None:
            self.notes: list[dict[str, Any]] = []

        def note_guard(self, note: Any) -> None:
            self.notes.append(dict(note))

    recorder = SpyingRecorder()
    engine = build_guard_engine(["evidence_contract"], recorder=recorder)
    pipeline = new_pipeline(guard=engine, recorder=recorder)

    ctx = _ctx()
    ctx.pending[(C2S, 1)] = PendingCall(
        method="tools/call",
        tool_name="echo",
        arguments={},
        t_start=time.monotonic(),
        attempt=1,
    )

    resp = _tool_response(1, text="hello")
    await pipeline.on_s2c(resp, ctx)

    assert len(recorder.notes) == 1
    assert recorder.notes[0]["id"] == "evidence_contract"
    assert recorder.notes[0]["action"] == "contract_appended"


@pytest.mark.asyncio
async def test_pipeline_g06_blocks_and_avoids_fault_and_attempt_count() -> None:
    """When G06 intercepts on call 3, attempt count is not incremented (ADR-0007)."""
    engine = build_guard_engine(["loop_breaker"])
    pipeline = new_pipeline(guard=engine)
    ctx = _ctx()

    c = _call(1, "repeat_tool", {"a": 1})
    a1 = await pipeline.on_c2s(c, ctx)
    assert isinstance(a1[0], Forward)
    assert ctx.call_counts["repeat_tool"] == 1

    c2 = _call(2, "repeat_tool", {"a": 1})
    a2 = await pipeline.on_c2s(c2, ctx)
    assert isinstance(a2[0], Forward)
    assert ctx.call_counts["repeat_tool"] == 2

    # 3rd call intercepted by G06
    c3 = _call(3, "repeat_tool", {"a": 1})
    a3 = await pipeline.on_c2s(c3, ctx)
    assert isinstance(a3[0], ReplyToClient)
    # Because intercepted before fault stage, attempt is NOT incremented (ADR-0007)
    assert ctx.call_counts["repeat_tool"] == 2


@pytest.mark.asyncio
async def test_base_guard_defaults_and_matching() -> None:
    """Base Guard class default methods and tool pattern matching."""
    guard = Guard(GuardSpec(guard_id="base_test", tools=("echo*", "calc*")))
    ctx = _ctx()
    req = _call(1, "echo", {})
    resp = _tool_response(1, "ok")

    assert guard.matches_tool(None) is True
    assert guard.matches_tool("echo") is True
    assert guard.matches_tool("calc_sum") is True
    assert guard.matches_tool("other") is False
    assert guard.on_c2s(req, ctx) is None
    assert guard.on_s2c_call(resp, ctx, "echo") is None
    assert guard.on_s2c_list(resp, ctx) is None


@pytest.mark.asyncio
async def test_guard_engine_c2s_non_tool_call_and_filtering() -> None:
    """GuardEngine handles non-tool-call messages and non-matching tools gracefully."""
    engine = build_guard_engine(["loop_breaker"])
    ctx = _ctx()

    # Non-tools/call request
    not_call = Request(id=1, method="tools/list", params={})
    res1 = await engine.on_c2s(not_call, ctx)
    assert isinstance(res1[0], Forward)

    # Invalid params
    inv_params = Request(id=2, method="tools/call", params=None)  # type: ignore[arg-type]
    res2 = await engine.on_c2s(inv_params, ctx)
    assert isinstance(res2[0], Forward)

    # Tool name not str
    bad_name = Request(id=3, method="tools/call", params={"name": 123})
    res3 = await engine.on_c2s(bad_name, ctx)
    assert isinstance(res3[0], Forward)

    # Test build_guard_engine variants
    empty_engine = build_guard_engine(None)
    assert len(empty_engine._guards_by_id) == 0

    preset_engine = build_guard_engine("recommended")
    assert "loop_breaker" in preset_engine._guards_by_id

    spec_engine = build_guard_engine([GuardSpec(guard_id="loop_breaker")])
    assert "loop_breaker" in spec_engine._guards_by_id


@pytest.mark.asyncio
async def test_guard_engine_s2c_variants_and_list_guards() -> None:
    """GuardEngine s2c paths: missing id, missing pending, tools/list, and action returning."""

    # Dummy list guard to exercise S2C_LIST_GUARD_ORDER
    class DummyListGuard(Guard):
        id: str = "drift_lock"
        hooks: tuple[str, ...] = ("s2c_list",)

        def on_s2c_list(
            self, msg: Response | ErrorResponse, ctx: EpisodeContext
        ) -> GuardResult | None:
            return GuardResult(
                msg=Response(id=msg.id, result={"tools": ["mutated"]}),
                note={"id": self.id, "action": "drift_locked"},
            )

    guard_inst = DummyListGuard(GuardSpec(guard_id="drift_lock"))
    engine = GuardEngine([guard_inst])
    ctx = _ctx()

    # Missing message id
    req = Request(id=1, method="tools/call")
    res_no_id = await engine.on_s2c(req, ctx)
    assert isinstance(res_no_id[0], Forward)

    # Message id not in pending
    resp = Response(id=99, result={})
    res_no_pend = await engine.on_s2c(resp, ctx)
    assert isinstance(res_no_pend[0], Forward)

    # Pending tools/list
    ctx.pending[(C2S, 10)] = PendingCall(
        method="tools/list",
        tool_name=None,
        arguments={},
        t_start=time.monotonic(),
        attempt=1,
    )
    list_resp = Response(id=10, result={"tools": ["original"]})
    res_list = await engine.on_s2c(list_resp, ctx)
    assert isinstance(res_list[0], Forward)
    assert isinstance(res_list[0].msg, Response)
    assert res_list[0].msg.result == {"tools": ["mutated"]}


@pytest.mark.asyncio
async def test_evidence_contract_and_loop_breaker_edge_cases() -> None:
    """Edge cases for G01 and G06 guard handlers."""
    g01 = EvidenceContract(GuardSpec(guard_id="evidence_contract"))
    ctx = _ctx()

    # G01 ignores ErrorResponse
    err = ErrorResponse(id=1, error=ErrorObject(code=500, message="fail"))
    assert g01.on_s2c_call(err, ctx, "echo") is None

    # G01 ignores resultType != complete
    incomplete = Response(id=1, result={"resultType": "in_progress", "content": []})
    assert g01.on_s2c_call(incomplete, ctx, "echo") is None

    # G06 edge cases on request params
    g06 = LoopBreaker(GuardSpec(guard_id="loop_breaker"))
    bad_req1 = Request(id=1, method="tools/call", params=None)  # type: ignore[arg-type]
    assert g06.on_c2s(bad_req1, ctx) is None

    bad_req2 = Request(id=2, method="tools/call", params={"name": 999})
    assert g06.on_c2s(bad_req2, ctx) is None
