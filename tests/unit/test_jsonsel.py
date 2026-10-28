"""Unit tests for the JSONPath helpers (S6)."""

import pytest

from skeptic_agent.jsonsel import first_numeric_leaf, get_first, iter_leaves, set_first

pytestmark = pytest.mark.unit


def test_get_first_returns_the_first_match() -> None:
    """get_first returns the first match and None when nothing matches."""
    data = {"forecast": [{"max_c": 14.0}, {"max_c": 9.0}]}
    assert get_first(data, "$.forecast[0].max_c") == 14.0
    assert get_first(data, "$.forecast[*].max_c") == 14.0
    assert get_first(data, "$.missing.path") is None


def test_set_first_replaces_only_the_first_match() -> None:
    """set_first rewrites the first match in place and reports whether it did."""
    data = {"forecast": [{"max_c": 14.0}, {"max_c": 9.0}]}
    assert set_first(data, "$.forecast[*].max_c", 140.0) is True
    assert data == {"forecast": [{"max_c": 140.0}, {"max_c": 9.0}]}


def test_set_first_handles_nested_paths() -> None:
    """set_first works on nested objects and array elements."""
    data = {"a": {"b": [{"c": 1}]}, "d": "text"}
    assert set_first(data, "$.a.b[0].c", 7) is True
    assert set_first(data, "$.d", "changed") is True
    assert data == {"a": {"b": [{"c": 7}]}, "d": "changed"}


def test_set_first_reports_a_miss() -> None:
    """A path with no match changes nothing and returns False."""
    data = {"a": 1}
    assert set_first(data, "$.nope", 2) is False
    assert data == {"a": 1}


def test_iter_leaves_is_insertion_order_depth_first() -> None:
    """Leaves come out parents before children, in insertion order."""
    data = {"b": 1, "a": {"y": [10, 20], "x": 2}, "c": "z"}
    assert list(iter_leaves(data)) == [
        ("$.b", 1),
        ("$.a.y[0]", 10),
        ("$.a.y[1]", 20),
        ("$.a.x", 2),
        ("$.c", "z"),
    ]


def test_iter_leaves_skips_empty_containers() -> None:
    """Empty objects and arrays hold no leaves."""
    assert list(iter_leaves({"a": {}, "b": [], "c": None})) == [("$.c", None)]
    assert list(iter_leaves({})) == []


def test_iter_leaves_paths_feed_set_first() -> None:
    """Every yielded path can be written back through set_first."""
    data = {"a": {"y": [1, 2]}, "z": "t"}
    paths = [path for path, _ in iter_leaves(data)]
    for path in paths:
        assert set_first(data, path, "set") is True
    assert data == {"a": {"y": ["set", "set"]}, "z": "set"}


def test_first_numeric_leaf_skips_bools_and_keyed_numbers() -> None:
    """The first numeric leaf skips bools and the excluded key names."""
    data = {
        "id": 1,
        "item_id": 2,
        "count": 3,
        "index": 4,
        "page": 5,
        "limit": 6,
        "year": 7,
        "flag": True,
        "value": 14.0,
    }
    assert first_numeric_leaf(data) == ("$.value", 14.0)


def test_first_numeric_leaf_keeps_array_elements() -> None:
    """Array elements have an index, not a key, so they always count."""
    data = {"id": 1, "points": [30, 40]}
    assert first_numeric_leaf(data) == ("$.points[0]", 30)


def test_first_numeric_leaf_is_depth_first() -> None:
    """A nested number inside an earlier key wins over a later top-level number."""
    data = {"outer": {"inner": 3}, "later": 9}
    assert first_numeric_leaf(data) == ("$.outer.inner", 3)


def test_first_numeric_leaf_int_and_float() -> None:
    """Both int and float leaves count; strings do not."""
    assert first_numeric_leaf({"a": "12", "b": 12}) == ("$.b", 12)
    assert first_numeric_leaf({"a": 1.5}) == ("$.a", 1.5)


def test_first_numeric_leaf_none_when_there_is_no_number() -> None:
    """A document without a usable number returns None."""
    assert first_numeric_leaf({"id": 1, "name": "x", "flag": False}) is None
    assert first_numeric_leaf({}) is None
    assert first_numeric_leaf({1: "a"}) is None


def test_iter_leaves_of_a_scalar() -> None:
    """A bare scalar is a single leaf at the root path."""
    assert list(iter_leaves(5)) == [("$", 5)]
    assert list(iter_leaves(None)) == [("$", None)]


def test_excluded_keys_are_case_insensitive_and_substring() -> None:
    """The key regex ignores case and matches the listed substrings."""
    data = {"ID": 1, "Item_ID": 2, "ItemCount": 3, "MaxYear": 4, "ok": 5}
    assert first_numeric_leaf(data) == ("$.ok", 5)
