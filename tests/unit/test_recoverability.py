"""Unit tests for scenario recoverability cache (S8.3, S36)."""

import json
from pathlib import Path

import pytest

from skeptic_agent.scenario.recoverability import (
    RecoverabilityCache,
    RecoverabilityError,
    get_recoverability,
    load_recoverability,
    save_recoverability,
    set_recoverability,
)

pytestmark = pytest.mark.unit


def test_load_recoverability_empty_when_file_not_found(tmp_path: Path) -> None:
    """Loading a non-existent file returns an empty cache dict."""
    cache = load_recoverability(tmp_path / "missing.json")
    assert cache == {}


def test_load_recoverability_valid_file(tmp_path: Path) -> None:
    """Loading a valid JSON recoverability cache loads dictionary."""
    file = tmp_path / "rec.json"
    data = {
        "weather.forecast.001": {"L01": "unaffected", "S04": "recoverable"},
        "fx.rate.001": {"S04": "unrecoverable"},
    }
    file.write_text(json.dumps(data), encoding="utf-8")

    cache = load_recoverability(file)
    assert cache == data


def test_load_recoverability_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON raises RecoverabilityError."""
    file = tmp_path / "bad.json"
    file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RecoverabilityError, match="Failed to read"):
        load_recoverability(file)


def test_load_recoverability_non_object(tmp_path: Path) -> None:
    """Top-level JSON array raises RecoverabilityError."""
    file = tmp_path / "bad.json"
    file.write_text("[]", encoding="utf-8")
    with pytest.raises(RecoverabilityError, match="must be a JSON object"):
        load_recoverability(file)


def test_load_recoverability_non_dict_entry(tmp_path: Path) -> None:
    """A non-dict scenario entry raises RecoverabilityError."""
    file = tmp_path / "bad.json"
    file.write_text(json.dumps({"weather.001": "not-a-dict"}), encoding="utf-8")
    with pytest.raises(RecoverabilityError, match="must be an object"):
        load_recoverability(file)


def test_save_recoverability_merges_and_sorts(tmp_path: Path) -> None:
    """save_recoverability with merge=True merges existing entries and sorts keys."""
    file = tmp_path / "rec.json"
    initial = {"scen.B": {"S04": "recoverable"}, "scen.A": {"L01": "unaffected"}}
    save_recoverability(initial, file)

    update = {"scen.A": {"S04": "recoverable"}, "scen.C": {"L02": "unrecoverable"}}
    save_recoverability(update, file, merge=True)

    loaded = load_recoverability(file)
    assert "scen.A" in loaded
    assert loaded["scen.A"]["L01"] == "unaffected"
    assert loaded["scen.A"]["S04"] == "recoverable"
    assert loaded["scen.B"]["S04"] == "recoverable"
    assert loaded["scen.C"]["L02"] == "unrecoverable"

    # Check key ordering in raw JSON
    raw_lines = [line.strip() for line in file.read_text(encoding="utf-8").splitlines()]
    scen_keys = [line.strip('": {') for line in raw_lines if line.startswith('"scen.')]
    assert scen_keys == ["scen.A", "scen.B", "scen.C"]


def test_get_and_set_recoverability() -> None:
    """Helper get_recoverability and set_recoverability work as expected."""
    cache: RecoverabilityCache = {}
    set_recoverability(cache, "scen.001", "S04", "recoverable")
    assert get_recoverability(cache, "scen.001", "S04") == "recoverable"
    assert get_recoverability(cache, "scen.001", "L01") is None
    assert get_recoverability(cache, "missing.scen", "S04") is None
