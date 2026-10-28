"""JSON-RPC 2.0 message model and the MCP line framing.

Every parsed message keeps its original line bytes in ``raw_bytes`` so that an
unmodified message can be forwarded verbatim. Batch requests are not supported:
MCP removed them on 2025-06-18, so a top-level JSON array is a parse error.
"""

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

JSONRPC_VERSION: Literal["2.0"] = "2.0"


def _keep_id(value: int | str | None) -> int | str | None:
    """Return an id unchanged, so a string id is never coerced to an integer.

    Args:
        value: An integer, string or null message id.

    Returns:
        The same value.
    """
    return value


# Old-style aliases keep `Message` usable with `isinstance`. UP040's `type`
# statement would turn it into a PEP 695 alias, which isinstance rejects.
MessageId: TypeAlias = Annotated[int | str, AfterValidator(_keep_id)]  # noqa: UP040
NullableId: TypeAlias = Annotated[int | str | None, AfterValidator(_keep_id)]  # noqa: UP040


class _MessageBase(BaseModel):
    """Settings and framing fields shared by every JSON-RPC message."""

    model_config = ConfigDict(frozen=True, extra="allow")

    jsonrpc: Literal["2.0"] = JSONRPC_VERSION
    raw_bytes: bytes = Field(default=b"", repr=False)


class Request(_MessageBase):
    """A JSON-RPC request that expects a response."""

    id: MessageId
    method: str
    params: dict[str, Any] | list[Any] | None = None


class Notification(_MessageBase):
    """A JSON-RPC notification that expects no response."""

    method: str
    params: dict[str, Any] | list[Any] | None = None


class Response(_MessageBase):
    """A successful JSON-RPC response."""

    id: NullableId
    result: Any


class ErrorObject(BaseModel):
    """The ``error`` member of a JSON-RPC error response."""

    model_config = ConfigDict(frozen=True, extra="allow")

    code: int
    message: str
    data: Any = None


class ErrorResponse(_MessageBase):
    """A JSON-RPC error response."""

    id: NullableId
    error: ErrorObject


Message: TypeAlias = Request | Notification | Response | ErrorResponse  # noqa: UP040


@dataclass(frozen=True)
class ParseError:
    """A line that is not a supported JSON-RPC message.

    Attributes:
        raw_bytes: The line as received, without its trailing newline.
        reason: A short description of why the line was rejected.
    """

    raw_bytes: bytes
    reason: str


def _build_message(value: dict[str, Any]) -> Message:
    """Build the message variant selected by the object's members.

    Args:
        value: A decoded JSON object that already carries ``jsonrpc`` 2.0.

    Returns:
        The parsed message.

    Raises:
        ValidationError: When the object does not match any message variant.
    """
    if "method" in value:
        if "id" in value:
            return Request.model_validate(value)
        return Notification.model_validate(value)
    if "error" in value:
        return ErrorResponse.model_validate(value)
    if "result" in value:
        return Response.model_validate(value)
    return Request.model_validate(value)


def parse_line(line: bytes) -> Message | ParseError:
    """Parse one newline-terminated JSON-RPC message.

    A trailing ``\\n`` or ``\\r\\n`` is stripped before decoding. Invalid JSON,
    non-object values, arrays (batches), a missing or wrong ``jsonrpc`` version
    and structurally invalid messages all return a ``ParseError`` instead of
    raising.

    Args:
        line: One raw line, with or without its terminator.

    Returns:
        The parsed message, or a ``ParseError`` describing the rejection.
    """
    raw_bytes = line.removesuffix(b"\n").removesuffix(b"\r")
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ParseError(raw_bytes=raw_bytes, reason=f"invalid UTF-8: {exc.reason}")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return ParseError(raw_bytes=raw_bytes, reason=f"invalid JSON: {exc.msg}")
    if not isinstance(value, dict):
        return ParseError(raw_bytes=raw_bytes, reason="message must be a JSON object")
    if value.get("jsonrpc") != JSONRPC_VERSION:
        return ParseError(raw_bytes=raw_bytes, reason=f"jsonrpc must be {JSONRPC_VERSION!r}")
    try:
        message = _build_message(value)
    except ValidationError as exc:
        return ParseError(raw_bytes=raw_bytes, reason=f"invalid message: {exc.errors()}")
    return message.model_copy(update={"raw_bytes": raw_bytes})


def dump(msg: Message) -> bytes:
    """Serialize a message in the compact S4.1 form.

    The payload always carries ``jsonrpc`` 2.0, omits ``params`` when it is
    ``None`` and never includes ``raw_bytes``.

    Args:
        msg: The message to serialize.

    Returns:
        The compact UTF-8 JSON bytes followed by ``b"\\n"``.

    Raises:
        TypeError: When the payload holds a value JSON cannot encode.
    """
    payload = msg.model_dump()
    payload.pop("raw_bytes", None)
    if payload.get("params") is None:
        payload.pop("params", None)
    payload["jsonrpc"] = JSONRPC_VERSION
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
