"""Unit tests for packaging and schema resolution (R80)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeptic_agent.data import (
    get_fake_scripts_dir,
    get_recoverability_path,
    get_schema_path,
    get_schemas_dir,
    load_schema_dict,
)

pytestmark = pytest.mark.unit

EXPECTED_SCHEMAS = [
    "cassette.schema.json",
    "config.schema.json",
    "findings.schema.json",
    "matrix.schema.json",
    "models.schema.json",
    "profile.schema.json",
    "report.schema.json",
    "result.schema.json",
    "scenario.schema.json",
]


def test_get_schemas_dir_exists() -> None:
    schemas_dir = get_schemas_dir()
    assert schemas_dir.is_dir()
    for name in EXPECTED_SCHEMAS:
        assert (schemas_dir / name).is_file(), f"Missing schema in schemas_dir: {name}"


@pytest.mark.parametrize("schema_name", EXPECTED_SCHEMAS)
def test_get_schema_path_resolves(schema_name: str) -> None:
    path = get_schema_path(schema_name)
    assert path.is_file()
    data = load_schema_dict(schema_name)
    assert isinstance(data, dict)
    assert "$schema" in data or "$id" in data


def test_get_recoverability_path() -> None:
    path = get_recoverability_path()
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_get_fake_scripts_dir() -> None:
    scripts_dir = get_fake_scripts_dir()
    assert scripts_dir.is_dir()
    assert (scripts_dir / "oracle_follower.yaml").is_file()


def test_pyproject_wheel_force_includes() -> None:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    assert pyproject_path.is_file()
    text = pyproject_path.read_text(encoding="utf-8")
    assert "[tool.hatch.build.targets.wheel.force-include]" in text
    assert '"schemas" = "skeptic_agent/data/schemas"' in text
