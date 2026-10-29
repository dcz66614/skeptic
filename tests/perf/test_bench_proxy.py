"""Smoke tests for the P17 benchmark harness (marked ``perf``).

The benchmark itself takes minutes: it starts hundreds of short-lived proxy
processes. These tests run the same code on a tiny sample. The whole file is
marked ``perf`` and ``pyproject.toml`` deselects that marker by default, so
``uv run pytest tests/perf -m perf`` is the way to run it; ``--strict-markers``
keeps the marker name honest.
"""

import asyncio
import contextlib
import importlib.util
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.perf

SAMPLE = 5


def _load_bench() -> ModuleType:
    """Import ``bench_proxy.py`` as a plain module.

    The benchmark is a script rather than a library module, and there is no root
    ``conftest.py`` putting the repo root on ``sys.path``, so the file is loaded
    by path.

    Returns:
        The imported ``bench_proxy`` module.
    """
    path = Path(__file__).with_name("bench_proxy.py")
    spec = importlib.util.spec_from_file_location("bench_proxy", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_proxy"] = module
    spec.loader.exec_module(module)
    return module


bench = _load_bench()


def test_percentile_interpolates() -> None:
    """The percentile is the linear interpolation of the sorted samples."""
    samples = [0.001, 0.002, 0.003, 0.004]
    assert bench._percentile(samples, 0.0) == pytest.approx(1.0)
    assert bench._percentile(samples, 1.0) == pytest.approx(4.0)
    assert bench._percentile(samples, 0.5) == pytest.approx(2.5)
    assert bench._percentile(samples, 0.75) == pytest.approx(3.25)
    assert bench._percentile(samples, 0.25) == pytest.approx(1.75)
    assert bench._percentile([], 0.5) == 0.0


def test_summary_reports_milliseconds() -> None:
    """The summary converts seconds to milliseconds and counts the samples."""
    summary = bench._summary([0.001, 0.003])
    assert summary["count"] == 2.0
    assert summary["min"] == pytest.approx(1.0)
    assert summary["max"] == pytest.approx(3.0)
    assert summary["mean"] == pytest.approx(2.0)
    assert summary["p50"] == pytest.approx(2.0)
    assert bench._summary([])["mean"] == 0.0


def test_reply_payload_reads_json_and_event_stream() -> None:
    """A JSON body and an SSE body decode to the same message."""
    message = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "x"}]}}
    assert bench._reply_payload(json.dumps(message)) == message
    assert bench._reply_payload(f"event: message\ndata: {json.dumps(message)}\n\n") == message
    assert bench._first_text_http(json.dumps(message)) == "x"


def test_call_body_carries_the_tool_and_text() -> None:
    """A call body carries the id, the tool and its arguments."""
    body = bench._call_body(7, "hi")
    assert body["id"] == 7
    assert body["params"] == {"name": "echo", "arguments": {"text": "hi"}}


def test_initialize_body_is_a_legacy_handshake() -> None:
    """The handshake names the version the echo fixture can serve."""
    body = bench._initialize_body()
    assert body["method"] == "initialize"
    assert body["params"]["protocolVersion"] == "2025-06-18"
    assert body["params"]["clientInfo"]["name"] == "skeptic-bench"


def test_parse_args_defaults() -> None:
    """The defaults are the P17 run: 5000 samples and 50 clients over 100 calls."""
    args = bench.parse_args([])
    assert args.only == ["stdio", "http", "concurrency"]
    assert (args.count, args.warmup, args.clients, args.calls) == (5000, 3, 50, 100)
    assert args.report is None


def test_stdio_samples_are_finite_and_real() -> None:
    """The stdio benchmark returns one finite difference per sample."""
    samples = asyncio.run(bench.bench_stdio(count=2, warmup=1))
    assert len(samples) == 2
    assert all(abs(value) < 10 for value in samples)


def test_stdio_samples_reuse_one_session_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every sample of one transport runs on the same direct and proxied session."""

    @contextlib.asynccontextmanager
    async def fake_session(command: list[str]) -> AsyncIterator[object]:
        sessions.append(command)
        yield object()

    sessions: list[list[str]] = []
    monkeypatch.setattr(bench, "_session", fake_session)
    monkeypatch.setattr(bench, "_call_and_check", _async_noop)
    samples = asyncio.run(bench.bench_stdio(count=3, warmup=1))
    assert len(samples) == 3
    assert sessions == [bench._echo_stdio(), bench._proxy_stdio()]


async def _async_noop(session: object, text: str) -> None:
    """Stand in for a real echo call.

    Args:
        session: The fake session.
        text: The text the real call would send.
    """
    del session, text


def test_http_samples_are_finite_and_real() -> None:
    """The HTTP benchmark returns one finite difference per sample."""
    samples = asyncio.run(bench.bench_http(count=2, warmup=1))
    assert len(samples) == 2
    assert all(abs(value) < 10 for value in samples)


def test_stdio_concurrency_loses_nothing() -> None:
    """Two concurrent sessions with a few calls each see no errors."""
    result = asyncio.run(bench.bench_stdio_concurrency(clients=2, calls=3))
    assert result == {"sessions": 2, "calls": 6, "errors": 0, "mismatches": 0}


def test_http_concurrency_loses_nothing() -> None:
    """Two concurrent HTTP clients with a few calls each see no errors."""
    result = asyncio.run(bench.bench_http_concurrency(clients=2, calls=3))
    assert result == {"sessions": 2, "calls": 6, "errors": 0, "mismatches": 0}


def test_main_writes_a_report(tmp_path: Path) -> None:
    """``main`` writes the JSON report and ends with the acceptance verdict."""
    report = tmp_path / "perf.json"
    code = bench.main(
        [
            "--only",
            "stdio",
            "http",
            "--count",
            str(SAMPLE),
            "--warmup",
            "1",
            "--report",
            str(report),
        ]
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    assert set(data) >= {"python", "platform", "stdio", "http"}
    assert data["stdio"]["count"] == float(SAMPLE)
    assert data["http"]["count"] == float(SAMPLE)
    assert code in {0, 1}
