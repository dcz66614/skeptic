"""Streamable HTTP proxy: relay one MCP connection through the pipeline (S2, S4.1).

The client talks to ``POST /mcp``, ``GET /mcp`` and ``DELETE /mcp`` on our
Starlette app. Every request body is forwarded to the upstream with
``httpx.AsyncClient``, and every response body goes back to the client through
the same ``Pipeline`` the stdio proxy uses. A JSON response is processed as one
message; a ``text/event-stream`` response is processed event by event, so a
long-running upstream stream is not buffered before its messages reach the
pipeline.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request as HttpRequest
from starlette.responses import Response as HttpResponse
from starlette.responses import StreamingResponse
from starlette.routing import Route

from skeptic_agent.jsonrpc import Message, ParseError, Request, dump, parse_line
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
from skeptic_agent.proxy.sse import SseDecoder, SseEvent, encode_event

MCP_PATH: str = "/mcp"
"""The single path the proxy serves (S4.1)."""

JSON_CONTENT_TYPE: str = "application/json"
"""The content type of a single JSON-RPC response."""

SSE_CONTENT_TYPE: str = "text/event-stream"
"""The content type of a streamed response (S4.1)."""

HOP_BY_HOP_HEADERS: frozenset[str] = frozenset(
    {
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
    }
)
"""The hop-by-hop headers that are never relayed in either direction (S4.1)."""

REQUEST_HEADERS_TO_DROP: frozenset[str] = HOP_BY_HOP_HEADERS | {"host", "content-length"}
"""Request headers rebuilt for the upstream: hop-by-hop ones and the framing ones."""

CONNECT_TIMEOUT_SECONDS: float = 30.0
"""How long to wait for the upstream to accept a connection."""

UPSTREAM_FAILED_STATUS: int = 502
"""The status sent when the upstream cannot be reached at all."""

ACCEPTED_STATUS: int = 202
"""The status sent when the pipeline dropped every reply of a request."""


def forwarded_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Drop the hop-by-hop and framing headers from a client's request headers.

    ``Authorization`` and the ``Mcp-*`` headers are kept (S4.1). ``Host`` and
    ``Content-Length`` describe the upstream connection and body, so httpx sets
    them itself.

    Args:
        headers: The client request headers.

    Returns:
        The headers to send upstream.
    """
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in REQUEST_HEADERS_TO_DROP
    }


def forwarded_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Drop the hop-by-hop and framing headers from an upstream response.

    The body is re-framed for the client, so ``Content-Length`` is dropped too.

    Args:
        headers: The upstream response headers.

    Returns:
        The headers to send the client.
    """
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length"
    }


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Return one header value, matched case-insensitively.

    Args:
        headers: The headers to search.
        name: The lower-case header name.

    Returns:
        The value, or ``None`` when absent.
    """
    for header_name, value in headers.items():
        if header_name.lower() == name:
            return value
    return None


def _is_sse(headers: Mapping[str, str]) -> bool:
    """Report whether a response is an event stream.

    Args:
        headers: The upstream response headers.

    Returns:
        ``True`` when the content type is ``text/event-stream``.
    """
    value = _header(headers, "content-type")
    return value is not None and value.split(";", 1)[0].strip().lower() == SSE_CONTENT_TYPE


def _text(msg: Message) -> str:
    """Serialize a message for a JSON body or an SSE ``data`` line.

    Args:
        msg: The message to serialize.

    Returns:
        The message's original bytes when untouched (S4.1), else the compact
        JSON, without the trailing newline.
    """
    raw = msg.raw_bytes
    return (raw if raw else dump(msg).removesuffix(b"\n")).decode("utf-8")


@dataclass(frozen=True)
class _Exchange:
    """What the upstream needs to answer one client request.

    Attributes:
        method: The HTTP method the client used.
        headers: The client request headers, framed for the upstream.
        body: The raw client request body.
    """

    method: str
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class _Reply:
    """The outcome of a set of pipeline actions.

    Attributes:
        message: The message to send the client itself, or ``None``.
        upstream: The upstream response to relay, or ``None``.
    """

    message: Message | None = None
    upstream: httpx.Response | None = None


