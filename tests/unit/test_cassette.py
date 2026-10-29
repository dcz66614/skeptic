"""Unit tests for the cassette recorder and the redaction rules (S5, 1.7, P15)."""

import asyncio
import hashlib
import json
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.engine import FaultEngine
from skeptic_agent.jsonrpc import Message, Notification, Request, Response, parse_line
from skeptic_agent.protocol import UNKNOWN, Era, detect_era
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import Forward, new_pipeline
from skeptic_agent.record.cassette import (
    SCHEMA_ID,
    CassetteRecorder,
    Recorder,
    cassette_file_name,
    cassette_header,
    cassette_path,
    fault_plan_entry,
    is_internal,
    message_id,
    message_payload,
    utc_now,
)
from skeptic_agent.record.redact import REDACTED, redact

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "cassette.schema.json"
EPISODE_ID = "20261105-142233-a1b2c3:weather.forecast.max-temp.001:S04:1"
ERA = Era(kind="MODERN", version="2026-07-28")


def _validator() -> Draft202012Validator:
    """Build the cassette validator with the S5 format checker.

    Returns:
        A Draft 2020-12 validator for ``schemas/cassette.schema.json``.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _parse(payload: dict[str, Any]) -> Message:
    """Parse a JSON-RPC object into a message carrying its bytes.

    Args:
        payload: The JSON-RPC object.

    Returns:
        The parsed message.
    """
    message = parse_line(json.dumps(payload).encode("utf-8"))
    assert not isinstance(message, Exception)
    assert isinstance(message, Request | Notification | Response)
    return message


def _call(**params: Any) -> Request:
    """Build a ``tools/call`` request with the given arguments.

    Args:
        params: Extra ``arguments`` members.

    Returns:
        The request.
    """
    message = _parse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_forecast", "arguments": {"city": "Paris", **params}},
        }
    )
    assert isinstance(message, Request)
    return message


def _ctx() -> EpisodeContext:
    """Build an episode context matching ``EPISODE_ID``.

    Returns:
        The context.
    """
    return EpisodeContext(episode_id=EPISODE_ID, seed=1, era=ERA)


def _records(path: Path) -> list[dict[str, Any]]:
    """Read every JSON line of a cassette.

    Args:
        path: The cassette file.

    Returns:
        The decoded records.
    """
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _recorder(tmp_path: Path, **overrides: Any) -> Recorder:
    """Open a recorder in ``tmp_path`` with the standard test episode.

    Args:
        tmp_path: The record directory.
        overrides: Extra ``Recorder.open`` keyword arguments.

    Returns:
        The open recorder.
    """
    options: dict[str, Any] = {
        "episode_id": EPISODE_ID,
        "transport": "stdio",
        "upstream": ["python", "-m", "skeptic_agent.sandboxes.sb_weather"],
        "era": ERA,
        "seed": 1,
        "profile": "silent-core",
        "guards": ["schema_guard"],
        "scenario_id": "weather.forecast.max-temp.001",
    }
    options.update(overrides)
    return Recorder.open(tmp_path, **options)


def _header(**overrides: Any) -> dict[str, Any]:
    """Build a header with the standard test episode.

    Args:
        overrides: Extra ``cassette_header`` keyword arguments.

    Returns:
        The header object.
    """
    options: dict[str, Any] = {
        "episode_id": EPISODE_ID,
        "created_at": "2026-11-05T14:22:33Z",
        "transport": "stdio",
        "upstream": ["python", "-m", "skeptic_agent.sandboxes.sb_weather"],
        "era": ERA,
        "seed": 1,
        "profile": "silent-core",
        "scenario_id": "weather.forecast.max-temp.001",
    }
    options.update(overrides)
    return cassette_header(**options)


def test_file_name_replaces_the_episode_colons() -> None:
    """S5 names the file after the episode id with ``:`` replaced by ``__``."""
    assert cassette_file_name(EPISODE_ID) == (
        "20261105-142233-a1b2c3__weather.forecast.max-temp.001__S04__1.jsonl"
    )
    assert cassette_path(Path("runs"), EPISODE_ID) == Path(
        "runs/20261105-142233-a1b2c3__weather.forecast.max-temp.001__S04__1.jsonl"
    )


def test_header_validates_and_carries_the_s5_fields() -> None:
    """The header is exactly the S5 object and validates on its own."""
    header = _header()
    _validator().validate(header)
    assert header["schema"] == SCHEMA_ID
    assert header["skeptic_version"] == "0.0.0"
    assert header["era"] == "2026-07-28"
    assert header["upstream"] == {"command": ["python", "-m", "skeptic_agent.sandboxes.sb_weather"]}
    assert header["fault_plan"] == []
    assert list(header) == [
        "type",
        "schema",
        "episode_id",
        "created_at",
        "skeptic_version",
        "transport",
        "upstream",
        "era",
        "seed",
        "profile",
        "fault_plan",
        "guards",
        "scenario_id",
    ]


def test_header_records_the_unknown_era_and_a_http_upstream() -> None:
    """S4.2 writes ``unknown`` for an undetected era; HTTP keeps only the URL."""
    header = _header(
        era=UNKNOWN,
        transport="http",
        upstream="http://127.0.0.1:9000/mcp",
    )
    _validator().validate(header)
    assert header["era"] == "unknown"
    assert header["upstream"] == {"url": "http://127.0.0.1:9000/mcp"}
    assert header["scenario_id"] == "weather.forecast.max-temp.001"


def test_fault_plan_entry_keeps_only_the_set_persistence_fields() -> None:
    """S5's fault plan carries the S7.1 fields that were configured."""

    def spec(**overrides: Any) -> FaultSpec:
        """Build one scheduled fault.

        Args:
            overrides: ``FaultSpec`` field overrides.

        Returns:
            The fault.
        """
        fields: dict[str, Any] = {
            "fault_id": "S04",
            "tool": "get_forecast",
            "call_index": 2,
            "probability": 1.0,
            "persistence": "permanent",
        }
        fields.update(overrides)
        return FaultSpec(**fields)

    assert fault_plan_entry(spec()) == {
        "id": "S04",
        "target": {"tool": "get_forecast"},
        "when": {"call_index": 2},
        "persistence": {"mode": "permanent"},
    }
    mixed = fault_plan_entry(
        spec(
            fault_id="L01",
            call_index=(1, 2),
            probability=0.5,
            persistence="mixed",
            n=3,
            p=0.25,
            permanent_p=0.7,
            params={"hold_ms": 10},
        )
    )
    assert mixed["when"] == {"call_index": [1, 2], "probability": 0.5}
    assert mixed["persistence"] == {"mode": "mixed", "n": 3, "p": 0.25, "permanent_p": 0.7}
    assert mixed["params"] == {"hold_ms": 10}
    transient = fault_plan_entry(spec(persistence="transient"))
    assert transient["persistence"] == {"mode": "transient", "n": 1}
    intermittent = fault_plan_entry(spec(persistence="intermittent"))
    assert intermittent["persistence"] == {"mode": "intermittent", "p": 0.5}
    all_calls = fault_plan_entry(spec(call_index="all"))
    assert all_calls["when"] == {"call_index": "all"}


