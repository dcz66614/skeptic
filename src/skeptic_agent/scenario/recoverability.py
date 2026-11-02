"""Recoverability cache loading, saving, and querying (S8.3, S36, S39)."""

import json
from pathlib import Path
from typing import Literal

Recoverability = Literal["unaffected", "recoverable", "unrecoverable"]
"""Recoverability outcome values according to S8.3."""

RecoverabilityCache = dict[str, dict[str, str]]
"""Mapping of scenario_id -> {fault_id -> recoverability}."""

RECOVERABILITY_VALUES: set[str] = {"unaffected", "recoverable", "unrecoverable"}


class RecoverabilityError(ValueError):
    """Raised when recoverability cache data or file is invalid."""


def load_recoverability(path: Path | str) -> RecoverabilityCache:
    """Load the recoverability cache from a JSON file.

    Args:
        path: Path to the JSON cache file.

    Returns:
        The recoverability mapping.

    Raises:
        RecoverabilityError: When the file contains invalid JSON or structure.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {}

    try:
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)
    except Exception as exc:
        raise RecoverabilityError(f"Failed to read recoverability file {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RecoverabilityError(f"Recoverability file {file_path} must be a JSON object")

    result: RecoverabilityCache = {}
    for scenario_id, fault_map in data.items():
        if not isinstance(fault_map, dict):
            raise RecoverabilityError(
                f"Entry for scenario {scenario_id!r} in {file_path} must be an object"
            )
        result[scenario_id] = {str(k): str(v) for k, v in fault_map.items()}

    return result


def save_recoverability(
    cache: RecoverabilityCache,
    path: Path | str,
    *,
    merge: bool = True,
) -> None:
    """Write recoverability cache to a JSON file atomically.

    Args:
        cache: Recoverability data to save.
        path: Destination JSON file path.
        merge: When True, merges into existing file contents if present.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    final_cache: RecoverabilityCache = {}
    if merge and dest.is_file():
        try:
            final_cache = load_recoverability(dest)
        except RecoverabilityError:
            final_cache = {}

    for scenario_id, fault_map in cache.items():
        if scenario_id not in final_cache:
            final_cache[scenario_id] = {}
        final_cache[scenario_id].update(fault_map)

    # Sort scenario IDs and fault IDs deterministically
    sorted_data: dict[str, dict[str, str]] = {
        scenario_id: dict(sorted(final_cache[scenario_id].items()))
        for scenario_id in sorted(final_cache)
    }

    text = json.dumps(sorted_data, ensure_ascii=False, indent=2) + "\n"
    temp_path = dest.with_suffix(f"{dest.suffix}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(dest)


def get_recoverability(
    cache: RecoverabilityCache,
    scenario_id: str,
    fault_id: str,
) -> str | None:
    """Look up a recoverability entry from cache.

    Args:
        cache: The recoverability mapping.
        scenario_id: Scenario identifier.
        fault_id: Fault identifier.

    Returns:
        'unaffected', 'recoverable', 'unrecoverable', or None if not cached.
    """
    return cache.get(scenario_id, {}).get(fault_id)


def set_recoverability(
    cache: RecoverabilityCache,
    scenario_id: str,
    fault_id: str,
    status: str,
) -> None:
    """Set a recoverability entry in cache.

    Args:
        cache: The recoverability mapping to mutate.
        scenario_id: Scenario identifier.
        fault_id: Fault identifier.
        status: One of 'unaffected', 'recoverable', 'unrecoverable'.
    """
    if scenario_id not in cache:
        cache[scenario_id] = {}
    cache[scenario_id][fault_id] = status
