"""The cassette recorder: one JSONL file per episode (S5, 1.7).

A cassette has a header line, one line per message and a footer line. The
recorder flushes every line, redacts every ``raw`` and ``final`` value, and
writes the footer from ``atexit`` or a termination signal so a killed proxy
still leaves a finished file. The format is frozen by
``schemas/cassette.schema.json`` (``skeptic.cassette/v1``).
"""

import atexit
import contextlib
import json
import signal
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any, TextIO

from skeptic_agent import __version__
from skeptic_agent.faults.base import FaultSpec
from skeptic_agent.faults.schedule import CallIndex
from skeptic_agent.jsonrpc import ErrorResponse, Message, Request, Response
from skeptic_agent.protocol import Era
from skeptic_agent.proxy.context import INTERNAL_ID_PREFIX, EpisodeContext
from skeptic_agent.proxy.pipeline import (
    C2S,
    S2C,
    TOOLS_CALL,
    Action,
    Forward,
    RecorderStage,
)
from skeptic_agent.record.redact import redact

SCHEMA_ID: str = "skeptic.cassette/v1"
"""The cassette schema id written in the header (S5)."""

SIGNALS: tuple[str, ...] = ("SIGTERM", "SIGINT")
"""The signals that flush the footer before the process ends (S5, P15)."""


def cassette_file_name(episode_id: str) -> str:
    """Return the cassette file name of an episode (S5).

    Args:
        episode_id: The episode identifier, whose colons separate its parts.

    Returns:
        The identifier with every ``:`` replaced by ``__`` and ``.jsonl`` added.
    """
    return episode_id.replace(":", "__") + ".jsonl"


def cassette_path(directory: Path, episode_id: str) -> Path:
    """Return the cassette path of an episode inside a record directory (S5).

    Args:
        directory: The ``--record`` directory.
        episode_id: The episode identifier.

    Returns:
        ``directory/<episode id with "__">.jsonl``.
    """
    return directory / cassette_file_name(episode_id)


