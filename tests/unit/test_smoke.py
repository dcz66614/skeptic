"""Smoke coverage for the package version and the CLI."""

import pytest
from typer.testing import CliRunner

from skeptic_agent import __version__
from skeptic_agent.cli import app

pytestmark = pytest.mark.unit


def test_package_version() -> None:
    assert __version__ == "0.1.0a1"


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0a1"
