"""Unit tests for ``skeptic proxy http`` and its ``--listen`` option (S2)."""

from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from skeptic_agent.cli import DEFAULT_LISTEN, app, parse_listen
from skeptic_agent.proxy.http import HttpProxy

pytestmark = pytest.mark.unit


def test_listen_default_is_the_s2_value() -> None:
    """S2 fixes the default listen address at ``127.0.0.1:8765``."""
    assert DEFAULT_LISTEN == "127.0.0.1:8765"
    assert parse_listen(DEFAULT_LISTEN) == ("127.0.0.1", 8765)


def test_listen_accepts_host_and_port() -> None:
    """Any host and port are split at the last colon."""
    assert parse_listen("0.0.0.0:9000") == ("0.0.0.0", 9000)
    assert parse_listen("[::1]:9000") == ("[::1]", 9000)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("127.0.0.1", "HOST:PORT"),
        (":8765", "HOST:PORT"),
        ("127.0.0.1:x", "numeric"),
        ("127.0.0.1:70000", "out of range"),
    ],
)
def test_listen_rejects_a_bad_value(value: str, message: str) -> None:
    """A value that is not ``HOST:PORT`` is a usage error."""
    with pytest.raises(typer.BadParameter, match=message):
        parse_listen(value)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stop ``HttpProxy.run`` and record how the CLI called it.

    Args:
        monkeypatch: The pytest patcher.

    Returns:
        The list the CLI arguments are recorded in.
    """
    seen: list[dict[str, Any]] = []

    def fake_run(self: HttpProxy, *, host: str = "", port: int = 0) -> None:
        """Record the listen address.

        Args:
            self: The proxy.
            host: The listen address.
            port: The listen port.
        """
        seen.append({"upstream": self.upstream, "host": host, "port": port})

    monkeypatch.setattr(HttpProxy, "run", fake_run)
    return seen


def test_cli_uses_the_default_listen(served: list[dict[str, Any]]) -> None:
    """``--upstream`` alone serves on ``127.0.0.1:8765``."""
    result = CliRunner().invoke(app, ["proxy", "http", "--upstream", "http://up.test/mcp"])
    assert result.exit_code == 0, result.output
    assert served == [{"upstream": "http://up.test/mcp", "host": "127.0.0.1", "port": 8765}]


def test_cli_listen_overrides_host_and_port(served: list[dict[str, Any]]) -> None:
    """``--listen HOST:PORT`` replaces both halves of the default."""
    result = CliRunner().invoke(
        app,
        ["proxy", "http", "--upstream", "http://up.test/mcp", "--listen", "0.0.0.0:9100"],
    )
    assert result.exit_code == 0, result.output
    assert served == [{"upstream": "http://up.test/mcp", "host": "0.0.0.0", "port": 9100}]


def test_cli_bad_listen_is_a_usage_error(served: list[dict[str, Any]]) -> None:
    """A ``--listen`` without a port exits with code 2 and serves nothing."""
    result = CliRunner().invoke(
        app, ["proxy", "http", "--upstream", "http://up.test/mcp", "--listen", "nope"]
    )
    assert result.exit_code == 2
    assert served == []


def test_cli_upstream_is_required() -> None:
    """S2 makes ``--upstream`` mandatory."""
    result = CliRunner().invoke(app, ["proxy", "http"])
    assert result.exit_code == 2


@pytest.mark.parametrize("flag", ["--host", "--port"])
def test_cli_has_no_host_or_port_option(flag: str) -> None:
    """The removed ``--host``/``--port`` options are not accepted."""
    result = CliRunner().invoke(
        app, ["proxy", "http", "--upstream", "http://up.test/mcp", flag, "1"]
    )
    assert result.exit_code == 2