def utc_now() -> str:
    """Return the current UTC time in the S5 ``date-time`` form.

    Returns:
        ``YYYY-MM-DDTHH:MM:SSZ``.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _upstream(transport: str, upstream: Sequence[str] | str) -> dict[str, Any]:
    """Build the header's ``upstream`` object for the transport (S5).

    Args:
        transport: ``stdio`` or ``http``.
        upstream: The upstream command for stdio, or the URL for HTTP.

    Returns:
        ``{"command": [...]}`` for stdio, ``{"url": "..."}`` for HTTP.
    """
    if transport == "http":
        return {"url": upstream if isinstance(upstream, str) else " ".join(upstream)}
    return {"command": [upstream] if isinstance(upstream, str) else list(upstream)}


def _call_index(index: CallIndex) -> int | list[int] | str:
    """Convert a ``CallIndex`` to its JSON form (S5, S7.1).

    Args:
        index: One attempt, a tuple of attempts, or ``"all"``.

    Returns:
        An integer, a list of integers, or ``"all"``.
    """
    return list(index) if isinstance(index, tuple) else index


def fault_plan_entry(spec: FaultSpec) -> dict[str, Any]:
    """Build one ``fault_plan`` object of the header (S5, S7.1).

    Only the keys that were set are written: ``probability`` when it is not 1,
    ``n`` for ``transient`` and ``mixed``, ``p`` for ``intermittent`` and
    ``mixed``, ``permanent_p`` for ``mixed``, ``params`` when not empty.

    Args:
        spec: One scheduled fault.

    Returns:
        The fault plan entry.
    """
    entry: dict[str, Any] = {"id": spec.fault_id, "target": {"tool": spec.tool}}
    when: dict[str, Any] = {"call_index": _call_index(spec.call_index)}
    if spec.probability != 1.0:
        when["probability"] = spec.probability
    entry["when"] = when
    persistence: dict[str, Any] = {"mode": spec.persistence}
    if spec.persistence in {"transient", "mixed"}:
        persistence["n"] = spec.n
    if spec.persistence in {"intermittent", "mixed"}:
        persistence["p"] = spec.p
    if spec.persistence == "mixed":
        persistence["permanent_p"] = spec.permanent_p
    entry["persistence"] = persistence
    if spec.params:
        entry["params"] = dict(spec.params)
    return entry


def cassette_header(
    *,
    episode_id: str,
    created_at: str,
    transport: str,
    upstream: Sequence[str] | str,
    era: Era,
    seed: int,
    profile: str,
    fault_plan: Iterable[FaultSpec] = (),
    guards: Iterable[str] = (),
    scenario_id: str,
) -> dict[str, Any]:
    """Build the first cassette record (S5).

    Args:
        episode_id: The episode identifier.
        created_at: The creation time in the S5 form.
        transport: ``stdio`` or ``http``.
        upstream: The upstream command, or the URL for HTTP.
        era: The detected protocol era; ``UNKNOWN`` is written ``unknown`` (S4.2).
        seed: The episode seed.
        profile: The fault profile id or path.
        fault_plan: The scheduled faults.
        guards: The enabled Guard ids.
        scenario_id: The scenario id.

    Returns:
        The header object.
    """
    return {
        "type": "header",
        "schema": SCHEMA_ID,
        "episode_id": episode_id,
        "created_at": created_at,
        "skeptic_version": __version__,
        "transport": transport,
        "upstream": _upstream(transport, upstream),
        "era": era.version if era.version is not None else "unknown",
        "seed": seed,
        "profile": profile,
        "fault_plan": [fault_plan_entry(spec) for spec in fault_plan],
        "guards": list(guards),
        "scenario_id": scenario_id,
    }


def message_payload(msg: Message) -> dict[str, Any]:
    """Return the JSON object a message carries (S5 ``raw`` and ``final``).

    The original bytes are decoded when the message still has them, so a
    cassette holds exactly what crossed the wire; a message a fault rebuilt has
    no bytes and its fields are used instead.

    Args:
        msg: The message.

    Returns:
        A JSON object.
    """
    if msg.raw_bytes:
        try:
            value: Any = json.loads(msg.raw_bytes)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value
    payload = msg.model_dump()
    payload.pop("raw_bytes", None)
    if payload.get("params") is None:
        payload.pop("params", None)
    payload["jsonrpc"] = "2.0"
    return payload


def message_id(msg: Message) -> int | str | None:
    """Return the id of a request or response.

    Args:
        msg: Any message.

    Returns:
        The id, or ``None`` for a notification.
    """
    if isinstance(msg, (Request, Response, ErrorResponse)):
        return msg.id
    return None


def is_internal(msg: Message) -> bool:
    """Report whether the proxy sent or received this message itself (S4.3, S5).

    Args:
        msg: Any message.

    Returns:
        ``True`` for a message carrying a ``skeptic-`` id.
    """
    ident = message_id(msg)
    return ident is not None and str(ident).startswith(INTERNAL_ID_PREFIX)


def _stats(
    messages: int, tool_calls: int, faults_applied: int, guard_actions: int
) -> dict[str, int]:
    """Build the footer ``stats`` object (S5).

    Args:
        messages: How many ``msg`` lines were written.
        tool_calls: How many ``tools/call`` requests were recorded.
        faults_applied: How many lines carry a fault.
        guard_actions: How many Guard actions were recorded.

    Returns:
        The stats object.
    """
    return {
        "messages": messages,
        "tool_calls": tool_calls,
        "faults_applied": faults_applied,
        "guard_actions": guard_actions,
    }


@dataclass
class Recorder:
    """Write one cassette file: header, messages, then the footer (S5).

    Attributes:
        path: The cassette file.
    """

    path: Path
    """The cassette file."""
    _stream: TextIO | None = field(default=None, repr=False)
    _seq: int = field(default=0, repr=False)
    _start: float = field(default=0.0, repr=False)
    _messages: int = field(default=0, repr=False)
    _tool_calls: int = field(default=0, repr=False)
    _faults: int = field(default=0, repr=False)
    _guards: int = field(default=0, repr=False)
    _finished: bool = field(default=False, repr=False)
    _exit_hook: Callable[[], None] | None = field(default=None, repr=False)
    _signals: list[tuple[Any, Any]] = field(default_factory=list, repr=False)

    @classmethod
    def open(
        cls,
        directory: Path,
        *,
        episode_id: str,
        transport: str,
        upstream: Sequence[str] | str,
        era: Era,
        seed: int,
        profile: str,
        fault_plan: Iterable[FaultSpec] = (),
        guards: Iterable[str] = (),
        scenario_id: str,
    ) -> "Recorder":
        """Create the episode directory, its file and the header line (S5).

        Args:
            directory: The record directory.
            episode_id: The episode identifier.
            transport: ``stdio`` or ``http``.
            upstream: The upstream command, or the URL for HTTP.
            era: The detected protocol era.
            seed: The episode seed.
            profile: The fault profile id or path.
            fault_plan: The scheduled faults.
            guards: The enabled Guard ids.
            scenario_id: The scenario id.

        Returns:
            The open recorder.
        """
        directory.mkdir(parents=True, exist_ok=True)
        recorder = cls(path=cassette_path(directory, episode_id))
        recorder._stream = recorder.path.open("w", encoding="utf-8", newline="\n")
        recorder._start = datetime.now(UTC).timestamp()
        recorder._write(
            cassette_header(
                episode_id=episode_id,
                created_at=utc_now(),
                transport=transport,
                upstream=upstream,
                era=era,
                seed=seed,
                profile=profile,
                fault_plan=fault_plan,
                guards=guards,
                scenario_id=scenario_id,
            )
        )
        recorder._install_exit_hooks()
        return recorder

    def __enter__(self) -> "Recorder":
        """Return the recorder itself for a ``with`` block.

        Returns:
            The recorder.
        """
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Write the footer on leaving the block (S5).

        Args:
            exc_type: The exception type, or ``None``.
            exc: The exception, or ``None``.
            tb: The traceback, or ``None``.
        """
        self.finish()

    @property
    def finished(self) -> bool:
        """Report whether the footer has been written.

        Returns:
            ``True`` once ``finish`` has run.
        """
        return self._finished

    def _install_exit_hooks(self) -> None:
        """Write the footer from ``atexit`` and the termination signals (S5).

        Platforms without a signal keep only the ``atexit`` hook, and a
        process whose signals cannot be set (a worker thread) keeps the same.
        """
        self._exit_hook = atexit.register(self.finish)
        for name in SIGNALS:
            number = getattr(signal, name, None)
            if number is None:
                continue
            try:
                previous = signal.getsignal(number)
                signal.signal(number, self._make_handler(number, previous))
            except (ValueError, OSError):
                continue
            self._signals.append((number, previous))

    def _make_handler(self, number: int, previous: Any) -> Callable[[int, FrameType | None], None]:
        """Build a handler that writes the footer, then runs ``previous`` (S5).

        Args:
            number: The signal number.
            previous: The handler installed before this recorder.

        Returns:
            The signal handler.
        """

        def handler(received: int, frame: FrameType | None) -> None:
            self.finish()
            if previous is signal.SIG_IGN:
                return
            if callable(previous):
                previous(received, frame)
                return
            if received == getattr(signal, "SIGINT", None):
                raise KeyboardInterrupt
            raise SystemExit(128 + received)

        return handler

    def _uninstall_exit_hooks(self) -> None:
        """Undo ``_install_exit_hooks`` so a finished recorder is inert (S5)."""
        if self._exit_hook is not None:
            atexit.unregister(self._exit_hook)
            self._exit_hook = None
        for number, previous in self._signals:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(number, previous)
        self._signals.clear()

    def _write(self, record: Mapping[str, Any]) -> None:
        """Write one record as a JSON line and flush it (S5).

        Args:
            record: The record to write.
        """
        if self._stream is None:
            return
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        self._stream.write(line + "\n")
        self._stream.flush()

    def _elapsed_ms(self) -> int:
        """Return the time since the header was written, in milliseconds (S5).

        Returns:
            A non-negative integer.
        """
        return max(0, int((datetime.now(UTC).timestamp() - self._start) * 1000))

    def record(
        self,
        *,
        direction: str,
        msg: Message,
        final: Message | None = None,
        fault: Mapping[str, Any] | None = None,
        guards: Sequence[Mapping[str, Any]] = (),
        dropped: bool = False,
        internal: bool | None = None,
    ) -> dict[str, Any]:
        """Write one ``msg`` line and return it (S5).

        ``raw`` is the message as received and ``final`` the message as sent;
        both are redacted (1.7). ``final`` is ``None`` when the message was not
        modified, and ``fault`` is ``None`` when no fault fired.

        Args:
            direction: ``c2s`` or ``s2c``.
            msg: The message as received.
            final: The message as sent, when it differs from ``msg``.
            fault: The applied fault record, or ``None``.
            guards: The Guard action records.
            dropped: Whether the message was dropped.
            internal: Whether the proxy sent or received it itself; ``None``
                reads it from the message id.

        Returns:
            The record as written.
        """
        is_proxy = is_internal(msg) if internal is None else internal
        record: dict[str, Any] = {
            "type": "msg",
            "seq": self._seq,
            "t_ms": self._elapsed_ms(),
            "dir": direction,
            "raw": redact(message_payload(msg)),
            "final": None if final is None else redact(message_payload(final)),
            "fault": None if fault is None else dict(fault),
            "guards": [dict(entry) for entry in guards],
            "dropped": dropped,
            "internal": is_proxy,
        }
        self._seq += 1
        self._messages += 1
        if isinstance(msg, Request) and msg.method == TOOLS_CALL and not is_proxy:
            self._tool_calls += 1
        if record["fault"] is not None:
            self._faults += 1
        self._guards += len(record["guards"])
        self._write(record)
        return record

    def stats(self) -> dict[str, int]:
        """Return the counters the footer reports so far (S5).

        Returns:
            The stats object.
        """
        return _stats(self._messages, self._tool_calls, self._faults, self._guards)

    def finish(self) -> None:
        """Write the footer and close the file; safe to call more than once (S5)."""
        if self._finished:
            return
        self._finished = True
        self._write({"type": "footer", "ended_at": utc_now(), "stats": self.stats()})
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._uninstall_exit_hooks()


