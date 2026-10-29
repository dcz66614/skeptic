"""Unit tests for the SSE framing and the HTTP header rules (S4.1, P14)."""

import pytest

from skeptic_agent.proxy.http import (
    HOP_BY_HOP_HEADERS,
    forwarded_request_headers,
    forwarded_response_headers,
)
from skeptic_agent.proxy.sse import SseDecoder, SseEvent, encode_event

pytestmark = pytest.mark.unit


def _decode(chunks: list[bytes]) -> list[SseEvent]:
    """Feed chunks to a decoder and return every event it produced.

    Args:
        chunks: The byte chunks of a stream.

    Returns:
        The decoded events, followed by the ones left at close.
    """
    decoder = SseDecoder()
    events: list[SseEvent] = []
    for chunk in chunks:
        events.extend(decoder.feed(chunk))
    events.extend(decoder.close())
    return events


def test_encode_event_without_id_or_type() -> None:
    """A plain event writes only ``data`` lines."""
    assert encode_event(SseEvent(data='{"a":1}')) == b'data: {"a":1}\n\n'


def test_encode_event_keeps_id_and_type() -> None:
    """The id and the event type are written back in the SSE order."""
    event = SseEvent(data='{"a":1}', event="message", event_id="4")
    assert encode_event(event) == b'id: 4\nevent: message\ndata: {"a":1}\n\n'


def test_encode_multi_line_data() -> None:
    """Every data line is written with its own ``data:`` prefix."""
    assert encode_event(SseEvent(data="a\nb")) == b"data: a\ndata: b\n\n"


def test_decode_single_event() -> None:
    """One complete event decodes with its fields."""
    events = _decode([b'event: message\nid: 3\ndata: {"x":1}\n\n'])
    assert events == [SseEvent(data='{"x":1}', event="message", event_id="3")]


def test_decode_split_across_chunks() -> None:
    """An event may arrive over several chunks."""
    events = _decode([b"data: {", b'"x":', b"1}\n", b"\n"])
    assert events == [SseEvent(data='{"x":1}')]


def test_decode_crlf_and_cr_terminators() -> None:
    """``\\r\\n`` and a bare ``\\r`` both end a line."""
    events = _decode([b"data: a\r\n\r\ndata: b\r\r"])
    assert events == [SseEvent(data="a"), SseEvent(data="b")]


def test_decode_keeps_comment_lines_out() -> None:
    """A comment line is not an event and not a field."""
    events = _decode([b": keep-alive\n\n", b"data: x\n\n"])
    assert events == [SseEvent(data="x")]


def test_decode_without_space_after_colon() -> None:
    """``data:{}`` is a valid field value too."""
    assert _decode([b"data:{}\n\n"]) == [SseEvent(data="{}")]


def test_decode_unknown_fields_are_ignored() -> None:
    """``retry`` and friends do not affect the decoded event."""
    assert _decode([b"retry: 10\ndata: x\n\n"]) == [SseEvent(data="x")]


def test_close_flushes_an_unterminated_event() -> None:
    """A stream that ends without a blank line still yields its last event."""
    decoder = SseDecoder()
    assert decoder.feed(b"data: tail") == []
    assert decoder.close() == [SseEvent(data="tail")]


def test_invalid_utf8_is_dropped() -> None:
    """Bytes that are not UTF-8 produce no events instead of an error."""
    assert _decode([b"\xff\xfe", b"data: ok\n\n"]) == [SseEvent(data="ok")]


def test_event_type_is_kept_but_message_answers_plain() -> None:
    """``is_message`` accepts untyped and ``message`` events only."""
    assert SseEvent(data="x").is_message()
    assert SseEvent(data="x", event="message").is_message()
    assert not SseEvent(data="x", event="ping").is_message()
    assert not SseEvent(data="").is_message()


@pytest.mark.asyncio
async def test_read_yields_events_from_an_iterator() -> None:
    """``read`` drives the decoder from an async chunk iterator."""

    async def chunks() -> object:
        for chunk in (b"data: a\n\n", b"data: b\n\n"):
            yield chunk

    decoder = SseDecoder()
    events = [event async for event in decoder.read(chunks())]  # type: ignore[arg-type]
    assert events == [SseEvent(data="a"), SseEvent(data="b")]


def test_request_headers_drop_hop_by_hop() -> None:
    """Hop-by-hop, ``Host`` and ``Content-Length`` are not forwarded."""
    headers = {
        "Authorization": "Bearer t",
        "Mcp-Protocol-Version": "2026-07-28",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
        "Host": "localhost:8000",
        "Content-Length": "12",
    }
    assert forwarded_request_headers(headers) == {
        "Authorization": "Bearer t",
        "Mcp-Protocol-Version": "2026-07-28",
    }


def test_response_headers_drop_hop_by_hop_and_length() -> None:
    """The body is re-framed, so the upstream length is dropped as well."""
    headers = {"Content-Type": "text/event-stream", "Transfer-Encoding": "chunked"}
    assert forwarded_response_headers(headers) == {"Content-Type": "text/event-stream"}


def test_hop_by_hop_list_is_the_plan_list() -> None:
    """The header set covers every name S4.1 lists."""
    assert {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
    } == HOP_BY_HOP_HEADERS
