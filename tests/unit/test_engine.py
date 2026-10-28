"""Unit tests for the fault engine stage and registry (S4.4, S7).

The fault classes here are local fakes; F21-F24 register the real 20 faults.
"""

import json
from typing import Any

import pytest

from skeptic_agent.faults.base import Fault, FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.faults.registry import REGISTRY, get_fault, register
from skeptic_agent.jsonrpc import Message, Request, Response, parse_line
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import C2S, Forward, new_pipeline

pytestmark = pytest.mark.unit

ERA = Era(kind="MODERN", version="2026-07-28")

SCENARIO = {
    "id": "weather.forecast.max-temp.001",
    "fault_targets": {"primary": ["get_forecast"], "write_tools": []},
}


class RecordingFault(Fault):
    """A fake fault that records the attempt number of every firing."""

    id = "T01"
    cls = "silent"
    hooks: tuple[str, ...] = ("pre_call",)

    def __init__(self) -> None:
        """Start with no firings."""
        self.calls: list[int] = []

    def apply(self, payload: Any, spec: FaultSpec, ctx: EpisodeContext) -> Any:
        """Record the firing.

        Args:
            payload: The payload handed over.
            spec: The scheduled fault.
            ctx: The episode context.

        Returns:
            The payload unchanged.
        """
        self.calls.append(ctx.current_call_index.get("get_forecast", 0))
        return payload


class PostFault(RecordingFault):
    """The same recording fake, wired to the post_call hook."""

    id = "T02"
    hooks = ("post_call",)


class ListFault(RecordingFault):
    """The same recording fake, wired to the list hook."""

    id = "T03"
    hooks = ("list",)


class NeverApplicable(RecordingFault):
    """The same recording fake, which refuses every context."""

    id = "T04"

    def applicable(self, ctx: EpisodeContext) -> bool:
        """Refuse every context.

        Args:
            ctx: The episode context.

        Returns:
            ``False``.
        """
        return False


def _parse(payload: dict[str, Any]) -> Message:
    """Parse a JSON-RPC object.

    Args:
        payload: The message object.

    Returns:
        The parsed message.
    """
    message = parse_line(json.dumps(payload).encode())
    assert isinstance(message, (Request, Response))
    return message


def _call(id_: int, tool: str = "get_forecast") -> Request:
    """Build a tools/call request.

    Args:
        id_: The request id.
        tool: The tool name.

    Returns:
        The request.
    """
    message = _parse(
        {"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": {"name": tool}}
    )
    assert isinstance(message, Request)
    return message


def _ctx(seed: int = 1) -> EpisodeContext:
    """Build an episode context with the test scenario.

    Args:
        seed: The run seed.

    Returns:
        The context.
    """
    return EpisodeContext(episode_id="run:scenario:X:1", seed=seed, era=ERA, scenario=SCENARIO)


def engine_for(
    fault_ids: tuple[str, ...], **spec_fields: Any
) -> tuple[FaultEngine, EpisodeContext]:
    """Build an engine with one spec per fault id, bound to a fresh context.

    The fault classes are instantiated here, after the registry fixture ran.

    Args:
        fault_ids: The registered ids to schedule.
        spec_fields: Extra ``FaultSpec`` fields, applied to every spec.

    Returns:
        The engine and its bound context.
    """
    specs = [
        FaultSpec(
            fault_id=fault_id,
            tool=str(spec_fields.get("tool", "$primary")),
            call_index=spec_fields.get("call_index", "all"),  # type: ignore[arg-type]
            probability=float(spec_fields.get("probability", 1.0)),
            persistence=str(spec_fields.get("persistence", "permanent")),
        )
        for fault_id in fault_ids
    ]
    engine = FaultEngine(specs, scenario=SCENARIO)
    ctx = _ctx()
    engine.bind(ctx)
    return engine, ctx


def _recorder(engine: FaultEngine, fault_id: str) -> RecordingFault:
    """Return the recorded fake behind a scheduled fault.

    Args:
        engine: The engine.
        fault_id: The fault id.

    Returns:
        The fake fault.
    """
    for planned in engine.planned:
        if planned.spec.fault_id == fault_id:
            fault = planned.fault
            assert isinstance(fault, RecordingFault)
            return fault
    raise AssertionError(f"{fault_id} is not planned")


@pytest.fixture(autouse=True)
def _fakes() -> Any:
    """Register the fake faults for the duration of one test.

    Yields:
        Nothing.
    """
    for fault_cls in (RecordingFault, PostFault, ListFault, NeverApplicable):
        register(fault_cls)
    yield
    for fault_id in ("T01", "T02", "T03", "T04"):
        REGISTRY.pop(fault_id, None)


def test_registry_register_and_get() -> None:
    """register adds a class and get_fault finds it; unknown ids return None."""
    assert get_fault("T01") is RecordingFault
    assert get_fault("T02") is PostFault
    assert get_fault("ZZZ") is None