class CassetteRecorder(RecorderStage):
    """The pipeline stage that records every message into one cassette (S4.4, S5).

    The recorder stage runs first on c2s and last on s2c, so it always sees the
    message the client sent and the message the client receives; anything a
    fault or a Guard changed is therefore what ``final`` holds. Other stages
    report their own work through ``note_fault`` and ``note_guard``; each note
    is attached to the message it happened on.
    """

    def __init__(self, recorder: Recorder) -> None:
        """Attach the writer.

        Args:
            recorder: The cassette writer.
        """
        self.recorder = recorder
        self._fault: dict[str, Any] | None = None
        self._guards: list[dict[str, Any]] = []

    def note_fault(self, fault: Mapping[str, Any]) -> None:
        """Attach a fault record to the next message written (S5).

        Args:
            fault: The applied fault record.
        """
        self._fault = dict(fault)

    def note_guard(self, guard: Mapping[str, Any]) -> None:
        """Attach a Guard action to the next message written (S5).

        Args:
            guard: The Guard action record.
        """
        self._guards.append(dict(guard))

    def _take_notes(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Return and clear the notes collected since the last line (S5).

        Returns:
            The fault record and the Guard records.
        """
        fault, guards = self._fault, self._guards
        self._fault, self._guards = None, []
        return fault, guards

    def _write(self, direction: str, msg: Message, ctx: EpisodeContext) -> None:
        """Write one line for a message the stage received (S5).

        Args:
            direction: ``c2s`` or ``s2c``.
            msg: The message as received.
            ctx: The episode context.
        """
        del ctx
        fault, guards = self._take_notes()
        same = direction == S2C
        self.recorder.record(
            direction=direction,
            msg=msg,
            final=msg if same and msg.raw_bytes == b"" else None,
            fault=fault,
            guards=guards,
        )

    async def on_c2s(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Record a client-to-server message and forward it (S4.4).

        Args:
            msg: The message as the client sent it.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        self._write(C2S, msg, ctx)
        return [Forward(msg)]

    async def on_s2c(self, msg: Message, ctx: EpisodeContext) -> list[Action]:
        """Record a server-to-client message and forward it (S4.4).

        Args:
            msg: The message as it leaves the Guard.
            ctx: The episode context.

        Returns:
            ``[Forward(msg)]``.
        """
        self._write(S2C, msg, ctx)
        return [Forward(msg)]
