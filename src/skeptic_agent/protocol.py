"""MCP protocol era detection.

An era records which generation of the MCP protocol a client speaks, so that the
proxy can pick the right rules. Detection follows S4.2 exactly: an explicit HTTP
header wins, otherwise the first client message is inspected.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from skeptic_agent.jsonrpc import Notification, Request

MODERN_SINCE: str = "2026-07-28"
"""The first protocol version that counts as MODERN."""

PROTOCOL_VERSION_HEADER: str = "mcp-protocol-version"
"""The HTTP header that carries the protocol version."""

PROTOCOL_VERSION_META_KEY: str = "io.modelcontextprotocol/protocolVersion"
"""The ``params._meta`` key that carries the protocol version."""

EraKind = Literal["LEGACY", "MODERN", "UNKNOWN"]


@dataclass(frozen=True)
class Era:
    """The protocol generation a client speaks.

    Attributes:
        kind: One of ``LEGACY``, ``MODERN`` or ``UNKNOWN``.
        version: The version string, or ``None`` for ``UNKNOWN``.
    """

    kind: EraKind
    version: str | None


UNKNOWN: Era = Era(kind="UNKNOWN", version=None)
"""The era used when neither the header nor the message names a version."""


def _params_dict(message: Request | Notification) -> dict[str, Any]:
    """Return the message params when they are an object.

    Args:
        message: A parsed request or notification.

    Returns:
        The params object, or an empty dict for ``None`` or an array.
    """
    if isinstance(message.params, dict):
        return message.params
    return {}


def _detect_from_header(era_version: str) -> Era:
    """Classify a version string into a modern or legacy era.

    Args:
        era_version: The version string taken from the header.

    Returns:
        ``MODERN`` when the version is at least ``2026-07-28``, else ``LEGACY``.
    """
    if era_version >= MODERN_SINCE:
        return Era(kind="MODERN", version=era_version)
    return Era(kind="LEGACY", version=era_version)


def detect_era(
    first_client_message: Request | Notification,
    http_headers: Mapping[str, str] | None = None,
) -> Era:
    """Detect the protocol era from HTTP headers and the first client message.

    Header names are matched case-insensitively, and a header wins over the
    message body. Version strings are compared lexicographically, which matches
    chronological order for ``YYYY-MM-DD``.

    Args:
        first_client_message: The first message the client sends upstream.
        http_headers: The HTTP request headers, if the transport has them.

    Returns:
        The detected era.
    """
    if http_headers:
        lowered = MappingProxyType({name.lower(): value for name, value in http_headers.items()})
        if PROTOCOL_VERSION_HEADER in lowered:
            return _detect_from_header(lowered[PROTOCOL_VERSION_HEADER])
    message = first_client_message
    if message.method == "initialize":
        return Era(kind="LEGACY", version=_params_dict(message).get("protocolVersion"))
    if message.method == "server/discover":
        return Era(kind="MODERN", version=MODERN_SINCE)
    meta = _params_dict(message).get("_meta")
    if isinstance(meta, dict) and PROTOCOL_VERSION_META_KEY in meta:
        return Era(kind="MODERN", version=meta[PROTOCOL_VERSION_META_KEY])
    return UNKNOWN
