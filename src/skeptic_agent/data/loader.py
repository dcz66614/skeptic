"""Data and schema resource loaders (R80).

Loads schemas, recoverability cache, and fake LLM scripts from package data
via importlib.resources when installed, falling back to repository checkout paths.
"""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
from typing import Any, cast


def _resolve_traversable(t: Any) -> Path | None:
    if isinstance(t, Path):
        return t
    try:
        p = Path(str(t))
        if p.exists():
            return p
    except Exception:
        pass
    return None


def get_schemas_dir() -> Path:
    """Return the directory containing JSON schema files.

    Returns:
        Path to schemas directory (from package data, repo checkout, or cwd).
    """
    try:
        traversable = importlib.resources.files("skeptic_agent") / "data" / "schemas"
        p = _resolve_traversable(traversable)
        if p is not None and p.is_dir():
            return p
    except Exception:
        pass

    checkout = Path(__file__).resolve().parents[3] / "schemas"
    if checkout.is_dir():
        return checkout

    cwd = Path.cwd() / "schemas"
    if cwd.is_dir():
        return cwd

    return checkout


def get_schema_path(filename: str) -> Path:
    """Resolve a schema file from package data or checkout root.

    Args:
        filename: Schema filename (e.g. 'scenario.schema.json').

    Returns:
        Path to the resolved schema file.

    Raises:
        FileNotFoundError: If the schema file cannot be located.
    """
    try:
        traversable = importlib.resources.files("skeptic_agent") / "data" / "schemas" / filename
        p = _resolve_traversable(traversable)
        if p is not None and p.is_file():
            return p
    except Exception:
        pass

    schemas_dir = get_schemas_dir()
    candidate = schemas_dir / filename
    if candidate.is_file():
        return candidate

    checkout = Path(__file__).resolve().parents[3] / "schemas" / filename
    if checkout.is_file():
        return checkout

    cwd = Path.cwd() / "schemas" / filename
    if cwd.is_file():
        return cwd

    raise FileNotFoundError(f"Schema file not found: {filename}")


def load_schema_dict(filename: str) -> dict[str, Any]:
    """Load and parse a JSON schema file.

    Args:
        filename: Schema filename (e.g. 'scenario.schema.json').

    Returns:
        Parsed schema dictionary.
    """
    path = get_schema_path(filename)
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def get_recoverability_path() -> Path:
    """Return the path to recoverability.json (package data, repo checkout, or cwd)."""
    try:
        traversable = importlib.resources.files("skeptic_agent") / "data" / "recoverability.json"
        p = _resolve_traversable(traversable)
        if p is not None and p.is_file():
            return p
    except Exception:
        pass

    checkout = Path(__file__).resolve().parents[3] / "bench" / "recoverability.json"
    if checkout.is_file():
        return checkout

    cwd = Path.cwd() / "bench" / "recoverability.json"
    if cwd.is_file():
        return cwd

    return checkout


def get_fake_scripts_dir() -> Path:
    """Return the directory containing fake LLM YAML scripts."""
    try:
        traversable = importlib.resources.files("skeptic_agent") / "data" / "fake_scripts"
        p = _resolve_traversable(traversable)
        if p is not None and p.is_dir():
            return p
    except Exception:
        pass

    checkout = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fake_scripts"
    if checkout.is_dir():
        return checkout

    cwd = Path.cwd() / "tests" / "fixtures" / "fake_scripts"
    if cwd.is_dir():
        return cwd

    return checkout
