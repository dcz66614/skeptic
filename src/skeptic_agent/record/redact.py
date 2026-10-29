"""Redaction of secrets before a message is written to a cassette (1.7, S5).

Recording is redacted by default: the ``Authorization`` and ``Cookie`` request
headers, and the value of every key whose name matches a secret-looking pattern,
are replaced by ``"***"``. The same rule applies to ``raw`` and ``final``.
"""

import re
from typing import Any

REDACTED: str = "***"
"""What every secret value is replaced with (1.7)."""

SECRET_HEADERS: frozenset[str] = frozenset({"authorization", "cookie"})
"""The request headers that are always redacted, compared lower-cased (1.7)."""

SECRET_KEY_PATTERN: re.Pattern[str] = re.compile(r"(?i)(api[_-]?key|token|secret|password)")
"""A key name that holds a secret; 1.7 matches this anywhere in the name."""

HEADERS_KEY: str = "headers"
"""The key whose object value is a whole header table, not a payload (1.7)."""


def _secret_key(name: str) -> bool:
    """Report whether a key name marks the value under it as a secret.

    Args:
        name: The JSON object key.

    Returns:
        ``True`` when 1.7's pattern matches anywhere in the name.
    """
    return SECRET_KEY_PATTERN.search(name) is not None


def _redact_headers(headers: dict[Any, Any]) -> dict[Any, Any]:
    """Replace the secret header values of one header table.

    Args:
        headers: A header table, name to value.

    Returns:
        A copy whose ``Authorization`` and ``Cookie`` values are ``"***"``.
    """
    return {
        name: REDACTED
        if isinstance(name, str) and name.lower() in SECRET_HEADERS
        else _redact(value)
        for name, value in headers.items()
    }


def _redact(value: Any) -> Any:
    """Redact one JSON value, recursing through objects and arrays.

    A key that matches the secret pattern loses its whole value; the object
    under ``headers`` is redacted as a header table. Keys are never renamed and
    the walk never mutates its input.

    Args:
        value: Any decoded JSON value.

    Returns:
        A redacted copy.
    """
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _secret_key(key):
                redacted[key] = REDACTED
            elif key == HEADERS_KEY and isinstance(item, dict):
                redacted[key] = _redact_headers(item)
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def redact(value: Any) -> Any:
    """Return a redacted copy of a decoded JSON value (1.7).

    Args:
        value: Any decoded JSON value, typically ``raw`` or ``final``.

    Returns:
        The same shape with every secret value replaced by ``"***"``.
    """
    return _redact(value)