def test_header_with_a_fault_plan_validates() -> None:
    """A plan built from ``FaultSpec`` values passes the schema."""
    spec = FaultSpec(
        fault_id="S04",
        tool="get_forecast",
        call_index=1,
        probability=1.0,
        persistence="permanent",
        params={"factor": 10},
    )
    header = _header(fault_plan=[spec], guards=["schema_guard"])
    _validator().validate(header)
    assert header["fault_plan"] == [
        {
            "id": "S04",
            "target": {"tool": "get_forecast"},
            "when": {"call_index": 1},
            "persistence": {"mode": "permanent"},
            "params": {"factor": 10},
        }
    ]


def test_message_payload_decodes_the_received_bytes() -> None:
    """``raw`` is the object the client actually sent."""
    message = _call()
    assert message_payload(message) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_forecast", "arguments": {"city": "Paris"}},
    }


def test_message_payload_rebuilds_a_message_without_bytes() -> None:
    """A message a fault rebuilt has no bytes, so its fields are the payload."""
    rebuilt = Response(id=1, result={"content": []})
    assert message_payload(rebuilt) == {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}


def test_message_ids_and_internal_flag() -> None:
    """Notifications have no id; only the proxy's ``skeptic-`` ids are internal."""
    notification = Notification(method="notifications/initialized")
    assert message_id(notification) is None
    assert not is_internal(notification)
    assert message_id(_call()) == 1
    assert not is_internal(_call())
    internal = _parse({"jsonrpc": "2.0", "id": "skeptic-abc", "method": "tools/list"})
    assert is_internal(internal)
    response = _parse({"jsonrpc": "2.0", "id": "skeptic-abc", "result": {}})
    assert is_internal(response)


