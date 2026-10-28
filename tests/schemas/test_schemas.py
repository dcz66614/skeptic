"""Validate Skeptic documents against the frozen Draft 2020-12 schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
EXAMPLES = ROOT / "tests" / "schemas" / "examples"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

SCHEMA_NAMES = (
    "config",
    "cassette",
    "profile",
    "scenario",
    "result",
    "report",
    "findings",
    "matrix",
    "models",
)


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _load_schema(name: str) -> dict[str, Any]:
    schema = _load(SCHEMA_DIR / f"{name}.schema.json")
    if not isinstance(schema, dict):
        raise AssertionError(f"{name} schema is not an object")
    return schema


def _examples(name: str, kind: str) -> list[Path]:
    folder = EXAMPLES / name
    paths: list[Path] = []
    for pattern in (f"{kind}_*.json", f"{kind}_*.yaml", f"{kind}_*.yml"):
        paths.extend(folder.glob(pattern))
    return sorted(paths)


def _registry() -> Registry[Any]:
    pairs: list[tuple[str, Resource[Any]]] = []
    for name in SCHEMA_NAMES:
        schema = _load_schema(name)
        pairs.append((str(schema["$id"]), Resource.from_contents(schema)))
    return Registry().with_resources(pairs)


def _validator(name: str, registry: Registry[Any]) -> Draft202012Validator:
    return Draft202012Validator(
        _load_schema(name),
        registry=registry,
        format_checker=FormatChecker(),
    )


@pytest.fixture(scope="module")
def registry() -> Registry[Any]:
    return _registry()


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_draft_2020_12(name: str) -> None:
    schema = _load_schema(name)
    assert schema["$schema"] == DRAFT
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_valid_examples(name: str, registry: Registry[Any]) -> None:
    paths = _examples(name, "valid")
    assert paths
    validator = _validator(name, registry)
    for path in paths:
        validator.validate(_load(path))


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_invalid_examples(name: str, registry: Registry[Any]) -> None:
    paths = _examples(name, "invalid")
    assert paths
    validator = _validator(name, registry)
    for path in paths:
        with pytest.raises(ValidationError):
            validator.validate(_load(path))
