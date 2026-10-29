"""Unit tests for the stdio proxy relay (S2, S4.1, P13)."""

import asyncio
import sys

import pytest

from skeptic_agent.jsonrpc import Message, Notification, Request, Response, dump, parse_line
from skeptic_agent.protocol import UNKNOWN
from skeptic_agent.proxy.pipeline import (
    Drop,
    Forward,
    Hold,
    Pipeline,
    RecorderStage,
    ReplyToClient,
    SendToServer,
    new_pipeline,
)
from skeptic_agent.proxy.stdio import CLOSE_TIMEOUT_SECONDS, START_FAILED, StdioProxy

pytestmark = pytest.mark.unit


class _FakeStream:
    """A binary stream that records what was written and flushed."""

    def __init__(self) -> None:
        """Start with no writes and no flushes."""
        self.written: list[bytes] = []
        self.flushes: int = 0

    def write(self, data: bytes) -> None:
        """Record a write.

        Args:
            data: The bytes written.
        """
        self.written.append(data)

    def flush(self) -> None:
        """Count a flush."""
        self.flushes += 1

    async def drain(self) -> None:
        """Flush, like the real output stream."""
        self.flushes += 1

    @property
    def data(self) -> bytes:
        """Return everything written so far.

        Returns:
            The concatenated writes.
        """
        return b"".join(self.written)


def _parse(payload: str) -> Message:
    """Parse one JSON-RPC line.

    Args:
        payload: A JSON-RPC message.

    Returns:
        The parsed message.
    """
    message = parse_line(payload.encode("utf-8"))
    assert isinstance(message, (Request, Notification, Response))
    return message


def _proxy() -> StdioProxy:
    """Build a proxy that never starts its upstream.

    Returns:
        A proxy with an empty pipeline.
    """
    return StdioProxy([sys.executable, "-c", "pass"])


def test_empty_command_is_rejected() -> None:
    """An empty upstream command is a programming error."""
    with pytest.raises(ValueError, match="must not be empty"):
        StdioProxy([])


def test_defaults() -> None:
    """A fresh proxy has no process and an unknown era."""
    proxy = StdioProxy(["python"], episode_id="ep-1", seed=3)
    assert proxy.process is None
    assert proxy.ctx.era is UNKNOWN
    assert proxy.ctx.episode_id == "ep-1"
    assert proxy.ctx.seed == 3
    assert proxy.command == ["python"]


def test_write_upstream_without_process_fails() -> None:
    """Writing before the upstream starts raises instead of being lost."""
    with pytest.raises(RuntimeError, match="not running"):
        _proxy()._write_upstream(b"{}\n")