def test_utc_now_is_second_precision() -> None:
    """S5 shows ``YYYY-MM-DDTHH:MM:SSZ``; the format checker accepts ours."""
    now = utc_now()
    assert now.endswith("Z")
    assert len(now) == 20


def test_header_and_footer_are_written_and_validated(tmp_path: Path) -> None:
    """An empty episode still has a header, a footer and a valid file."""
    recorder = _recorder(tmp_path)
    recorder.finish()
    assert recorder.finished
    records = _records(recorder.path)
    assert [record["type"] for record in records] == ["header", "footer"]
    validator = _validator()
    for record in records:
        validator.validate(record)
    assert records[1]["stats"] == {
        "messages": 0,
        "tool_calls": 0,
        "faults_applied": 0,
        "guard_actions": 0,
    }


def test_finish_is_idempotent(tmp_path: Path) -> None:
    """Leaving the context after ``finish`` writes no second footer."""
    recorder = _recorder(tmp_path)
    recorder.finish()
    recorder.finish()
    records = _records(recorder.path)
    assert [record["type"] for record in records].count("footer") == 1


def test_with_block_writes_the_footer(tmp_path: Path) -> None:
    """The recorder writes its footer when the block is left."""
    with _recorder(tmp_path) as recorder:
        recorder.record(direction="c2s", msg=_call())
    assert _records(recorder.path)[-1]["type"] == "footer"


def test_record_writes_the_s5_msg_fields(tmp_path: Path) -> None:
    """A ``msg`` line has exactly the S5 fields and the running counters."""
    recorder = _recorder(tmp_path)
    record = recorder.record(
        direction="s2c",
        msg=_call(),
        fault={"id": "S04", "params": {"factor": 10}, "call_index": 1},
        guards=[{"id": "schema_guard", "action": "loudify", "detail": "$.max_c"}],
    )
    recorder.finish()
    lines = _records(recorder.path)
    assert record["seq"] == 0
    assert record["dir"] == "s2c"
    assert record["fault"] == {"id": "S04", "params": {"factor": 10}, "call_index": 1}
    assert record["guards"] == [{"id": "schema_guard", "action": "loudify", "detail": "$.max_c"}]
    assert record["final"] is None
    assert record["dropped"] is False
    assert record["internal"] is False
    assert isinstance(record["t_ms"], int)
    assert lines[1] == record
    for line in lines:
        _validator().validate(line)
    assert lines[-1]["stats"] == {
        "messages": 1,
        "tool_calls": 1,
        "faults_applied": 1,
        "guard_actions": 1,
    }


def test_record_counts_only_forwarded_tool_calls(tmp_path: Path) -> None:
    """``tools/call`` counts; the proxy's own calls do not."""
    recorder = _recorder(tmp_path)
    recorder.record(direction="c2s", msg=_call())
    recorder.record(
        direction="c2s",
        msg=_parse({"jsonrpc": "2.0", "id": "skeptic-1", "method": "tools/call"}),
    )
    recorder.record(direction="c2s", msg=Notification(method="notifications/initialized"))
    assert recorder.stats()["messages"] == 3
    assert recorder.stats()["tool_calls"] == 1


