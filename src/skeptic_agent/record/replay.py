"""The cassette replayer: serve a recorded cassette back to a client (S2, S5).

A cassette holds one episode. Replay reads it, groups the recorded responses by
the request they answer, keyed by ``(method, tool_name, stable_hash(arguments))``,
and keeps one queue per key in the order the responses crossed the wire. Every
queue is filled with the recorded ``final`` message when one exists and with the
``raw`` one otherwise.

Run as ``skeptic replay``, the replayer is a stdio MCP server: it answers
``initialize``, ``server/discover`` and ``tools/list`` with the recorded reply
and takes each ``tools/call`` from its queue. A request that matches nothing is
answered with a JSON-RPC error under ``--on-miss error`` (the default) or
forwarded to a live upstream command under ``--on-miss live``.
"""

import asyncio
import json
import sys
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skeptic_agent.canonical import stable_hash
from skeptic_agent.jsonrpc import (
    ErrorObject,
    ErrorResponse,
    Message,
    ParseError,
    Request,
    dump,
    parse_line,
)
from skeptic_agent.proxy.pipeline import TOOLS_CALL, TOOLS_LIST
from skeptic_agent.record.cassette import SCHEMA_ID
from skeptic_agent.record.redact import REDACTED

DISCOVER: str = "server/discover"
"""The modern handshake request (S4.2)."""

INITIALIZE: str = "initialize"
"""The legacy handshake request (S4.2)."""

HANDSHAKE_METHODS: frozenset[str] = frozenset({INITIALIZE, DISCOVER})
"""The requests the recorded episode already answered, answered as recorded."""

CACHED_METHODS: frozenset[str] = frozenset({*HANDSHAKE_METHODS, TOOLS_LIST})
"""The requests answered from the single recorded reply of their method."""

ON_MISS_ERROR: str = "error"
"""The S2 default ``--on-miss``: answer a match miss with a JSON-RPC error."""

ON_MISS_LIVE: str = "live"
"""The S2 ``--on-miss live``: send a match miss to the live upstream command."""

ON_MISS_VALUES: tuple[str, ...] = (ON_MISS_ERROR, ON_MISS_LIVE)
"""Every accepted ``--on-miss`` value (S2)."""

MISS_CODE: int = -32602
"""The JSON-RPC error code a match miss is answered with (S2, S6 L06's code)."""

EXIT_USAGE: int = 2
"""The S2 exit code for a usage error."""

EXIT_INVALID: int = 3
"""The S2 exit code for an invalid cassette or a failed live upstream start."""

BACKLOG_LIMIT: int = 1 << 20
"""How many bytes a live upstream's stdio stream may buffer before it blocks."""

LIVE_CLOSE_TIMEOUT_SECONDS: float = 5.0
"""How long a live upstream gets to exit once its stdin is closed (P13)."""


class ReplayError(Exception):
    """A cassette that cannot be replayed."""


def request_key(method: str, tool_name: str | None, arguments: Any) -> str:
    """Build the replay key of a request (P16).

    Args:
        method: The JSON-RPC method.
        tool_name: ``params.name`` for a ``tools/call``, else ``None``.
        arguments: ``params.arguments`` for a ``tools/call``, else ``None``.

    Returns:
        A string that uniquely identifies the key triple.
    """
    return stable_hash([method, tool_name, arguments])


def _request_key(msg: Request) -> str:
    """Build the replay key of a request message (P16).

    Args:
        msg: The request.

    Returns:
        The key of its method, tool name and arguments.
    """
    params = msg.params if isinstance(msg.params, dict) else {}
    name = params.get("name")
    tool = name if isinstance(name, str) else None
    return request_key(msg.method, tool, params.get("arguments"))


