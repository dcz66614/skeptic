"""Unit tests for canonical JSON and stable hashing."""

import hashlib

import pytest

from skeptic_agent.canonical import canonical_json, stable_hash

pytestmark = pytest.mark.unit


def test_key_order_independence() -> None:
    left = {"b": 2, "a": {"y": 1, "x": [3, 2, 1]}}
    right = {"a": {"x": [3, 2, 1], "y": 1}, "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert stable_hash(left) == stable_hash(right)


def test_canonical_form_is_compact_and_sorted() -> None:
    assert canonical_json({"b": 1, "a": "x"}) == '{"a":"x","b":1}'


def test_ensure_ascii_false_keeps_chinese() -> None:
    text = canonical_json({"name": "天气"})
    assert text == '{"name":"天气"}'
    assert "\\u" not in text
    assert "天气" in text


def test_known_sha256_value() -> None:
    expected = hashlib.sha256(b'{"a":1}').hexdigest()
    assert stable_hash({"a": 1}) == expected
    assert len(stable_hash({"a": 1})) == 64


def test_stable_hash_is_lowercase_hex() -> None:
    digest = stable_hash({"a": 1})
    assert digest == digest.lower()
    int(digest, 16)
