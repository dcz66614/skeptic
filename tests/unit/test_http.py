"""Unit tests for the HTTP proxy internals that do not need a real server (P14)."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from starlette.requests import Request as HttpRequest

from skeptic_agent.jsonrpc import Notification, Request, Response, dump
from skeptic_agent.proxy.context import EpisodeContext
from skeptic_agent.proxy.http import (
    ACCEPTED_STATUS,
    MCP_PATH,
    UPSTREAM_FAILED_STATUS,
    HttpProxy,
    _Exchange,
    _is_json,
    _is_sse,
    _text,
    forwarded_request_headers,
    forwarded_response_headers,
    run_http_proxy,
)
from skeptic_agent.proxy.pipeline import (
    Drop,
    FaultStage,
    Forward,
    GuardStage,
    Hold,
    Pipeline,
    RecorderStage,
    ReplyToClient,
    ReplyWithStatus,
    SendToServer,
)

pytestmark = pytest.mark.unit


class _ScriptedTransport(httpx.AsyncBaseTransport):
    """An HTTP transport that replays one canned response per request."""

    def __init__(self, *responses: httpx.Response) -> None:
        """Store the responses to hand out, in order.

        Args:
            responses: The responses, one per request.
        """
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Record the request and return the next response.

        Args:
            request: The outgoing request.

        Returns:
            The next scripted response.
        """
        await request.aread()
        self.requests.append(request)
        return self.responses.pop(0)


class _FailingTransport(httpx.AsyncBaseTransport):
    """An HTTP transport that always raises, like a dead upstream."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Fail every request.

        Args:
            request: The outgoing request.

        Raises:
            httpx.ConnectError: Always.
        """
        raise httpx.ConnectError("no route", request=request)


def _proxy(*stages: RecorderStage, transport: httpx.AsyncBaseTransport) -> HttpProxy:
    """Build a proxy wired to a scripted transport, without its lifespan.

    Args:
        stages: A stage to install as the fault stage, when given.
        transport: The transport the HTTP client uses.

    Returns:
        The proxy, already holding an open client.
    """
    pipeline = None
    if stages:
        pipeline = Pipeline(FaultStage(), GuardStage(), stages[0])
    proxy = HttpProxy("http://upstream.test/mcp", pipeline)
    proxy.client = httpx.AsyncClient(transport=transport)
    return proxy


def _request(method: str, body: bytes = b"", headers: dict[str, str] | None = None) -> HttpRequest:
    """Build a Starlette request without a server.

    Args:
        method: The HTTP method.
        body: The raw body.
        headers: Extra headers.

    Returns:
        The request.
    """
    scope: dict[str, Any] = {
        "type": "http",
        "method": method,
        "path": MCP_PATH,
        "headers": [
            (name.lower().encode(), value.encode()) for name, value in (headers or {}).items()
        ],
        "query_string": b"",
    }

    async def receive() -> dict[str, Any]:
        """Deliver the body once, then report the disconnect.

        Returns:
            The ``http.request`` message, then ``http.disconnect``.
        """
        if not hasattr(receive, "sent"):
            receive.sent = True  # type: ignore[attr-defined]
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return HttpRequest(scope, receive)


async def _body(response: Any) -> bytes:
    """Collect a Starlette response body, streaming one if needed.

    Args:
        response: The response.

    Returns:
        The body bytes.
    """
    if hasattr(response, "body_iterator"):
        return b"".join([chunk async for chunk in response.body_iterator])
    return bytes(response.body)


class _HoldStage(RecorderStage):
    """Hold every s2c reply, then answer it with a scripted action."""

    def __init__(self, hold: Hold) -> None:
        """Store the hold to return.

        Args:
            hold: The hold action every reply gets.
        """
        self.hold = hold

    async def on_s2c(self, msg: Any, ctx: EpisodeContext) -> list[Any]:
        """Hold the reply.

        Args:
            msg: The server message.
            ctx: The episode context.

        Returns:
            The hold action.
        """
        del msg, ctx
        return [self.hold]