def test_record_redacts_raw_and_final(tmp_path: Path) -> None:
    """S5 applies the 1.7 rules to ``raw`` and ``final`` alike."""
    recorder = _recorder(tmp_path)
    request = _call(api_key="sk-live-123", token="abc")
    response = Response(
        id=1,
        result={"content": [{"type": "text", "text": "ok"}], "password": "hunter2"},
    )
    recorder.record(direction="c2s", msg=request)
    recorder.record(direction="s2c", msg=response, final=response)
    records = _records(recorder.path)
    assert records[1]["raw"]["params"]["arguments"]["api_key"] == REDACTED
    assert records[1]["raw"]["params"]["arguments"]["token"] == REDACTED
    assert records[2]["final"]["result"]["password"] == REDACTED
    assert records[2]["final"]["result"]["content"][0]["text"] == "ok"
    for record in records:
        _validator().validate(record)


def test_redact_headers_and_secret_keys() -> None:
    """1.7 redacts ``Authorization``, ``Cookie`` and secret-looking keys."""
    headers = {
        "Authorization": "Bearer sk-123",
        "authorization": "Bearer lower",
        "Cookie": "session=abc",
        "Cookie2": "other=1",
        "Accept": "application/json",
    }
    payload = {
        "headers": headers,
        "arguments": {
            "api_key": "sk-1",
            "api-key": "sk-2",
            "API_KEY": "sk-3",
            "apikey": "sk-4",
            "token": "t",
            "secret": "s",
            "password": "p",
            "city": "Paris",
        },
    }
    redacted = redact(payload)
    assert redacted["headers"]["Authorization"] == REDACTED
    assert redacted["headers"]["authorization"] == REDACTED
    assert redacted["headers"]["Cookie"] == REDACTED
    assert redacted["headers"]["Cookie2"] == "other=1"
    assert redacted["headers"]["Accept"] == "application/json"
    for key in ("api_key", "api-key", "API_KEY", "apikey", "token", "secret", "password"):
        assert redacted["arguments"][key] == REDACTED
    assert redacted["arguments"]["city"] == "Paris"


def test_redact_recurses_and_keeps_the_input() -> None:
    """Nested arrays and objects are redacted; the original object is untouched."""
    payload = {
        "items": [{"access_token": "a"}, {"status": "ok"}],
        "meta": {"_meta": {"secret": "s"}},
    }
    redacted = redact(payload)
    assert redacted["items"][0]["access_token"] == REDACTED
    assert redacted["items"][1]["status"] == "ok"
    assert redacted["meta"]["_meta"]["secret"] == REDACTED
    assert payload["items"][0]["access_token"] == "a"


def test_redact_leaves_scalars_and_lists_alone() -> None:
    """A scalar passes through, a plain list is copied with its values intact."""
    assert redact("plain") == "plain"
    assert redact(7) == 7
    assert redact(None) is None
    assert redact(["a", {"token": "t"}]) == ["a", {"token": REDACTED}]


@pytest.mark.asyncio
async def test_stage_records_both_directions_and_forward(tmp_path: Path) -> None:
    """The recorder stage writes one line per direction and never rewrites."""
    recorder = _recorder(tmp_path)
    stage = CassetteRecorder(recorder)
    ctx = _ctx()
    c2s = _call()
    s2c = _parse({"jsonrpc": "2.0", "id": 1, "result": {"content": []}})
    assert await stage.on_c2s(c2s, ctx) == [Forward(c2s)]
    assert await stage.on_s2c(s2c, ctx) == [Forward(s2c)]
    recorder.finish()
    records = _records(recorder.path)
    assert [(record["type"], record.get("dir")) for record in records[1:-1]] == [
        ("msg", "c2s"),
        ("msg", "s2c"),
    ]
    assert records[1]["final"] is None
    assert records[2]["final"] is None