def _response_key(raw: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    """Build the replay key of the request a recorded response answers (P16).

    Args:
        raw: The ``tools/call`` record.
        request: The message that record holds (``final`` or ``raw``).

    Returns:
        The replay key of the request.
    """
    tool = (raw.get("fault") or {}).get("target", {}).get("tool")
    if not isinstance(tool, str):
        tool = (request.get("params") or {}).get("name")
    return request_key(TOOLS_CALL, tool, (request.get("params") or {}).get("arguments"))


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the message to replay from a cassette record (S5).

    ``final`` is the message the client received when the episode rewrote it;
    ``raw`` is the message as it crossed the wire. The replayed message must be
    the one the client saw, so ``final`` wins whenever it exists.

    Args:
        record: A ``msg`` record.

    Returns:
        The recorded request or response object.
    """
    final = record.get("final")
    if isinstance(final, dict):
        return dict(final)
    raw = record.get("raw")
    if not isinstance(raw, dict):
        raise ReplayError(f"msg seq {record.get('seq')}: raw is not an object")
    return dict(raw)


@dataclass(frozen=True)
class Entry:
    """One message read from a cassette.

    Attributes:
        record: The ``msg`` record.
        payload: The message to replay: ``final`` when present, else ``raw``.
    """

    record: dict[str, Any]
    payload: dict[str, Any]


def read_cassette(path: Path) -> list[dict[str, Any]]:
    """Read every record of a cassette file (S5).

    Args:
        path: The cassette file.

    Returns:
        The decoded records, in file order.

    Raises:
        ReplayError: When the file is unreadable, is not JSONL, or does not
            start with a ``skeptic.cassette/v1`` header.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReplayError(f"cannot read {path}: {exc.strerror}") from exc
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ReplayError(f"{path}:{number}: a record must be a JSON object")
        records.append(value)
    if not records or records[0].get("type") != "header":
        raise ReplayError(f"{path}: the first record is not a header")
    if records[0].get("schema") != SCHEMA_ID:
        raise ReplayError(f"{path}: schema is not {SCHEMA_ID}")
    return records


def _interleave(
    records: Sequence[Entry], methods: frozenset[str] = frozenset({TOOLS_CALL})
) -> Iterator[tuple[Entry, Entry | None]]:
    """Pair each request record with the response that follows it (S4.3).

    The response is the next ``s2c`` record whose id equals the request id and
    that is not internal. Notifications and other methods are skipped.

    Args:
        records: Every ``msg`` record of the cassette, in file order.
        methods: The request methods to pair.

    Yields:
        One ``(request, response)`` pair; ``response`` is ``None`` when the
        request never got an answer.
    """
    for index, entry in enumerate(records):
        request = entry.record.get("raw")
        if entry.record.get("dir") != "c2s" or not isinstance(request, dict):
            continue
        if request.get("method") not in methods or "id" not in request:
            continue
        ident = request["id"]
        answer: Entry | None = None
        for later in records[index + 1 :]:
            record = later.record
            if record.get("dir") != "s2c" or record.get("internal"):
                continue
            candidate = later.payload
            if candidate.get("id") == ident and ("result" in candidate or "error" in candidate):
                answer = later
                break
        yield entry, answer


@dataclass
class Cassette:
    """One episode's recorded replies, queued by replay key (P16).

    Attributes:
        path: The cassette file.
        methods: The single recorded reply of each handshake or list method.
        calls: One queue per ``tools/call`` key, in recorded order.
        order: The ``tools/call`` keys in the order their first request came.
    """

    path: Path
    methods: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Cassette":
        """Read a cassette and queue its replayable responses (S5, P16).

        Args:
            path: The cassette file.

        Returns:
            The loaded cassette.

        Raises:
            ReplayError: When the file is not a readable cassette, or a reply
                that would be replayed was redacted (1.7).
        """
        records = read_cassette(path)
        cassette = cls(path=path)
        entries: list[Entry] = []
        for record in records:
            if record.get("type") != "msg":
                continue
            if not isinstance(record.get("raw"), dict):
                raise ReplayError(f"msg seq {record.get('seq')}: raw is not an object")
            entry = Entry(record=record, payload=_payload(record))
            # A response carries ``id``; an s2c notification does not and is
            # never replayed, so only a would-be reply is checked here.
            raw = record["raw"]
            is_reply = "id" in raw or "result" in raw
            if record.get("dir") == "s2c" and is_reply:
                _replayable(entry, "the recorded reply")
            entries.append(entry)

        for request, answer in _interleave(entries, CACHED_METHODS):
            if answer is None:
                continue
            method = (request.payload.get("method") or "").strip()
            if method in HANDSHAKE_METHODS or method == TOOLS_LIST:
                cassette.methods.setdefault(method, _replayable(answer, "the recorded reply"))

        for request, answer in _interleave(entries):
            if answer is None:
                raise ReplayError(
                    f"msg seq {request.record.get('seq')}: the tools/call has no recorded reply"
                )
            key = _response_key(request.record, request.payload)
            reply = _replayable(answer, "the recorded tools/call reply")
            if key not in cassette.calls:
                cassette.calls[key] = deque()
                cassette.order.append(key)
            cassette.calls[key].append(reply)
        return cassette

    def match(self, msg: Request) -> dict[str, Any] | None:
        """Take the next recorded reply of a request, or ``None`` on a miss (P16).

        Args:
            msg: The client request.

        Returns:
            The recorded reply object, or ``None`` when nothing matches.
        """
        if msg.method in CACHED_METHODS:
            return self.methods.get(msg.method)
        queue = self.calls.get(_request_key(msg))
        if not queue:
            return None
        return queue.popleft()

    def pending(self) -> int:
        """Return how many ``tools/call`` replies are still queued.

        Returns:
            The number of replies left in every queue.
        """
        return sum(len(queue) for queue in self.calls.values())


def _without_secrets(entry: Entry, what: str) -> dict[str, Any]:
    """Return a reply, refusing one that lost a value to redaction (1.7).

    Args:
        entry: The s2c record.
        what: What the reply is, for the error message.

    Returns:
        The payload.

    Raises:
        ReplayError: When the recorded value contains a redaction marker.
    """
    if REDACTED in json.dumps(entry.payload, ensure_ascii=False):
        raise ReplayError(what + " was redacted by the recorder (1.7), so it cannot be replayed")
    return entry.payload


def _replayable(entry: Entry, what: str) -> dict[str, Any]:
    """Return a reply that can be replayed word for word (S2, P16).

    Args:
        entry: The s2c record.
        what: What the reply is, for the error message.

    Returns:
        The payload.

    Raises:
        ReplayError: When the recorded value was redacted (1.7) or is not a
            JSON-RPC reply, so serving it could not reproduce the episode.
    """
    payload = _without_secrets(entry, what)
    value = dict(payload)
    value.setdefault("jsonrpc", "2.0")
    value.setdefault("id", None)
    if not ("result" in value or "error" in value):
        raise ReplayError(f"msg seq {entry.record.get('seq')}: {what} is not a response")
    parsed = parse_line(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if isinstance(parsed, ParseError):
        raise ReplayError(f"msg seq {entry.record.get('seq')}: {what} is not a JSON-RPC message")
    return payload


def recorded_initialize(cassette: Cassette) -> dict[str, Any] | None:
    """Return the recorded handshake, with ``initialize`` and ``discover`` merged.

    A cassette of a modern episode records ``server/discover``; a cassette of a
    legacy one records ``initialize``. Answering either name with whichever was
    recorded lets one client handshake reach one cassette on either era.

    Args:
        cassette: The loaded cassette.

    Returns:
        The recorded handshake reply, or ``None`` when the cassette has none.
    """
    for method in (INITIALIZE, DISCOVER):
        reply = cassette.methods.get(method)
        if reply is not None:
            return reply
    return None


def miss_error(msg: Request, *, detail: str) -> ErrorResponse:
    """Build the error a match miss is answered with (S2).

    Args:
        msg: The request that missed.
        detail: A short explanation for the error message.

    Returns:
        The error response carrying the request id.
    """
    return ErrorResponse(
        id=msg.id,
        error=ErrorObject(code=MISS_CODE, message=f"replay: no recorded reply ({detail})"),
    )


def _response_from(payload: Mapping[str, Any], msg: Request) -> Message:
    """Rebuild a recorded reply for a request, with the request's id.

    ``Cassette.load`` has already checked every queued reply is a JSON-RPC
    response and replaced its id, so this only substitutes the client's id.

    Args:
        payload: The recorded reply object.
        msg: The request being answered.

    Returns:
        The reply message.
    """
    value = dict(payload)
    value["id"] = msg.id
    value["jsonrpc"] = "2.0"
    reply = parse_line(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    assert not isinstance(reply, ParseError)
    return reply


class _StdinReader:
    """The process stdin seen as a line source."""

    def readline(self) -> bytes:
        """Read one blocking line; the runner puts it in a worker thread.

        Returns:
            The line including its terminator, or ``b""`` at EOF.
        """
        return sys.stdin.buffer.readline()


class _StdoutWriter:
    """The process stdout seen as a line sink."""

    def write(self, data: bytes) -> None:
        """Write bytes to stdout without flushing.

        Args:
            data: The bytes to write.
        """
        sys.stdout.buffer.write(data)

    async def drain(self) -> None:
        """Flush stdout."""
        sys.stdout.buffer.flush()


class _Live:
    """A live upstream child process used when a request matches nothing (S2)."""

    def __init__(self, command: Sequence[str]) -> None:
        """Remember the command.

        Args:
            command: The upstream command.
        """
        self.command = list(command)
        self.process: asyncio.subprocess.Process | None = None
        self._stderr: asyncio.Task[None] | None = None

    async def start(self) -> bool:
        """Start the upstream.

        Returns:
            ``True`` when it started, ``False`` when the command could not run.
        """
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=BACKLOG_LIMIT,
            )
        except OSError:
            return False
        self._stderr = asyncio.create_task(self._copy_stderr())
        return True

    async def _copy_stderr(self) -> None:
        """Copy the upstream stderr to ours (S4.1)."""
        if self.process is None or self.process.stderr is None:
            return
        while True:
            chunk = await self.process.stderr.read(65536)
            if not chunk:
                return
            sys.stderr.buffer.write(chunk)
            sys.stderr.buffer.flush()

    async def request(self, line: bytes, out: Any) -> bytes | None:
        """Forward one request and return the upstream's answer to it.

        Replay handles one client line at a time, so a miss is forwarded on its
        own. Lines the upstream sends meanwhile that are not the answer are
        passed on to the client as they arrive.

        Args:
            line: The client's request line.
            out: The client's binary output stream.

        Returns:
            The answering upstream line, or ``None`` on EOF.
        """
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            return None
        self.process.stdin.write(line)
        await self.process.stdin.drain()
        wanted = parse_line(line)
        wanted_id = wanted.id if isinstance(wanted, Request) else None
        while True:
            answered = await self.process.stdout.readline()
            if not answered:
                return None
            reply = parse_line(answered)
            if wanted_id is not None and not isinstance(reply, ParseError):
                if getattr(reply, "id", None) == wanted_id:
                    return answered
                if not isinstance(reply, Request):
                    out.write(answered)
                    await out.drain()
                    continue
            return answered

    async def handshake(self, line: bytes) -> None:
        """Send the client's handshake to the upstream and discard the answer.

        The replayer answers the handshake from the cassette, but the live
        upstream is a fresh process that has not handshaken yet; without this it
        would reject every forwarded call as out of session.

        Args:
            line: The client's ``initialize`` or ``server/discover`` line.
        """
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            return
        self.process.stdin.write(line)
        await self.process.stdin.drain()
        await self.process.stdout.readline()

    async def close(self) -> None:
        """Close the upstream stdin and wait for it to exit (S2)."""
        if self.process is None:
            return
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), LIVE_CLOSE_TIMEOUT_SECONDS)
        except TimeoutError:
            self.process.terminate()
            await self.process.wait()
        if self._stderr is not None:
            await asyncio.gather(self._stderr, return_exceptions=True)