class _SendStage(RecorderStage):
    """Queue extra actions after forwarding everything."""

    def __init__(self, *follow: Any) -> None:
        """Store the follow-up actions.

        Args:
            follow: The actions to append.
        """
        self.follow = follow

    async def on_c2s(self, msg: Any, ctx: EpisodeContext) -> list[Any]:
        """Forward the message and append the extra actions.

        Args:
            msg: The client message.
            ctx: The episode context.

        Returns:
            ``[Forward(msg), *follow]``.
        """
        del ctx
        return [Forward(msg)] if not self.follow else list(self.follow)


@pytest.mark.asyncio
async def test_post_forwards_and_relays_a_json_body() -> None:
    """A JSON reply is relayed with the upstream status."""
    body = dump(Response(id=1, result={"ok": True}))
    transport = _ScriptedTransport(httpx.Response(200, content=body))
    proxy = _proxy(transport=transport)
    request = _request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')

    reply = await proxy.handle(request)

    assert reply.status_code == 200
    assert await _body(reply) == body.removesuffix(b"\n")
    assert transport.requests[0].headers["accept"] == "*/*"
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_post_with_a_parse_error_is_forwarded_raw() -> None:
    """A body that is not one message is forwarded untouched."""
    transport = _ScriptedTransport(httpx.Response(200, content=b"raw"))
    proxy = _proxy(transport=transport)
    reply = await proxy.handle(_request("POST", b"{not json}"))
    assert await _body(reply) == b"raw"
    assert transport.requests[0].content == b"{not json}"
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_upstream_failure_is_a_bad_gateway() -> None:
    """An unreachable upstream yields 502 instead of an exception."""
    proxy = _proxy(transport=_FailingTransport())
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == UPSTREAM_FAILED_STATUS
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_get_relays_an_event_stream() -> None:
    """``GET`` relays an SSE body event by event."""

    async def chunks() -> AsyncIterator[bytes]:
        yield b'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/message"}\n\n'

    transport = _ScriptedTransport(
        httpx.Response(200, content=chunks(), headers={"content-type": "text/event-stream"})
    )
    proxy = _proxy(transport=transport)
    reply = await proxy.handle(_request("GET", headers={"Accept": "text/event-stream"}))
    assert reply.status_code == 200
    assert b"notifications/message" in await _body(reply)
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_get_without_a_stream_is_relayed_plainly() -> None:
    """A ``GET`` the upstream answers with JSON relays the JSON body."""
    transport = _ScriptedTransport(httpx.Response(405, content=b"no stream"))
    proxy = _proxy(transport=transport)
    reply = await proxy.handle(_request("GET"))
    assert reply.status_code == 405
    assert await _body(reply) == b"no stream"
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_delete_relays_status_without_a_body() -> None:
    """``DELETE`` keeps the upstream status and drops the body."""
    transport = _ScriptedTransport(httpx.Response(204, content=b"ignored"))
    proxy = _proxy(transport=transport)
    reply = await proxy.handle(_request("DELETE"))
    assert reply.status_code == 204
    assert await _body(reply) == b""
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_reply_to_client_skips_the_upstream() -> None:
    """A stage that answers directly is never sent upstream."""
    answer = Response(id=1, result={"answered": True})
    transport = _ScriptedTransport()
    proxy = _proxy(_SendStage(ReplyToClient(answer)), transport=transport)
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == 200
    assert transport.requests == []
    assert b"answered" in await _body(reply)
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_status_reply_skips_the_upstream() -> None:
    """A ``ReplyWithStatus`` (L04) answers with the bare status (S6)."""
    transport = _ScriptedTransport()
    proxy = _proxy(_SendStage(ReplyWithStatus(503)), transport=transport)
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == 503
    assert await _body(reply) == b""
    assert transport.requests == []
    await proxy.client.aclose()  # type: ignore[union-attr]