@pytest.mark.asyncio
async def test_apply_c2s_writes_bytes_and_flushes() -> None:
    """Forward, SendToServer and ReplyToClient all flush the right stream."""
    proxy = _proxy()
    request = _parse('{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
    response = _parse('{"jsonrpc":"2.0","id":1,"result":{}}')
    client_out = _FakeStream()

    writes: list[bytes] = []

    class _Stdin:
        def write(self, data: bytes) -> None:
            writes.append(data)

        async def drain(self) -> None:
            writes.append(b"<drained>")

    proxy.process = type("P", (), {"stdin": _Stdin()})()  # type: ignore[assignment]
    await proxy._apply_c2s(
        [Forward(request), SendToServer(response), ReplyToClient(response)], client_out
    )

    assert writes[:3] == [dump(request), b"<drained>", dump(response)]
    assert client_out.data == dump(response)
    assert client_out.flushes == 1


@pytest.mark.asyncio
async def test_apply_c2s_hold_then_forward() -> None:
    """Hold sleeps and then applies the wrapped action."""
    proxy = _proxy()
    notification = _parse('{"jsonrpc":"2.0","method":"notifications/initialized"}')
    writes: list[bytes] = []

    class _Stdin:
        def write(self, data: bytes) -> None:
            writes.append(data)

        async def drain(self) -> None:
            pass

    proxy.process = type("P", (), {"stdin": _Stdin()})()  # type: ignore[assignment]
    await proxy._apply_c2s([Hold(ms=1, then=Forward(notification))], _FakeStream())
    assert writes == [dump(notification)]


@pytest.mark.asyncio
async def test_apply_c2s_hold_then_reply() -> None:
    """Hold may wrap a direct client reply."""
    proxy = _proxy()
    response = _parse('{"jsonrpc":"2.0","id":1,"result":{}}')
    client_out = _FakeStream()
    await proxy._apply_c2s([Hold(ms=1, then=ReplyToClient(response))], client_out)
    assert client_out.data == dump(response)


@pytest.mark.asyncio
async def test_apply_c2s_drop_writes_nothing() -> None:
    """A dropped message never reaches the upstream or the client."""
    proxy = _proxy()
    client_out = _FakeStream()
    await proxy._apply_c2s([Drop()], client_out)
    assert client_out.data == b""


@pytest.mark.asyncio
async def test_apply_s2c_forward_is_verbatim() -> None:
    """A forwarded s2c message keeps its original bytes."""
    proxy = _proxy()
    line = b'{"jsonrpc":"2.0","id":1,"result":{ }}'
    response = parse_line(line)
    assert isinstance(response, Response)
    client_out = _FakeStream()
    await proxy._apply_s2c([Forward(response)], client_out)
    assert client_out.data == line + b"\n"


@pytest.mark.asyncio
async def test_apply_s2c_send_to_server_and_reply() -> None:
    """SendToServer goes upstream while ReplyToClient goes to the client."""
    proxy = _proxy()
    request = _parse('{"jsonrpc":"2.0","id":"skeptic-1","method":"tools/call"}')
    response = _parse('{"jsonrpc":"2.0","id":2,"result":{}}')
    writes: list[bytes] = []

    class _Stdin:
        def write(self, data: bytes) -> None:
            writes.append(data)

        async def drain(self) -> None:
            pass

    proxy.process = type("P", (), {"stdin": _Stdin()})()  # type: ignore[assignment]
    client_out = _FakeStream()
    await proxy._apply_s2c([SendToServer(request), ReplyToClient(response)], client_out)
    assert writes == [dump(request)]
    assert client_out.data == dump(response)


@pytest.mark.asyncio
async def test_apply_s2c_hold_then_reply() -> None:
    """Hold delays an s2c reply."""
    proxy = _proxy()
    response = _parse('{"jsonrpc":"2.0","id":1,"result":{}}')
    client_out = _FakeStream()
    await proxy._apply_s2c([Hold(ms=1, then=ReplyToClient(response))], client_out)
    assert client_out.data == dump(response)


def test_detect_era_from_first_request() -> None:
    """The first request fixes the era and later messages do not change it."""
    proxy = _proxy()
    legacy = _parse(
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}'
    )
    modern = _parse(
        '{"jsonrpc":"2.0","id":2,"method":"tools/call",'
        '"params":{"name":"echo","_meta":{"io.modelcontextprotocol/protocol-version":"2026-07-28"}}}'
    )
    proxy._detect_era(legacy)
    assert proxy.ctx.era.version == "2025-11-25"
    proxy._detect_era(modern)
    assert proxy.ctx.era.version == "2025-11-25"


def test_detect_era_ignores_response() -> None:
    """A response is not a client message, so the era stays unknown."""
    proxy = _proxy()
    proxy._detect_era(_parse('{"jsonrpc":"2.0","id":1,"result":{}}'))
    assert proxy.ctx.era is UNKNOWN