@pytest.mark.asyncio
async def test_unregistered_spec_forwards_and_counts() -> None:
    """A spec whose id has no class keeps forwarding and still counts attempts."""
    engine, ctx = engine_for(("ZZZ",))
    pipeline = new_pipeline(fault=engine)
    call = _call(1)
    assert await pipeline.on_c2s(call, ctx) == [Forward(call)]
    assert ctx.pending[(C2S, 1)].attempt == 1
    assert engine.planned[0].fault is None


@pytest.mark.asyncio
async def test_no_registered_faults_forwards_unchanged() -> None:
    """An empty engine forwards every message unchanged."""
    engine = FaultEngine()
    ctx = _ctx()
    pipeline = new_pipeline(fault=engine)
    call = _call(1)
    assert await pipeline.on_c2s(call, ctx) == [Forward(call)]
    response = _parse({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert await pipeline.on_s2c(response, ctx) == [Forward(response)]


@pytest.mark.asyncio
async def test_pre_call_fault_sees_call_index() -> None:
    """A pre_call fault fires first on the attempt its schedule names, then persists."""
    engine, ctx = engine_for(("T01",), call_index=(2,))
    pipeline = new_pipeline(fault=engine)
    for id_ in (1, 2, 3):
        await pipeline.on_c2s(_call(id_), ctx)
    assert _recorder(engine, "T01").calls == [2, 3]


@pytest.mark.asyncio
async def test_post_call_fault_fires_on_the_matching_response() -> None:
    """A post_call fault runs when the response arrives and sees the same index."""
    engine, ctx = engine_for(("T02",))
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_call(7), ctx)
    await pipeline.on_s2c(_parse({"jsonrpc": "2.0", "id": 7, "result": {"content": []}}), ctx)
    assert _recorder(engine, "T02").calls == [1]


@pytest.mark.asyncio
async def test_list_fault_runs_on_tools_list_response() -> None:
    """A list fault runs on the tools/list response, with attempt 0."""
    engine, ctx = engine_for(("T03",))
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_parse({"jsonrpc": "2.0", "id": 4, "method": "tools/list"}), ctx)
    await pipeline.on_s2c(_parse({"jsonrpc": "2.0", "id": 4, "result": {"tools": []}}), ctx)
    assert _recorder(engine, "T03").calls == [0]


@pytest.mark.asyncio
async def test_tool_target_filter() -> None:
    """A fault only fires for the tools its target resolves to."""
    engine, ctx = engine_for(("T01",), call_index=1)
    pipeline = new_pipeline(fault=engine)
    await pipeline.on_c2s(_call(1, "other_tool"), ctx)
    await pipeline.on_c2s(_call(2, "get_forecast"), ctx)
    assert _recorder(engine, "T01").calls == [1]


@pytest.mark.asyncio
async def test_hook_mismatch_never_fires() -> None:
    """A pre_call fault ignores the response hook and vice versa."""
    pre, ctx = engine_for(("T01",), call_index=1)
    post, _ = engine_for(("T02",), call_index=1)
    pipeline = new_pipeline(fault=pre)
    await pipeline.on_c2s(_call(1), ctx)
    await pipeline.on_s2c(_parse({"jsonrpc": "2.0", "id": 1, "result": {}}), ctx)
    assert _recorder(pre, "T01").calls == [1]
    assert _recorder(post, "T02").calls == []


@pytest.mark.asyncio
async def test_not_applicable_fault_does_not_fire() -> None:
    """applicable(ctx) false keeps the fault silent."""
    engine, ctx = engine_for(("T04",), call_index=1)
    await new_pipeline(fault=engine).on_c2s(_call(1), ctx)
    assert _recorder(engine, "T04").calls == []


def test_bind_uses_the_episode_seed() -> None:
    """Two episodes with different seeds get different RNG streams."""
    engine, _ = engine_for(("T01",), probability=0.5)
    engine.bind(_ctx(seed=1))
    first = engine.planned[0].schedule.rng.random()
    engine.bind(_ctx(seed=2))
    second = engine.planned[0].schedule.rng.random()
    assert first != second


def test_bind_uses_the_resolved_target_tool() -> None:
    """The RNG key uses the resolved tool, not the ``$primary`` expression."""
    from skeptic_agent.faults.schedule import fault_rng

    engine, _ = engine_for(("T01",))
    ctx = _ctx()
    engine.bind(ctx)
    bound = [engine.planned[0].schedule.rng.random() for _ in range(3)]
    resolved = fault_rng(ctx.seed, ctx.episode_id, "T01", "get_forecast")
    expression = fault_rng(ctx.seed, ctx.episode_id, "T01", "$primary")
    assert bound == [resolved.random() for _ in range(3)]
    assert bound != [expression.random() for _ in range(3)]


def test_bind_keys_multi_tool_targets_per_actual_tool() -> None:
    """A multi-tool target seeds on the tool of the call, not patterns[0] (S7.3)."""
    from skeptic_agent.faults.schedule import fault_rng

    engine, _ = engine_for(("T01",), tool="*")
    first = _ctx()
    first.current_call_index["other_tool"] = 1
    engine.bind(first)
    actual = fault_rng(first.seed, first.episode_id, "T01", "other_tool")
    assert [engine.planned[0].schedule.rng.random() for _ in range(3)] == [
        actual.random() for _ in range(3)
    ]