@dataclass
class ReplayServer:
    """A stdio MCP server that answers from a cassette (S2, P16).

    Attributes:
        cassette: The loaded cassette.
        on_miss: ``error`` or ``live`` (S2).
        live_command: The upstream command ``--on-miss live`` needs.
    """

    cassette: Cassette
    on_miss: str = ON_MISS_ERROR
    live_command: Sequence[str] | None = None
    _live: _Live | None = field(default=None, init=False, repr=False)

    def answer(self, msg: Request) -> Message | None:
        """Return the recorded reply of a request, or ``None`` on a miss.

        The recorded handshake is answered for ``initialize`` and
        ``server/discover`` alike, so either client era reaches the recording.

        Args:
            msg: The request.

        Returns:
            The reply message, or ``None`` when no reply was recorded.
        """
        payload = self.cassette.match(msg)
        if payload is None and msg.method in HANDSHAKE_METHODS:
            payload = recorded_initialize(self.cassette)
        if payload is None:
            return None
        return _response_from(payload, msg)

    async def handle_line(self, line: bytes, out: Any) -> None:
        """Answer one client line and write every reply to ``out``.

        Args:
            line: The client line, with or without its newline.
            out: A binary stream with ``write`` and async ``drain``.
        """
        msg = parse_line(line)
        if isinstance(msg, ParseError):
            await self._write(
                out,
                ErrorResponse(
                    id=None,
                    error=ErrorObject(code=-32700, message=f"parse error: {msg.reason}"),
                ),
            )
            return
        if not isinstance(msg, Request):
            return
        if msg.method in HANDSHAKE_METHODS and self._live is not None:
            await self._live.handshake(dump(msg))
        reply = self.answer(msg)
        if reply is not None:
            out.write(reply.raw_bytes + b"\n" if reply.raw_bytes else dump(reply))
            await out.drain()
            return
        if self.on_miss == ON_MISS_LIVE and self._live is not None:
            forwarded = await self._live.request(dump(msg), out)
            if forwarded:
                out.write(forwarded if forwarded.endswith(b"\n") else forwarded + b"\n")
                await out.drain()
                return
        await self._write(
            out,
            miss_error(msg, detail=f"{msg.method} {_short(json.dumps(msg.params or {}))}"),
        )

    @staticmethod
    async def _write(out: Any, msg: Message) -> None:
        """Write one message to the client.

        Args:
            out: A binary stream with ``write`` and async ``drain``.
            msg: The message.
        """
        out.write(dump(msg))
        await out.drain()

    async def run(self, *, stdin: Any = None, stdout: Any = None) -> int:
        """Serve stdin until it closes (S2).

        Args:
            stdin: A binary line source; defaults to ``sys.stdin.buffer``.
            stdout: A binary sink; defaults to ``sys.stdout.buffer``.

        Returns:
            ``0`` on a clean run, ``EXIT_INVALID`` when the live upstream does
            not start.
        """
        source = stdin if stdin is not None else _StdinReader()
        sink = stdout if stdout is not None else _StdoutWriter()
        if self.on_miss == ON_MISS_LIVE and self.live_command:
            self._live = _Live(self.live_command)
            if not await self._live.start():
                sys.stderr.write(
                    "error: could not start the --on-miss live upstream: "
                    + " ".join(self.live_command)
                    + "\n"
                )
                return EXIT_INVALID
        try:
            while True:
                line = await asyncio.to_thread(source.readline)
                if not line:
                    return 0
                if not line.strip():
                    continue
                await self.handle_line(line, sink)
        finally:
            if self._live is not None:
                await self._live.close()


def _short(text: str, limit: int = 120) -> str:
    """Shorten a string for an error message.

    Args:
        text: The text.
        limit: The maximum length.

    Returns:
        The text, cut with an ellipsis when longer than ``limit``.
    """
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = [
    "ON_MISS_ERROR",
    "ON_MISS_LIVE",
    "ON_MISS_VALUES",
    "Cassette",
    "ReplayError",
    "ReplayServer",
    "read_cassette",
    "recorded_initialize",
    "request_key",
]