class _EchoStage(RecorderStage):
    """Forward every message unchanged while remembering the era it saw."""

    def __init__(self) -> None:
        """Start with no recorded eras."""
        self.eras: list[object] = []

    async def on_c2s(self, msg: Message, ctx: object) -> list[object]:  # type: ignore[override]
        """Record the era and forward.

        Args:
            msg: The client message.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        self.eras.append(getattr(ctx, "era", None))
        return [Forward(msg)]


@pytest.mark.asyncio
async def test_client_loop_forwards_and_skips_blank_lines() -> None:
    """Blank lines are ignored, parse errors go upstream and messages relay."""
    proxy = _proxy()
    stage = _EchoStage()
    proxy.pipeline = Pipeline(new_pipeline().fault, new_pipeline().guard, stage)
    proxy.process = type("P", (), {"stdin": _StdinWriter()})()  # type: ignore[assignment]

    lines = [
        b"\n",
        b"{not json}\n",
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        b"",
    ]

    class _Reader:
        async def readline(self) -> bytes:
            return lines.pop(0)

    client_out = _FakeStream()
    await proxy._client_loop(_Reader(), client_out)  # type: ignore[arg-type]

    stdin = proxy.process.stdin  # type: ignore[attr-defined]
    initialize = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
    assert stdin.written[-1] == initialize
    assert b"{not json}\n" in stdin.written
    assert stage.eras
    assert client_out.data == b""


class _StdinWriter:
    """A writable fake upstream stdin."""

    def __init__(self) -> None:
        """Start with no writes."""
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        """Record a write.

        Args:
            data: The bytes written.
        """
        self.written.append(data)

    async def drain(self) -> None:
        """Do nothing; the writes are already synchronous."""


@pytest.mark.asyncio
async def test_upstream_loop_relays_to_client() -> None:
    """Upstream lines reach the client and parse errors pass through raw."""
    proxy = _proxy()

    lines = [b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n', b"garbage\n", b""]

    class _Out:
        def __init__(self) -> None:
            self.lines: list[bytes] = []

        async def readline(self) -> bytes:
            return lines.pop(0)

    class _Proc:
        stdout = _Out()

    proxy.process = _Proc()  # type: ignore[assignment]
    client_out = _FakeStream()
    await proxy._upstream_loop(client_out)
    assert client_out.data == b'{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n' + b"garbage\n"
    assert client_out.flushes == 2


@pytest.mark.asyncio
async def test_upstream_loop_without_stdout_fails() -> None:
    """A missing upstream stdout is a hard error."""
    proxy = _proxy()
    proxy.process = type("P", (), {"stdout": None})()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="stdout is missing"):
        await proxy._upstream_loop(_FakeStream())


@pytest.mark.asyncio
async def test_stderr_loop_without_stderr_fails() -> None:
    """A missing upstream stderr is a hard error."""
    proxy = _proxy()
    proxy.process = type("P", (), {"stderr": None})()  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="stderr is missing"):
        await proxy._stderr_loop()


@pytest.mark.asyncio
async def test_close_upstream_without_process_is_noop() -> None:
    """Closing when no upstream was started does nothing."""
    proxy = _proxy()
    await proxy._close_upstream(asyncio.create_task(asyncio.sleep(0, result=0)))


def test_constants() -> None:
    """The S2 constants match the plan."""
    assert CLOSE_TIMEOUT_SECONDS == 5.0
    assert START_FAILED == 4


@pytest.mark.asyncio
async def test_run_propagates_upstream_exit_code() -> None:
    """A child that exits non-zero is reported by ``run``."""
    proxy = StdioProxy([sys.executable, "-c", "import sys; sys.exit(5)"])
    assert await proxy.run() == 5


@pytest.mark.asyncio
async def test_run_reports_start_failure() -> None:
    """An unreachable upstream command returns ``START_FAILED``."""
    proxy = StdioProxy(["skeptic-command-that-does-not-exist"])
    assert await proxy.run() == START_FAILED


@pytest.mark.asyncio
async def test_run_with_closed_stdin_closes_upstream() -> None:
    """When the client stdin is already at EOF the upstream is closed and reaped."""
    code = "import sys\nfor _ in sys.stdin:\n    pass\n"
    proxy = StdioProxy([sys.executable, "-c", code])
    assert await proxy.run() == 0
    assert proxy.process is not None
    assert proxy.process.returncode == 0
