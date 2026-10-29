"""stdio proxy: relay one MCP connection through the pipeline (S2, S4.1).

The client talks to us over stdin/stdout, one JSON-RPC message per line. We start
the upstream server as a child process, run one read loop per direction, and let
the ``Pipeline`` decide what happens to each line. stdout carries protocol
messages and nothing else; upstream stderr goes to our stderr.
"""

import asyncio
import sys
from collections.abc import Sequence
from contextlib import suppress
from typing import Protocol

from skeptic_agent.jsonrpc import Message, Notification, ParseError, Request, dump, parse_line
from skeptic_agent.protocol import UNKNOWN, detect_era
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.pipeline import (
    Action,
    Drop,
    Forward,
    Hold,
    Pipeline,
    ReplyToClient,
    SendToServer,
    cancelled_id,
    new_pipeline,
)

CLOSE_TIMEOUT_SECONDS: float = 5.0
"""How long to wait for the upstream to exit after the client closes stdin."""

START_FAILED: int = 4
"""The S2 exit code for a failed upstream start."""


class _LineSource(Protocol):
    """The client side the proxy reads protocol lines from."""

    async def readline(self) -> bytes:
        """Read one line.

        Returns:
            The line including its terminator, or ``b""`` at EOF.
        """
        ...


class _LineSink(Protocol):
    """The client side the proxy writes protocol lines to."""

    def write(self, data: bytes) -> None:
        """Write bytes without flushing; ``drain`` flushes them.

        Args:
            data: The bytes to write.
        """
        ...

    async def drain(self) -> None:
        """Flush the buffered bytes."""
        ...


class _StdStream:
    """Binary stdin/stdout wrapped so the proxy can write and drain bytes."""

    def __init__(self, stream: "object") -> None:
        """Wrap a binary stream.

        Args:
            stream: ``sys.stdin.buffer`` or ``sys.stdout.buffer``.
        """
        self.stream = stream

    def write(self, data: bytes) -> None:
        """Write bytes without flushing; ``drain`` flushes them.

        Args:
            data: The bytes to write.
        """
        self.stream.write(data)  # type: ignore[attr-defined]

    async def drain(self) -> None:
        """Flush the buffered bytes."""
        self.stream.flush()  # type: ignore[attr-defined]


class _StdReader:
    """Line reader over a blocking binary stream, run in a worker thread."""

    def __init__(self, stream: "object") -> None:
        """Wrap a binary stream.

        Args:
            stream: ``sys.stdin.buffer``.
        """
        self.stream = stream

    async def readline(self) -> bytes:
        """Read one line in a thread so the event loop keeps running.

        Returns:
            The line including its terminator, or ``b""`` at EOF.
        """
        return await asyncio.to_thread(self.stream.readline)  # type: ignore[attr-defined]