@pytest.mark.asyncio
async def test_stage_records_notes_and_the_rewritten_final(tmp_path: Path) -> None:
    """A fault note and a rebuilt message become ``fault`` and ``final``."""
    recorder = _recorder(tmp_path)
    stage = CassetteRecorder(recorder)
    stage.note_fault({"id": "S04", "params": {"factor": 10}, "call_index": 1})
    stage.note_guard({"id": "schema_guard", "action": "loudify"})
    rebuilt = Response(id=1, result={"content": [{"type": "text", "text": "x"}]})
    await stage.on_s2c(rebuilt, _ctx())
    recorder.finish()
    line = _records(recorder.path)[1]
    assert line["fault"] == {"id": "S04", "params": {"factor": 10}, "call_index": 1}
    assert line["guards"] == [{"id": "schema_guard", "action": "loudify"}]
    assert line["final"] == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": "x"}]},
    }
    _validator().validate(line)


@pytest.mark.asyncio
async def test_pipeline_episode_cassette_validates(tmp_path: Path) -> None:
    """A real pipeline run with an L03 fault produces a valid cassette."""
    recorder = _recorder(tmp_path, profile="loud-core")
    stage = CassetteRecorder(recorder)
    engine = FaultEngine(
        [
            FaultSpec(
                fault_id="L03",
                tool="get_forecast",
                call_index="all",
                probability=1.0,
                persistence="permanent",
            )
        ]
    )
    pipeline = new_pipeline(fault=engine, recorder=stage)
    ctx = _ctx()
    request = _parse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_forecast", "arguments": {"city": "Paris"}},
        }
    )
    response = _parse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "sunny"}],
                "structuredContent": {"c": 20},
            },
        }
    )
    await pipeline.on_c2s(request, ctx)
    stage.note_fault({"id": "L03", "params": {}, "call_index": 1})
    final = await pipeline.on_s2c(response, ctx)
    recorder.finish()
    records = _records(recorder.path)
    validator = _validator()
    for record in records:
        validator.validate(record)
    assert isinstance(final[0], Forward)
    assert final[0].msg != response
    s2c = records[2]
    assert s2c["dir"] == "s2c"
    assert s2c["fault"] == {"id": "L03", "params": {}, "call_index": 1}
    assert s2c["final"] is not None
    assert s2c["final"]["result"]["isError"] is True
    assert s2c["raw"]["result"].get("isError", True)
    assert records[-1]["stats"]["faults_applied"] == 1
    assert records[-1]["stats"]["tool_calls"] == 1


def test_cassette_is_redacted_end_to_end(tmp_path: Path) -> None:
    """The file on disk never holds an ``Authorization`` or an ``api_key`` value."""
    recorder = _recorder(tmp_path)
    request = _parse(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_forecast",
                "arguments": {"api_key": "sk-secret-value"},
                "headers": {"Authorization": "Bearer sk-secret-value"},
            },
        }
    )
    recorder.record(direction="c2s", msg=request)
    recorder.finish()
    text = recorder.path.read_text(encoding="utf-8")
    assert "sk-secret-value" not in text
    assert text.count(REDACTED) == 2


def test_atexit_writes_the_missing_footer(tmp_path: Path) -> None:
    """A recorder that never calls ``finish`` still writes its footer at exit."""
    child = ROOT / "tests" / "fixtures" / "cassette_child.py"
    subprocess.run([sys.executable, str(child), str(tmp_path)], check=True, cwd=ROOT)
    records = _records(tmp_path / cassette_file_name(EPISODE_ID))
    assert [record["type"] for record in records] == ["header", "msg", "footer"]
    assert records[-1]["stats"]["messages"] == 1


def test_sigterm_lets_the_default_handler_terminate(tmp_path: Path) -> None:
    """SIGTERM writes the footer, then the process still dies by SIGTERM."""
    handler = None
    recorder = _recorder(tmp_path)
    import signal

    installed = signal.getsignal(signal.SIGTERM)
    assert callable(installed)
    handler = installed
    with pytest.raises(SystemExit) as exit_info:
        handler(signal.SIGTERM, None)
    assert exit_info.value.code == 128 + signal.SIGTERM
    records = _records(recorder.path)
    assert records[-1]["type"] == "footer"
    assert recorder.finished


