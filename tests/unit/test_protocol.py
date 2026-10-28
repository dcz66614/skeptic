"""Unit tests for MCP protocol era detection (S4.2)."""

import json
from pathlib import Path

import pytest

from skeptic_agent.jsonrpc import Request, parse_line
from skeptic_agent.protocol import UNKNOWN, Era, detect_era

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent.parent / "fixtures" / "protocol"


def _load(name: str) -> Request:
    """Parse one fixture into a P10 request message.

    Args:
        name: The fixture file name.

    Returns:
        The parsed message, which must be a request.

    Raises:
        AssertionError: When the fixture is not a single request message.
    """
    message = parse_line((FIXTURES / name).read_bytes())
    assert isinstance(message, Request)
    return message


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("legacy_init.json", Era(kind="LEGACY", version="2025-11-25")),
        ("modern_discover.json", Era(kind="MODERN", version="2026-07-28")),
        ("modern_meta_call.json", Era(kind="MODERN", version="2026-07-28")),
        ("unknown.json", UNKNOWN),
    ],
)
def test_fixture_era(fixture: str, expected: Era) -> None:
    """Each fixture maps to the era required by the plan."""
    assert detect_era(_load(fixture)) == expected


def test_missing_params_is_unknown() -> None:
    """A request without params still resolves to UNKNOWN."""
    message = _load("unknown.json").model_copy(update={"params": None})
    assert detect_era(message) is UNKNOWN


def test_unknown_version_is_none() -> None:
    """UNKNOWN carries no version string."""
    assert UNKNOWN.version is None


def test_fixtures_are_single_messages() -> None:
    """Every fixture file holds exactly one JSON-RPC message."""
    for path in sorted(FIXTURES.glob("*.json")):
        parsed = parse_line(path.read_bytes())
        assert isinstance(parsed, Request), path.name
        assert json.loads(path.read_text(encoding="utf-8"))["method"] == parsed.method


@pytest.mark.parametrize(
    ("version", "kind"),
    [("2026-07-28", "MODERN"), ("2025-11-25", "LEGACY"), ("2026-07-27", "LEGACY")],
)
def test_header_detection(version: str, kind: str) -> None:
    """The header version decides the era without looking at the message."""
    era = detect_era(_load("unknown.json"), {"mcp-protocol-version": version})
    assert era == Era(kind=kind, version=version)  # type: ignore[arg-type]


def test_header_name_is_case_insensitive() -> None:
    """Any casing of the header name is accepted."""
    headers = {"MCP-Protocol-Version": "2026-07-28"}
    assert detect_era(_load("unknown.json"), headers) == Era("MODERN", "2026-07-28")


def test_header_wins_over_message() -> None:
    """A header overrides whatever the message body says."""
    legacy_message = _load("legacy_init.json")
    assert detect_era(legacy_message, {"Mcp-Protocol-Version": "2026-07-28"}) == Era(
        "MODERN", "2026-07-28"
    )
    modern_message = _load("modern_meta_call.json")
    assert detect_era(modern_message, {"mcp-protocol-version": "2025-11-25"}) == Era(
        "LEGACY", "2025-11-25"
    )


def test_empty_headers_fall_through_to_message() -> None:
    """Empty or unrelated headers do not change the message-based result."""
    message = _load("legacy_init.json")
    assert detect_era(message, {}) == Era("LEGACY", "2025-11-25")
    assert detect_era(message, {"accept": "application/json"}) == Era("LEGACY", "2025-11-25")