class HttpProxy:
    """Relay a client's streamable HTTP MCP connection to an upstream URL.

    Attributes:
        upstream: The upstream MCP endpoint.
        ctx: The episode context shared by every stage and every request.
        client: The HTTP client once the app is served.
    """

    def __init__(
        self,
        upstream: str,
        pipeline: Pipeline | None = None,
        *,
        episode_id: str = "http",
        seed: int = 0,
    ) -> None:
        """Prepare a proxy for one episode.

        Args:
            upstream: The upstream MCP endpoint URL.
            pipeline: The pipeline to use, or ``None`` for one with no-op stages.
            episode_id: The episode identifier.
            seed: The episode seed.
        """
        self.upstream = upstream
        self.pipeline = pipeline if pipeline is not None else new_pipeline()
        self.ctx = EpisodeContext(episode_id=episode_id, seed=seed, era=UNKNOWN)
        self.client: httpx.AsyncClient | None = None
        self._cancelled: dict[int | str, asyncio.Event] = {}
        """Requests the client cancelled while their reply was held (L01)."""
        self._background: set[asyncio.Task[None]] = set()
        """Upstream exchanges no client is waiting for; closed with the app."""

    def app(self) -> Starlette:
        """Build the Starlette app that serves ``/mcp``.

        Returns:
            The app, with one route for the three methods of S4.1.
        """
        return Starlette(
            routes=[Route(MCP_PATH, self.handle, methods=["GET", "POST", "DELETE"])],
            lifespan=self._lifespan,
        )

    @contextlib.asynccontextmanager
    async def _lifespan(self, app: Any) -> AsyncIterator[None]:
        """Open the HTTP client for the serving window and close it after.

        Args:
            app: The Starlette app, unused.

        Yields:
            Nothing; the app serves requests while this is open.
        """
        del app
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(CONNECT_TIMEOUT_SECONDS, read=None))
        try:
            yield
        finally:
            for task in list(self._background):
                task.cancel()
            await asyncio.gather(*self._background, return_exceptions=True)
            await self.client.aclose()
            self.client = None

    def run(self, *, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Serve the app until the process is stopped (S2).

        Args:
            host: The listen address.
            port: The listen port.
        """
        uvicorn.run(self.app(), host=host, port=port, proxy_headers=False)

    async def handle(self, request: HttpRequest) -> HttpResponse:
        """Handle one ``/mcp`` request.

        Args:
            request: The client request.

        Returns:
            The client response: JSON, an event stream, or an empty body.
        """
        if request.method == "POST":
            return await self._post(request)
        if request.method == "DELETE":
            return await self._delete(request)
        return await self._get(request)

    async def _read(self, request: HttpRequest) -> _Exchange:
        """Read a client request into the shape the upstream needs.

        Args:
            request: The client request.

        Returns:
            The exchange to forward.
        """
        return _Exchange(
            method=request.method,
            headers=forwarded_request_headers(request.headers),
            body=await request.body(),
        )

    async def _post(self, request: HttpRequest) -> HttpResponse:
        """Forward a client message and relay the upstream reply.

        A body that is not one JSON-RPC message is forwarded untouched, exactly
        as the stdio proxy forwards unparseable lines.

        Args:
            request: The client request.

        Returns:
            The client response.
        """
        exchange = await self._read(request)
        msg = parse_line(exchange.body)
        if isinstance(msg, ParseError):
            return await self._relay(await self._send(exchange))
        self._detect_era(msg, exchange.headers)
        self._remember(msg)
        actions = await self.pipeline.on_c2s(msg, self.ctx)
        return await self._respond(exchange, actions)

    async def _get(self, request: HttpRequest) -> HttpResponse:
        """Relay the upstream event stream, pipeline-processing every event.

        Args:
            request: The client request.

        Returns:
            The event stream, or the upstream response when it is not one.
        """
        exchange = await self._read(request)
        return await self._relay(await self._send(exchange))

    async def _delete(self, request: HttpRequest) -> HttpResponse:
        """Relay the client's session teardown; its body carries no messages.

        Args:
            request: The client request.

        Returns:
            The upstream status with an empty body.
        """
        exchange = await self._read(request)
        reply = await self._send(exchange)
        headers = forwarded_response_headers(reply.headers)
        await reply.aclose()
        return HttpResponse(status_code=reply.status_code, headers=headers)

    def _detect_era(self, msg: Message, headers: Mapping[str, str]) -> None:
        """Detect the era from the request header or the first message (S4.2).

        Args:
            msg: The parsed client message.
            headers: The forwarded request headers.
        """
        if self.ctx.era is UNKNOWN and isinstance(msg, Request):
            self.ctx.era = detect_era(msg, headers)

    def _remember(self, msg: Message) -> None:
        """Record a client cancellation of a held request (L01).

        Args:
            msg: A client message.
        """
        request_id = cancelled_id(msg)
        if request_id is None:
            return
        event = self._cancelled.get(request_id)
        if event is not None:
            event.set()

    def _build(self, exchange: _Exchange, msg: Message) -> httpx.Request:
        """Build the upstream request for one message.

        Args:
            exchange: The client request being answered.
            msg: The message to send; its body replaces the client's.

        Returns:
            The upstream request.

        Raises:
            RuntimeError: When the app is not being served.
        """
        if self.client is None:
            raise RuntimeError("http proxy is not serving")
        headers = {key: value for key, value in exchange.headers.items() if not _is_json(key)}
        return self.client.build_request(
            exchange.method, self.upstream, headers=headers, content=dump(msg)
        )

    async def _send(self, exchange: _Exchange, msg: Message | None = None) -> httpx.Response:
        """Send a client request upstream, or a rewritten version of it.

        Args:
            exchange: The client request.
            msg: The message to send instead of the client's body, or ``None``
                to send the body unchanged.

        Returns:
            The upstream response, with its body not consumed yet.
        """
        if self.client is None:
            raise RuntimeError("http proxy is not serving")
        try:
            if msg is None:
                request = self.client.build_request(
                    exchange.method,
                    self.upstream,
                    headers=exchange.headers,
                    content=exchange.body,
                )
            else:
                request = self._build(exchange, msg)
            return await self.client.send(request, stream=True)
        except httpx.HTTPError:
            return httpx.Response(UPSTREAM_FAILED_STATUS)

    def _spawn(self, exchange: _Exchange, msg: Message) -> None:
        """Send an exchange upstream without a client waiting for its reply.

        Args:
            exchange: The client request the message belongs to.
            msg: The message to send.
        """

        async def run() -> None:
            """Send the message and discard the reply."""
            reply = await self._send(exchange, msg)
            await reply.aclose()

        task = asyncio.create_task(run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _relay(self, reply: httpx.Response) -> HttpResponse:
        """Relay an upstream response, pipeline-processing a JSON body.

        Args:
            reply: The upstream response.

        Returns:
            The client response.
        """
        headers = forwarded_response_headers(reply.headers)
        if _is_sse(reply.headers):
            return self._stream(reply, headers)
        try:
            body = b"".join([chunk async for chunk in reply.aiter_bytes()])
        finally:
            await reply.aclose()
        status = reply.status_code
        msg = parse_line(body)
        if isinstance(msg, ParseError):
            return HttpResponse(content=body, status_code=status, headers=headers)
        actions = await self.pipeline.on_s2c(msg, self.ctx)
        message = await self._s2c_result(actions)
        if message is None:
            return HttpResponse(status_code=ACCEPTED_STATUS)
        content = _text(message).encode("utf-8") if message.raw_bytes else body
        return HttpResponse(content=content, status_code=status, media_type=JSON_CONTENT_TYPE)

    async def _s2c_result(self, actions: list[Action]) -> Message | None:
        """Pick the message a set of s2c actions sends the client.

        The upstream response is already in hand, so a ``Forward`` keeps it and
        only a ``ReplyToClient`` replaces it. A ``Drop`` or a held reply the
        client cancelled sends nothing; extra ``SendToServer`` actions go out
        in the background.

        Args:
            actions: The pipeline actions.

        Returns:
            The message to send, or ``None`` when nothing should be sent.
        """
        message: Message | None = None
        for action in actions:
            if isinstance(action, Hold):
                action = await self._wait(action)
            if isinstance(action, Forward):
                if message is None:
                    message = action.msg
            elif isinstance(action, SendToServer):
                self._spawn(_Exchange("POST", {}, b""), action.msg)
            elif isinstance(action, ReplyToClient):
                if message is None:
                    message = action.msg
            elif isinstance(action, Drop):
                return None
        return message

    async def _respond(self, exchange: _Exchange, actions: list[Action]) -> HttpResponse:
        """Turn the c2s actions into the client's response.

        Args:
            exchange: The client request.
            actions: The pipeline actions.

        Returns:
            The client response.
        """
        result = await self._collect(exchange, actions)
        if result.message is not None:
            return HttpResponse(
                content=_text(result.message), status_code=200, media_type=JSON_CONTENT_TYPE
            )
        if result.upstream is None:
            return HttpResponse(status_code=ACCEPTED_STATUS)
        return await self._relay(result.upstream)

    async def _collect(self, exchange: _Exchange, actions: list[Action]) -> _Reply:
        """Run the actions until the exchange's reply is known.

        The upstream sends at most one message per exchange, so a second one is
        an internal exchange and is sent upstream in the background.

        Args:
            exchange: The client request the actions answer.
            actions: The pipeline actions.

        Returns:
            The message to send or the upstream response to relay.
        """
        message: Message | None = None
        upstream: httpx.Response | None = None
        for action in actions:
            if isinstance(action, Hold):
                action = await self._wait(action)
            if isinstance(action, Forward):
                if message is None and upstream is None:
                    upstream = await self._send(exchange)
            elif isinstance(action, SendToServer):
                if message is None and upstream is None:
                    upstream = await self._send(exchange, action.msg)
                else:
                    self._spawn(exchange, action.msg)
            elif isinstance(action, ReplyToClient) and message is None and upstream is None:
                message = action.msg
            elif isinstance(action, Drop):
                continue
        return _Reply(message=message, upstream=upstream)

    async def _wait(self, action: Hold) -> Action:
        """Sleep out a held action, or stop early when its request is cancelled.

        A ``Hold`` with ``unless_cancelled`` belongs to one request id. When the
        client confirms the cancellation with a ``notifications/cancelled`` on a
        later request, the follow-up is replaced by ``Drop``, so the cancelled
        call gets no reply (L01, as on stdio).

        Args:
            action: The hold to wait out.

        Returns:
            The action to apply after the wait.
        """
        request_id = action.unless_cancelled
        if request_id is None or action.ms <= 0:
            await asyncio.sleep(action.ms / 1000)
            return action.then
        event = asyncio.Event()
        self._cancelled[request_id] = event
        try:
            deadline = asyncio.get_running_loop().time() + action.ms / 1000
            while not event.is_set():
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return action.then
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), remaining)
            return Drop()
        finally:
            self._cancelled.pop(request_id, None)

    def _stream(self, reply: httpx.Response, headers: dict[str, str]) -> HttpResponse:
        """Relay an event stream, pipeline-processing every event as it arrives.

        Args:
            reply: The upstream event-stream response.
            headers: The headers to send the client.

        Returns:
            The client event stream.
        """
        decoder = SseDecoder()

        async def emit() -> AsyncIterator[bytes]:
            """Decode the upstream events and write the ones the pipeline keeps.

            Yields:
                The encoded client events.
            """
            try:
                async for chunk in reply.aiter_bytes():
                    for event in decoder.feed(chunk):
                        async for outgoing in self._event(event):
                            yield encode_event(outgoing)
                for event in decoder.close():
                    async for outgoing in self._event(event):
                        yield encode_event(outgoing)
            finally:
                await reply.aclose()

        return StreamingResponse(
            emit(),
            status_code=reply.status_code,
            headers=headers,
            media_type=SSE_CONTENT_TYPE,
        )

    async def _event(self, event: SseEvent) -> AsyncIterator[SseEvent]:
        """Run one event through the pipeline on the s2c side.

        An event that is not a JSON-RPC message (a keep-alive comment, or a
        body the P10 model rejects) is relayed untouched.

        Args:
            event: The decoded event.

        Yields:
            The events to send the client.
        """
        msg = parse_line(event.data.encode("utf-8"))
        if isinstance(msg, ParseError):
            yield event
            return
        actions = await self.pipeline.on_s2c(msg, self.ctx)
        for action in actions:
            if isinstance(action, Hold):
                action = await self._wait(action)
            if isinstance(action, Forward):
                yield SseEvent(
                    data=_text(action.msg),
                    event=event.event or "message",
                    event_id=event.event_id,
                )
            elif isinstance(action, ReplyToClient):
                yield SseEvent(data=_text(action.msg), event="message", event_id=event.event_id)
            elif isinstance(action, SendToServer):
                self._spawn(_Exchange("POST", {}, b""), action.msg)


def _is_json(name: str) -> bool:
    """Report whether a header describes the body httpx is about to set.

    Args:
        name: A header name.

    Returns:
        ``True`` for ``content-type`` and ``content-length``.
    """
    return name.lower() in {"content-type", "content-length"}


def run_http_proxy(
    upstream: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    pipeline: Pipeline | None = None,
    episode_id: str = "http",
    seed: int = 0,
) -> None:
    """Serve the HTTP proxy until the process is stopped (S2).

    Args:
        upstream: The upstream MCP endpoint URL.
        host: The listen address.
        port: The listen port.
        pipeline: The pipeline to use, or ``None`` for one with no-op stages.
        episode_id: The episode identifier.
        seed: The episode seed.
    """
    HttpProxy(upstream, pipeline, episode_id=episode_id, seed=seed).run(host=host, port=port)