def test_sigint_replays_keyboard_interrupt(tmp_path: Path) -> None:
    """The SIGINT handler keeps Ctrl-C working after the footer is flushed."""
    import signal

    recorder = _recorder(tmp_path)
    handler = signal.getsignal(signal.SIGINT)
    assert callable(handler)
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGINT, None)
    assert _records(recorder.path)[-1]["type"] == "footer"


def test_detected_era_reaches_the_header(tmp_path: Path) -> None:
    """A header built from ``detect_era`` carries the detected version (S4.2)."""
    first = _parse(
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "server/discover",
            "params": {},
        }
    )
    recorder = _recorder(tmp_path, era=detect_era(first))
    recorder.finish()
    assert _records(recorder.path)[0]["era"] == "2026-07-28"


def test_sha256_of_the_cassette_is_stable_for_one_run(tmp_path: Path) -> None:
    """The same records produce the same ``raw`` bytes, redaction included."""
    digests = []
    for _ in range(2):
        directory = tmp_path / str(len(digests))
        recorder = _recorder(directory)
        recorder.record(
            direction="c2s",
            msg=_parse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_forecast", "arguments": {"api_key": "sk-1"}},
                }
            ),
        )
        recorder.finish()
        line = _records(recorder.path)[1]
        digests.append(hashlib.sha256(json.dumps(line["raw"], sort_keys=True).encode()).hexdigest())
    assert digests[0] == digests[1]


def test_run_in_a_thread_keeps_only_the_atexit_hook(tmp_path: Path) -> None:
    """Signal handlers are main-thread only, so the recorder still opens."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        recorder = asyncio.run(asyncio.to_thread(_recorder, Path(directory)))
        recorder.finish()
        assert _records(recorder.path)[-1]["type"] == "footer"


def test_missing_signal_numbers_keep_only_atexit(tmp_path: Path) -> None:
    """A platform without SIGTERM still records; the footer comes from exit (S5)."""
    from skeptic_agent.record import cassette

    previous_names = cassette.SIGNALS
    cassette.SIGNALS = ("SIGTERM", "SIGTHAT_DOES_NOT_EXIST")
    try:
        recorder = _recorder(tmp_path)
    finally:
        cassette.SIGNALS = previous_names
    assert len(recorder._signals) <= 1
    recorder.finish()
    assert _records(recorder.path)[-1]["type"] == "footer"


def test_unsettable_signal_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker thread cannot set signal handlers, so the step is skipped (S5)."""

    def refuse(number: Any, handler: Any) -> None:
        """Raises as ``signal.signal`` does outside the main thread.

        Args:
            number: The signal number.
            handler: The handler to install.
        """
        raise ValueError("signal only works in main thread")

    monkeypatch.setattr(signal, "signal", refuse)
    recorder = _recorder(tmp_path)
    assert recorder._signals == []
    recorder.finish()
    assert _records(recorder.path)[-1]["type"] == "footer"


@pytest.mark.parametrize("previous", [signal.SIG_IGN, lambda received, frame: None])
def test_previous_ignored_or_custom_handlers_win(tmp_path: Path, previous: Any) -> None:
    """An ignored or custom previous handler decides what happens next (S5)."""
    recorder = _recorder(tmp_path)
    handler = recorder._make_handler(signal.SIGTERM, previous)
    handler(signal.SIGTERM, None)
    assert _records(recorder.path)[-1]["type"] == "footer"


def test_payload_falls_back_when_the_bytes_are_not_json() -> None:
    """A message whose bytes do not decode falls back to its fields."""
    message = Request(id=1, method="tools/list").model_copy(update={"raw_bytes": b"not json"})
    assert message_payload(message) == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
    }
