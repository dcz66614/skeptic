"""Canonical JSON and stable hashing."""

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize a JSON-compatible object in canonical form.

    Canonical form keeps non-ASCII text as UTF-8 characters and sorts object keys.

    Args:
        obj: A JSON-compatible value.

    Returns:
        The canonical JSON text with no extra whitespace.
    """
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def stable_hash(obj: Any) -> str:
    """Hash a JSON-compatible object by its canonical form.

    Args:
        obj: A JSON-compatible value.

    Returns:
        The lowercase hexadecimal SHA-256 digest of the canonical JSON bytes.
    """
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
