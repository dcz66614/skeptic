"""Unit tests: ``skeptic sandbox run`` (S2, S9.1 item 2, S31)."""

import importlib
import sys
import types
from typing import Any

import pytest
from typer.testing import CliRunner

from skeptic_agent.cli import SANDBOXES, app

pytestmark = pytest.mark.unit

WEATHER_MODULE = "skeptic_agent.sandboxes.sb_weather.server"
FX_MODULE = "skeptic_agent.sandboxes.sb_fx.server"


def _stub(seen: list[str], code: int | None = None) -> types.ModuleType:
    """Build a fake sandbox module whose ``main`` records ``sys.argv``.

    Args:
        seen: The list the sandbox arguments are recorded in.
        code: The exit code ``main`` raises, or ``None`` to return.

    Returns:
        The module object to place in ``sys.modules``.
    """

    def fake_main() -> None:
        seen.extend(sys.argv)
        if code is not None:
            raise SystemExit(code)

    module = types.ModuleType(WEATHER_MODULE)
    module.main = fake_main  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize("name", sorted(SANDBOXES))
def test_sandbox_names_map_to_sandbox_modules(name: str) -> None:
    """S31 registers weather/fx, S32 stocks/crm, S33 orders/calendar."""
    assert SANDBOXES[name] in {
        "sb_weather",
        "sb_fx",
        "sb_stocks",
        "sb_crm",
        "sb_orders",
        "sb_calendar",
    }


def test_sandbox_run_rejects_an_unknown_name() -> None:
    """An unknown sandbox is a usage error listing the known ones."""
    result = CliRunner().invoke(app, ["sandbox", "run", "nope"])
    assert result.exit_code == 2
    assert "unknown sandbox 'nope'" in result.output
    assert "weather" in result.output


def test_sandbox_run_forwards_arguments_after_the_separator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--`` separates the CLI from the sandbox's own flags (S9.1 item 2)."""
    seen: list[str] = []
    monkeypatch.setitem(sys.modules, WEATHER_MODULE, _stub(seen))
    monkeypatch.setattr(
        sys, "argv", ["skeptic", "sandbox", "run", "weather", "--", "--http", "h:1"]
    )
    result = CliRunner().invoke(app, ["sandbox", "run", "weather", "--", "--http", "h:1"])
    assert result.exit_code == 0
    assert seen == ["skeptic sandbox run weather", "--http", "h:1"]


def test_sandbox_run_without_extra_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without ``--`` the sandbox starts on its defaults (stdio)."""
    seen: list[str] = []
    monkeypatch.setitem(sys.modules, WEATHER_MODULE, _stub(seen))
    monkeypatch.setattr(sys, "argv", ["skeptic", "sandbox", "run", "weather"])
    result = CliRunner().invoke(app, ["sandbox", "run", "weather"])
    assert result.exit_code == 0
    assert seen == ["skeptic sandbox run weather"]


def test_sandbox_run_reports_an_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing module is a load error, not a traceback."""
    real_import_module = importlib.import_module

    def failing_import(name: str, package: str | None = None) -> Any:
        if name == FX_MODULE:
            raise ImportError("no such module")
        return real_import_module(name, package)

    monkeypatch.delitem(sys.modules, FX_MODULE, raising=False)
    monkeypatch.setattr(importlib, "import_module", failing_import)
    result = CliRunner().invoke(app, ["sandbox", "run", "fx"])
    assert result.exit_code == 2
    assert "cannot load sandbox 'fx'" in result.output


def test_sandbox_run_forwards_a_usage_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``SystemExit`` from the sandbox keeps its exit code."""
    seen: list[str] = []
    monkeypatch.setitem(sys.modules, WEATHER_MODULE, _stub(seen, code=2))
    result = CliRunner().invoke(app, ["sandbox", "run", "weather"])
    assert result.exit_code == 2
    assert seen == ["skeptic sandbox run weather"]