def test_hop_by_hop_and_proxy_headers_are_dropped() -> None:
    """``proxy-*`` and hop-by-hop headers leave both directions (S4.1)."""
    headers = {
        "Authorization": "Bearer t",
        "Mcp-Session-Id": "s",
        "Proxy-Authorization": "x",
        "PROXY-Connection": "close",
        "Proxy-Skeptic-Trace": "1",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
        "Upgrade": "h2c",
        "Content-Length": "0",
        "Content-Type": "application/json",
    }
    request_headers = forwarded_request_headers(headers)
    assert request_headers == {
        "Authorization": "Bearer t",
        "Mcp-Session-Id": "s",
        "Content-Type": "application/json",
    }
    response_headers = forwarded_response_headers(headers)
    assert response_headers == {
        "Authorization": "Bearer t",
        "Mcp-Session-Id": "s",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_drop_answers_accepted() -> None:
    """A dropped message leaves the client with 202."""
    transport = _ScriptedTransport()
    proxy = _proxy(_SendStage(Drop()), transport=transport)
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == ACCEPTED_STATUS
    assert transport.requests == []
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_send_to_server_replaces_the_body() -> None:
    """A ``SendToServer`` is sent as the exchange's body."""
    sent = Request(id=1, method="tools/list")
    body = dump(Response(id=1, result={}))
    transport = _ScriptedTransport(httpx.Response(200, content=body))
    proxy = _proxy(_SendStage(SendToServer(sent)), transport=transport)
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == 200
    assert len(transport.requests) == 1
    assert transport.requests[0].content == dump(sent)
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_extra_message_is_sent_in_the_background() -> None:
    """A second message of an exchange goes upstream out of band."""
    body = dump(Response(id=1, result={}))
    transport = _ScriptedTransport(
        httpx.Response(200, content=body), httpx.Response(200, content=b"")
    )
    extra = Notification(method="notifications/tools/list_changed")
    proxy = _proxy(_Later(extra), transport=transport)
    reply = await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))
    assert reply.status_code == 200
    await asyncio.gather(*proxy._background, return_exceptions=True)
    assert len(transport.requests) == 2
    await proxy.client.aclose()  # type: ignore[union-attr]


class _Later(RecorderStage):
    """Forward the reply, then ask for one extra message upstream."""

    def __init__(self, msg: Any) -> None:
        """Store the extra message.

        Args:
            msg: The message to send after the reply.
        """
        self.msg = msg

    async def on_s2c(self, msg: Any, ctx: EpisodeContext) -> list[Any]:
        """Forward, then queue the extra message.

        Args:
            msg: The server message.
            ctx: The episode context.

        Returns:
            The forward and the extra action.
        """
        del ctx
        return [Forward(msg), SendToServer(self.msg)]


@pytest.mark.asyncio
async def test_zero_hold_applies_the_follow_up_at_once() -> None:
    """A hold without a delay runs its follow-up immediately."""
    proxy = _proxy(transport=_ScriptedTransport())
    request = Request(id=1, method="tools/list")
    result = await proxy._wait(Hold(ms=0, then=Forward(request)))
    assert isinstance(result, Forward)
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_cancelled_hold_is_dropped() -> None:
    """A cancellation of the held request replaces the reply with ``Drop``."""
    proxy = _proxy(transport=_ScriptedTransport())
    request = Request(id=5, method="tools/call")
    task = asyncio.create_task(proxy._wait(Hold(ms=500, then=Forward(request), unless_cancelled=5)))
    await asyncio.sleep(0)
    proxy._remember(Notification(method="notifications/cancelled", params={"requestId": 5}))
    assert isinstance(await task, Drop)
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_hold_expiry_keeps_its_follow_up() -> None:
    """An uncancelled hold returns its follow-up after the delay."""
    proxy = _proxy(transport=_ScriptedTransport())
    request = Request(id=6, method="tools/call")
    result = await proxy._wait(Hold(ms=1, then=Forward(request), unless_cancelled=6))
    assert isinstance(result, Forward)
    assert 6 not in proxy._cancelled
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_era_comes_from_the_header() -> None:
    """The ``Mcp-Protocol-Version`` header fixes the era (S4.2)."""
    body = dump(Response(id=1, result={}))
    transport = _ScriptedTransport(httpx.Response(200, content=body))
    proxy = _proxy(transport=transport)
    await proxy.handle(
        _request(
            "POST",
            b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
            headers={"Mcp-Protocol-Version": "2026-07-28"},
        )
    )
    assert proxy.ctx.era.kind == "MODERN"
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_era_comes_from_the_first_message() -> None:
    """Without the header the first client message decides the era."""
    body = dump(Response(id=1, result={}))
    transport = _ScriptedTransport(httpx.Response(200, content=body))
    proxy = _proxy(transport=transport)
    await proxy.handle(
        _request(
            "POST",
            b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}',
        )
    )
    assert proxy.ctx.era.version == "2025-11-25"
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_stream_with_a_non_message_event() -> None:
    """A keep-alive comment in an event stream is relayed untouched."""

    async def chunks() -> AsyncIterator[bytes]:
        yield b": ping\n\n"

    transport = _ScriptedTransport(
        httpx.Response(200, content=chunks(), headers={"content-type": "text/event-stream"})
    )
    proxy = _proxy(transport=transport)
    reply = await proxy.handle(_request("GET"))
    assert await _body(reply) == b""
    await proxy.client.aclose()  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_stream_fault_reply_is_framed_as_an_event() -> None:
    """A ``ReplyToClient`` inside a stream becomes its own event."""
    answer = Response(id=2, result={"guarded": True})

    async def chunks() -> AsyncIterator[bytes]:
        yield b'data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'

    transport = _ScriptedTransport(
        httpx.Response(200, content=chunks(), headers={"content-type": "text/event-stream"})
    )
    proxy = _proxy(_StreamReply(answer), transport=transport)
    reply = await proxy.handle(_request("GET"))
    assert b"event: message\ndata: " in await _body(reply)
    await proxy.client.aclose()  # type: ignore[union-attr]


