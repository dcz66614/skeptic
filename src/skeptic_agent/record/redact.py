"""Redaction of secrets before a message is written to a cassette (1.7, S5).

Recording is redacted by default: the ``Authorization``, ``Cookie`` and
``Set-Cookie`` headers, and the value under every key whose name matches a
secret-looking pattern, are replaced by ``"***"``. One name test decides both,
names are matched case-insensitively at every depth, and the rule applies to
``raw`` and ``final`` alike.
"""

import re
from typing import Any

REDACTED: str = "***"
"""What every secret value is replaced with (1.7)."""

SECRET_HEADERS: frozenset[str] = frozenset({"authorization", "cookie", "set-cookie"})
"""The headers that are always redacted, compared lower-cased (1.7)."""

SECRET_KEY_PATTERN: re.Pattern[str] = re.compile(r"(?i)(api[_-]?key|token|secret|password)")
"""A key name that holds a secret; 1.7 matches this anywhere in the name."""


def _secret_key(name: str) -> bool:
    """Report whether a key or header name marks the value under it as a secret.

    This is the one test 1.7 uses everywhere: a header table and an ordinary
    object are treated the same, so an ``Authorization`` header, an
    ``X-Api-Key`` header, an ``arguments.Authorization`` member and a nested
    ``auth.password`` all redact. Names are compared lower-cased.

    Args:
        name: The JSON object key or the header name.

    Returns:
        ``True`` when the name is a secret header or 1.7's pattern matches
        anywhere in it.
    """
    lowered = name.lower()
    return lowered in SECRET_HEADERS or SECRET_KEY_PATTERN.search(lowered) is not None


def _redact(value: Any) -> Any:
    """Redact one JSON value, recursing through objects and arrays.

    A key that matches the secret test loses its whole value; every other key
    is kept and its value walked. The object under a ``headers`` key is walked
    the same way, so its header names hit the same test. Keys are never renamed
    and the walk never mutates its input.

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
