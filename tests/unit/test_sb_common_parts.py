"""Unit tests: the sb_common clock, state file and customer data (S30)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from skeptic_agent.sandboxes.sb_common import clock, data, generate
from skeptic_agent.sandboxes.sb_common.state import SandboxState, write_json_atomic

pytestmark = pytest.mark.unit


def test_clock_defaults_to_the_s9_1_instant() -> None:
    """Without the variable, ``now`` is the frozen instant S9.1 names."""
    assert clock.now() == datetime(2026, 11, 1, 9, 0, 0, tzinfo=UTC)
    assert clock.now_iso() == "2026-11-01T09:00:00Z"


def test_parse_instant_accepts_z_and_naive_values() -> None:
    """``Z`` and offset-less instants both resolve to UTC."""
    expected = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)
    assert clock.parse_instant("2026-11-01T09:00:00Z") == expected
    assert clock.parse_instant("2026-11-01T09:00:00") == expected
    assert clock.parse_instant("2026-11-01T17:00:00+08:00") == expected


def test_parse_instant_rejects_garbage() -> None:
    """A value that is not an ISO instant is an error, not a silent default."""
    with pytest.raises(ValueError, match="Invalid isoformat"):
        clock.parse_instant("yesterday")


def test_format_iso_renders_whole_seconds_in_utc() -> None:
    """Every sandbox writes the same ``...Z`` form."""
    moment = datetime(2026, 11, 1, 10, 0, 5, tzinfo=UTC) + timedelta(milliseconds=900)
    assert clock.format_iso(moment) == "2026-11-01T10:00:05Z"


def test_state_without_a_file_only_keeps_memory(tmp_path: Path) -> None:
    """``state_file=None`` never writes anything and stamps nothing."""
    state = SandboxState({"count": 1})
    state.save()
    assert state.state_file is None
    assert state.data == {"count": 1}


def test_save_writes_the_whole_state_and_a_string_timestamp(tmp_path: Path) -> None:
    """The file holds every key, with ``updated_at`` as the S9.1 string."""
    path = tmp_path / "nested" / "state.json"
    state = SandboxState({"count": 2}, path)
    state.save()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["count"] == 2
    assert body["updated_at"] == "2026-11-01T09:00:00Z"
    assert isinstance(state.data["updated_at"], datetime)


def test_write_json_atomic_leaves_no_temp_file(tmp_path: Path) -> None:
    """The temp file of the atomic write is renamed, not left behind."""
    path = tmp_path / "state.json"
    write_json_atomic(path, {"a": 1})
    assert [item.name for item in tmp_path.iterdir()] == ["state.json"]


def test_write_json_atomic_cleans_up_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure during the rename removes the temp file and re-raises."""
    target = tmp_path / "state.json"

    def explode(source: object, destination: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("skeptic_agent.sandboxes.sb_common.state.os.replace", explode)
    with pytest.raises(RuntimeError, match="boom"):
        write_json_atomic(target, {"count": 1})
    assert list(tmp_path.iterdir()) == []


def test_state_from_env_uses_the_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``from_env`` reads ``SKEPTIC_STATE_FILE`` and treats empty as unset."""
    path = tmp_path / "state.json"
    monkeypatch.setenv("SKEPTIC_STATE_FILE", str(path))
    assert SandboxState.from_env({"count": 0}).state_file == path
    monkeypatch.setenv("SKEPTIC_STATE_FILE", "")
    assert SandboxState.from_env({"count": 0}).state_file is None


def test_customers_are_the_shared_committed_table() -> None:
    """S9.1 item 9: C-1001 to C-1040, with the S9.2 customer fields."""
    customers = data.load_customers()
    assert [customer["id"] for customer in customers] == [f"C-{n}" for n in range(1001, 1041)]
    assert set(customers[0]) == {"id", "name", "email", "tier", "city", "created_at"}


def test_customers_are_copies() -> None:
    """A caller may mutate its copy without touching the next read."""
    first = data.load_customers()
    first[0]["email"] = "changed@example.com"
    assert data.load_customers()[0]["email"] != "changed@example.com"


def test_every_customer_email_is_fictional() -> None:
    """S9.1 item 8: every email is an ``@example.com`` address."""
    for customer in data.load_customers():
        assert str(customer["email"]).endswith("@example.com")


def test_generator_is_deterministic() -> None:
    """Two calls with the fixed seed produce the same table."""
    assert generate.build_customers() == generate.build_customers()
    assert len(generate.build_customers()) == generate.CUSTOMER_COUNT


def test_committed_customers_match_the_generator() -> None:
    """The committed file is exactly what ``generate.write`` would produce."""
    committed = json.loads(data.CUSTOMERS_FILE.read_text(encoding="utf-8"))
    assert committed == generate.build_customers()