class StdioProxy:
    """Relay a client's stdio MCP connection to a child process through the pipeline.

    Attributes:
        ctx: The episode context shared by every stage.
        process: The upstream process once started.
    """

    def __init__(
        self,
        command: Sequence[str],
        pipeline: Pipeline | None = None,
        *,
        episode_id: str = "stdio",
        seed: int = 0,
    ) -> None:
        """Prepare a proxy for one episode.

        Args:
            command: The upstream command and its arguments.
            pipeline: The pipeline to use, or ``None`` for one with no-op stages.
            episode_id: The episode identifier.
            seed: The episode seed.

        Raises:
            ValueError: When ``command`` is empty.
        """
        if not command:
            raise ValueError("upstream command must not be empty")
        self.command = list(command)
        self.pipeline = pipeline if pipeline is not None else new_pipeline()
        self.ctx = EpisodeContext(episode_id=episode_id, seed=seed, era=UNKNOWN)
        self.process: asyncio.subprocess.Process | None = None
        self._cancelled: set[int | str] = set()
        """Request ids the client cancelled while their reply was held (L01)."""

    def _write_upstream(self, data: bytes) -> None:
        """Write bytes to the upstream stdin.

        Args:
            data: The bytes to write.

        Raises:
            RuntimeError: When the upstream is not running.
        """
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("upstream is not running")
        self.process.stdin.write(data)

    async def _apply_c2s(self, actions: list[Action], client_out: "_LineSink") -> None:
        """Send the c2s actions to the upstream or answer the client directly.

        Args:
            actions: The pipeline actions.
            client_out: Our stdout, for ``ReplyToClient``.

        Raises:
            RuntimeError: When the upstream is not running.
        """
        for action in actions:
            if isinstance(action, Hold):
                await asyncio.sleep(action.ms / 1000)
                action = action.then
            if isinstance(action, (Forward, SendToServer)):
                self._write_upstream(dump(action.msg))
                if self.process is not None and self.process.stdin is not None:
                    await self.process.stdin.drain()
            elif isinstance(action, ReplyToClient):
                client_out.write(dump(action.msg))
                await client_out.drain()
            # A ReplyWithStatus (L04) has no stdio form; S6 marks L04 not
            # applicable here, and the fault itself refuses a non-HTTP episode.

    async def _wait(self, action: Hold) -> Action:
        """Sleep out a held action, or stop early when its request is cancelled.

        A ``Hold`` with ``unless_cancelled`` set belongs to one request id. When
        the client cancels that request before the delay ends, the follow-up is
        replaced by ``Drop`` so the client gets no reply at all (L01). Every
        other hold sleeps for its full time and keeps its follow-up.

        Args:
            action: The hold to wait out.

        Returns:
            The action to apply after the wait.
        """
        request_id = action.unless_cancelled
        if request_id is None or action.ms <= 0:
            await asyncio.sleep(action.ms / 1000)
            return action.then
        loop = asyncio.get_running_loop()
        deadline = loop.time() + action.ms / 1000
        while request_id not in self._cancelled:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return action.then
            await asyncio.sleep(remaining)
        return Drop()

    async def _apply_s2c(self, actions: list[Action], client_out: "_LineSink") -> None:
        """Send the s2c actions to the client or back to the upstream.

        Args:
            actions: The pipeline actions.
            client_out: Our stdout.

        Raises:
            RuntimeError: When the upstream is not running.
        """
        for action in actions:
            if isinstance(action, Hold):
                action = await self._wait(action)
            if isinstance(action, Forward):
                # S4.1: verbatim when untouched, compact JSON when a fault or a
                # Guard rewrote it (the engine clears ``raw_bytes`` on a rewrite).
                raw = action.msg.raw_bytes
                client_out.write(raw + b"\n" if raw else dump(action.msg))
                await client_out.drain()
            elif isinstance(action, SendToServer):
                self._write_upstream(dump(action.msg))
                if self.process is not None and self.process.stdin is not None:
                    await self.process.stdin.drain()
            elif isinstance(action, ReplyToClient):
                client_out.write(dump(action.msg))
                await client_out.drain()

    def _detect_era(self, msg: Message) -> None:
        """Detect the era from the first valid client message (S4.2).

        Args:
            msg: The first parsed client message.
        """
        if self.ctx.era is not UNKNOWN or not isinstance(msg, (Request, Notification)):
            return
        self.ctx.era = detect_era(msg)

    async def _client_loop(self, client_in: "_LineSource", client_out: "_LineSink") -> None:
        """Read client lines, run them through the pipeline and act on the result.

        Args:
            client_in: Our stdin.
            client_out: Our stdout.
        """
        while True:
            line = await client_in.readline()
            if not line:
                return
            if not line.strip():
                continue
            msg = parse_line(line)
            if isinstance(msg, ParseError):
                self._write_upstream(msg.raw_bytes + b"\n")
                if self.process is not None and self.process.stdin is not None:
                    await self.process.stdin.drain()
                continue
            self._detect_era(msg)
            request_id = cancelled_id(msg)
            if request_id is not None:
                self._cancelled.add(request_id)
            actions = await self.pipeline.on_c2s(msg, self.ctx)
            await self._apply_c2s(actions, client_out)

    async def _upstream_loop(self, client_out: "_LineSink") -> None:
        """Read upstream lines, run them through the pipeline and act on the result.

        Args:
            client_out: Our stdout.

        Raises:
            RuntimeError: When the upstream stdout is missing.
        """
        if self.process is None or self.process.stdout is None:
            raise RuntimeError("upstream stdout is missing")
        while True:
            line = await self.process.stdout.readline()
            if not line:
                return
            if not line.strip():
                continue
            msg = parse_line(line)
            if isinstance(msg, ParseError):
                client_out.write(msg.raw_bytes + b"\n")
                await client_out.drain()
                continue
            actions = await self.pipeline.on_s2c(msg, self.ctx)
            await self._apply_s2c(actions, client_out)

    async def _stderr_loop(self) -> None:
        """Copy the upstream stderr to our stderr.

        Raises:
            RuntimeError: When the upstream stderr is missing.
        """
        if self.process is None or self.process.stderr is None:
            raise RuntimeError("upstream stderr is missing")
        while True:
            chunk = await self.process.stderr.read(65536)
            if not chunk:
                return
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()

    async def _close_upstream(self, exit_task: "asyncio.Task[int]") -> None:
        """Close the upstream stdin, wait, then terminate it (S2/P13).

        Args:
            exit_task: The task awaiting the upstream's exit code.
        """
        if self.process is None:
            return
        with suppress(BrokenPipeError, ConnectionResetError, RuntimeError, OSError):
            if self.process.stdin is not None:
                self.process.stdin.close()
        try:
            await asyncio.wait_for(asyncio.shield(exit_task), CLOSE_TIMEOUT_SECONDS)
        except TimeoutError:
            self.process.terminate()
            await exit_task

    async def run(self) -> int:
        """Run the proxy until the upstream exits.

        On client stdin EOF the upstream stdin is closed, then the upstream is
        given ``CLOSE_TIMEOUT_SECONDS`` to exit before it is terminated.

        Returns:
            The upstream exit code, or ``START_FAILED`` when it cannot be started.
        """
        return await self.serve(
            reader=_StdReader(sys.stdin.buffer), writer=_StdStream(sys.stdout.buffer)
        )

    async def _start(self) -> bool:
        """Start the upstream child process.

        Returns:
            ``True`` when it started, ``False`` when the command cannot run.
        """
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return False
        return True

    async def serve(self, *, reader: "_LineSource", writer: "_LineSink") -> int:
        """Relay one client connection from the given streams.

        ``run`` uses the process stdin and stdout; a test can pass another pair
        that speaks the same two methods.

        Args:
            reader: The client's line source (an async ``readline``).
            writer: The client's line sink (``write`` and async ``drain``).

        Returns:
            The upstream exit code, or ``START_FAILED`` when it cannot be started.
        """
        if not await self._start() or self.process is None:
            return START_FAILED
        process = self.process
        client_in = reader
        client_out = writer

        exit_task: asyncio.Task[int] = asyncio.create_task(process.wait())
        stderr_task = asyncio.create_task(self._stderr_loop())
        upstream_task = asyncio.create_task(self._upstream_loop(client_out))
        client_task = asyncio.create_task(self._client_loop(client_in, client_out))

        done, _ = await asyncio.wait(
            {upstream_task, client_task, exit_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if client_task in done:
            await self._close_upstream(exit_task)
        else:
            await exit_task

        for task in (upstream_task, client_task):
            task.cancel()
        await asyncio.gather(upstream_task, client_task, return_exceptions=True)
        await stderr_task
        code = process.returncode
        return code if code is not None else 0