class _StreamReply(RecorderStage):
    """Answer every s2c message directly, as a Guard loudify would."""

    def __init__(self, answer: Any) -> None:
        """Store the answer.

        Args:
            answer: The message to send the client.
        """
        self.answer = answer

    async def on_s2c(self, msg: Any, ctx: EpisodeContext) -> list[Any]:
        """Replace the reply.

        Args:
            msg: The server message.
            ctx: The episode context.

        Returns:
            The direct reply.
        """
        del msg, ctx
        return [ReplyToClient(self.answer)]


@pytest.mark.asyncio
async def test_stream_without_a_client_fails_when_not_serving() -> None:
    """Using the proxy before its lifespan opens it is a programming error."""
    proxy = HttpProxy("http://upstream.test/mcp")
    with pytest.raises(RuntimeError, match="not serving"):
        await proxy.handle(_request("POST", b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'))


def test_helpers() -> None:
    """The content-type helpers read names case-insensitively."""
    assert _is_sse({"Content-Type": "text/event-stream; charset=utf-8"})
    assert not _is_sse({"Content-Type": "application/json"})
    assert not _is_sse({})
    assert _is_json("Content-Length")
    assert not _is_json("accept")
    assert _text(Response(id=1, result={})) == '{"jsonrpc":"2.0","id":1,"result":{}}'


def test_app_serves_the_mcp_path() -> None:
    """The app exposes one route for the three methods of S4.1."""
    app = HttpProxy("http://upstream.test/mcp").app()
    route = app.routes[0]
    assert route.path == MCP_PATH
    assert set(getattr(route, "methods", ())) >= {"GET", "POST", "DELETE"}


def test_run_delegates_to_the_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run_http_proxy`` builds the proxy with its arguments and serves it."""
    seen: dict[str, Any] = {}

    def fake_run(self: HttpProxy, *, host: str = "", port: int = 0) -> None:
        """Record the call.

        Args:
            self: The proxy.
            host: The listen address.
            port: The listen port.
        """
        seen.update(upstream=self.upstream, host=host, port=port, episode=self.ctx.episode_id)

    monkeypatch.setattr(HttpProxy, "run", fake_run)
    run_http_proxy("http://upstream.test/mcp", host="0.0.0.0", port=9, episode_id="ep-9")
    assert seen == {
        "upstream": "http://upstream.test/mcp",
        "host": "0.0.0.0",
        "port": 9,
        "episode": "ep-9",
    }


def test_exchange_keeps_its_parts() -> None:
    """The exchange dataclass carries method, headers and body."""
    exchange = _Exchange("POST", {"a": "b"}, b"x")
    assert (exchange.method, exchange.headers, exchange.body) == ("POST", {"a": "b"}, b"x")
