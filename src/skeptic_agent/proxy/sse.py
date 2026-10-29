"""Server-sent event framing for the HTTP proxy (S4.1).

An upstream ``text/event-stream`` body carries one JSON-RPC message per event, in
``data:`` lines. The proxy must hand every message to the pipeline on its own, so
this module decodes the body one event at a time and writes the events back out
with the same ``id`` and ``event`` fields.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass

DATA_FIELD: str = "data"
"""The SSE field that carries the JSON-RPC payload (S4.1)."""

ID_FIELD: str = "id"
"""The SSE field that carries the last event id."""

EVENT_FIELD: str = "event"
"""The SSE field that carries an event type such as ``message``."""

_SPECIAL_LINE_CHARS: tuple[str, ...] = ("\r", "\n", "\x00")
"""Characters a field value cannot hold; such a line is not a field."""


@dataclass(frozen=True)
class SseEvent:
    """One server-sent event.

    Attributes:
        data: The joined ``data`` lines, without the trailing newline.
        event: The ``event`` field, or ``""`` when absent.
        event_id: The ``id`` field, or ``""`` when absent.
    """

    data: str
    event: str = ""
    event_id: str = ""

    def is_message(self) -> bool:
        """Report whether this event carries a JSON-RPC message.

        Returns:
            ``True`` when the data is not empty and the event is a plain
            ``message`` (or untyped), which is what the pipeline processes.
        """
        return bool(self.data) and self.event in {"", "message"}


def _field(line: str) -> tuple[str, str] | None:
    """Split one SSE line into its field name and value.

    Args:
        line: A line without its terminator.

    Returns:
        The name and value, or ``None`` for a blank line or a comment.
    """
    if not line or line.startswith(":"):
        return None
    name, separator, value = line.partition(":")
    if any(char in value for char in _SPECIAL_LINE_CHARS):
        return None
    if separator and value.startswith(" "):
        value = value[1:]
    return name, value


def encode_event(event: SseEvent) -> bytes:
    """Serialize an event as an SSE block ending in a blank line.

    Args:
        event: The event to write.

    Returns:
        The UTF-8 bytes of the event.
    """
    lines: list[str] = []
    if event.event_id:
        lines.append(f"{ID_FIELD}: {event.event_id}")
    if event.event:
        lines.append(f"{EVENT_FIELD}: {event.event}")
    lines.extend(f"{DATA_FIELD}: {line}" for line in event.data.split("\n"))
    return ("\n".join(lines) + "\n\n").encode("utf-8")


class SseDecoder:
    """Turn an incremental byte stream into events, one complete event at a time.

    A line becomes complete on ``\\r\\n``, ``\\r`` or ``\\n``. An event becomes
    complete on the blank line that follows its fields, so the decoder keeps the
    bytes of an unfinished line and the fields of an unfinished event between
    calls.
    """

    def __init__(self) -> None:
        """Start a decoder with no buffered bytes and no pending event."""
        self._buffer: str = ""
        self._data: list[str] = []
        self._event: str = ""
        self._event_id: str = ""

    def feed(self, chunk: bytes) -> list[SseEvent]:
        """Add bytes and return every event they completed.

        The last line of a chunk stays buffered, because the chunk may end in
        the middle of it.

        Args:
            chunk: The bytes read from the upstream.

        Returns:
            The completed events, in arrival order.
        """
        try:
            self._buffer += chunk.decode("utf-8")
        except UnicodeDecodeError:
            # A page that is not SSE at all: drop it rather than send garbage.
            self._buffer = ""
            return []
        return self._drain(final=False)

    def close(self) -> list[SseEvent]:
        """Return the events left in the buffer when the stream ends.

        A final line without a terminator still counts as a line.

        Returns:
            The remaining events, in arrival order.
        """
        return self._drain(final=True)

    def _flush(self) -> SseEvent | None:
        """Build the pending event and clear its fields.

        Returns:
            The event when the pending fields form one, else ``None``.
        """
        event = None
        if self._data:
            event = SseEvent(data="\n".join(self._data), event=self._event, event_id=self._event_id)
        self._data, self._event, self._event_id = [], "", ""
        return event

    def _drain(self, *, final: bool) -> list[SseEvent]:
        """Split the buffer into lines and collect the completed events.

        Args:
            final: When true, also consume the last unterminated line.

        Returns:
            The completed events.
        """
        text = self._buffer
        events: list[SseEvent] = []
        consumed = 0
        length = len(text)
        while consumed < length:
            line_end = consumed
            while line_end < length and text[line_end] not in "\r\n":
                line_end += 1
            last_line = line_end == length and final
            if line_end == length and not final:
                break
            next_position = line_end + 1
            if not last_line and text[line_end] == "\r":
                if next_position >= length and not final:
                    # The ``\n`` of a ``\r\n`` may still be in the next chunk.
                    break
                if next_position < length and text[next_position] == "\n":
                    next_position += 1
            if last_line:
                next_position = length
            line = text[consumed:line_end]
            consumed = next_position
            if not line:
                event = self._flush()
                if event is not None:
                    events.append(event)
                continue
            field = _field(line)
            if field is None:
                continue
            name, value = field
            if name == DATA_FIELD:
                self._data.append(value)
            elif name == EVENT_FIELD:
                self._event = value
            elif name == ID_FIELD:
                self._event_id = value
        self._buffer = text[consumed:]
        if final:
            event = self._flush()
            if event is not None:
                events.append(event)
        return events

    async def read(self, lines: AsyncIterator[bytes]) -> AsyncIterator[SseEvent]:
        """Decode the events of a byte-iterator stream as they complete.

        Args:
            lines: Chunks of the event-stream body.

        Yields:
            Each complete event, in arrival order.
        """
        async for chunk in lines:
            for event in self.feed(chunk):
                yield event
        for event in self.close():
            yield event
