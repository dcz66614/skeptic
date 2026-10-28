"""JSONPath helpers for fault injection (S6).

Thin wrappers over ``jsonpath-ng`` that the fault implementations share: read or
write the first match of a path, walk every leaf in insertion order, and find the
"first numeric leaf" defined by S6.
"""

import re
from collections.abc import Iterator
from typing import Any

from jsonpath_ng.jsonpath import JSONPath
from jsonpath_ng.parser import parse

_NUMERIC_KEY_EXCLUDED = re.compile(r"(?i)(^id$|_id$|count|index|page|limit|year)")
"""Key names that never select the first numeric leaf (S6)."""


def _path(expression: str) -> JSONPath:
    """Parse a JSONPath expression.

    Args:
        expression: A JSONPath such as ``$.max_c``.

    Returns:
        The parsed expression.
    """
    return parse(expression)


def get_first(data: Any, expression: str) -> Any:
    """Return the value of the first match of a JSONPath.

    Args:
        data: The JSON-compatible document.
        expression: A JSONPath.

    Returns:
        The first matched value, or ``None`` when the path matches nothing.
    """
    matches = _path(expression).find(data)
    return matches[0].value if matches else None


def set_first(data: Any, expression: str, value: Any) -> bool:
    """Replace the first match of a JSONPath in place.

    Args:
        data: The JSON-compatible document; containers on the path are mutated.
        expression: A JSONPath.
        value: The new value.

    Returns:
        ``True`` when a match was replaced, ``False`` when nothing matched.
    """
    match = _path(expression).find(data)
    if not match:
        return False
    match[0].full_path.update(data, value)
    return True


def iter_leaves(data: Any) -> Iterator[tuple[str, Any]]:
    """Yield every leaf in insertion-order depth-first traversal.

    A leaf is a value that is not a ``dict`` or a ``list``. The paired string is
    a JSONPath that addresses the leaf, so ``get_first`` and ``set_first`` work
    on it directly.

    Args:
        data: The JSON-compatible document.

    Yields:
        ``(path, value)`` for each leaf, parents before children.
    """
    yield from _walk(data, "$")


def _walk(value: Any, path: str) -> Iterator[tuple[str, Any]]:
    """Recurse through a value in insertion order.

    Args:
        value: The current value.
        path: The JSONPath of ``value``.

    Yields:
        ``(path, value)`` for each leaf.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if isinstance(item, (dict, list)):
                yield from _walk(item, child)
            else:
                yield child, item
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            if isinstance(item, (dict, list)):
                yield from _walk(item, child)
            else:
                yield child, item
    else:
        yield path, value


def first_numeric_leaf(data: Any) -> tuple[str, int | float] | None:
    """Find the first numeric leaf of a document (S6).

    Leaves are visited in insertion-order depth-first traversal. A leaf counts
    when its value is an ``int`` or ``float`` but not a ``bool``, and its key
    does not match ``(?i)(^id$|_id$|count|index|page|limit|year)``. Array
    elements have an index rather than a key, so they always count.

    Args:
        data: The JSON-compatible document.

    Returns:
        ``(path, value)`` of the first numeric leaf, or ``None``.
    """
    for path, value in iter_leaves(data):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if _NUMERIC_KEY_EXCLUDED.search(_key_of(path)):
            continue
        return path, value
    return None


def _key_of(path: str) -> str:
    """Return the object key a leaf path ends with, or the array index.

    Args:
        path: A path produced by ``iter_leaves``.

    Returns:
        The final key, or the index text for an array element.
    """
    return path.rsplit(".", 1)[-1].strip("[]")
