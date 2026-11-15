"""Suite models, loading, and resolution (S1, S2, S39)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.scenario.model import Scenario, load_scenario

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_SUITES_DIR = (
    Path.cwd() / "bench" / "suites"
    if (Path.cwd() / "bench" / "suites").is_dir()
    else ROOT_DIR / "bench" / "suites"
)
DEFAULT_SCENARIOS_DIR = (
    Path.cwd() / "bench" / "scenarios"
    if (Path.cwd() / "bench" / "scenarios").is_dir()
    else ROOT_DIR / "bench" / "scenarios"
)


class SuiteError(ValueError):
    """Raised when a suite file or dictionary is malformed or not found."""


class Suite(BaseModel):
    """A suite declaration grouping benchmark scenarios (S1, S39).

    Attributes:
        id: Unique suite identifier (e.g. 'smoke', 'core-v1', 'zh-v1').
        title: Human-readable name.
        description: Description of suite purpose and contents.
        scenarios: List of scenario file paths (relative to repo root) or scenario IDs.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    description: str | None = None
    scenarios: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert suite to dictionary."""
        data: dict[str, Any] = {"id": self.id}
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        data["scenarios"] = list(self.scenarios)
        return data


def load_suite(
    source: str | Path | Mapping[str, Any],
    *,
    suites_dir: Path | str | None = None,
) -> Suite:
    """Load a Suite from file path, suite name, or mapping.

    Args:
        source: File path, suite name (e.g. 'smoke'), or dict mapping.
        suites_dir: Directory where named suites reside. Defaults to bench/suites.

    Returns:
        The validated Suite instance.

    Raises:
        SuiteError: If suite cannot be found or parsed.
    """
    if isinstance(source, Mapping):
        try:
            return Suite.model_validate(source)
        except Exception as exc:
            raise SuiteError(f"Failed to validate suite mapping: {exc}") from exc

    path = Path(source)
    if not path.is_file():
        base_dir = Path(suites_dir) if suites_dir is not None else DEFAULT_SUITES_DIR
        candidate1 = base_dir / f"{source}.yaml"
        candidate2 = base_dir / f"{source}.yml"
        if candidate1.is_file():
            path = candidate1
        elif candidate2.is_file():
            path = candidate2
        else:
            raise SuiteError(f"Suite not found at {path} or in {base_dir}")

    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except Exception as exc:
        raise SuiteError(f"Failed to read suite YAML from {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SuiteError(f"Suite file {path} did not contain a mapping")

    try:
        return Suite.model_validate(data)
    except Exception as exc:
        raise SuiteError(f"Failed to validate suite from {path}: {exc}") from exc


def save_suite(suite: Suite, path: Path | str) -> None:
    """Serialize and write a Suite to a YAML file.

    Args:
        suite: The suite model.
        path: Destination file path.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = suite.to_dict()
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    dest.write_text(text, encoding="utf-8")


def list_suites(suites_dir: Path | str | None = None) -> dict[str, int]:
    """List available suites and their scenario counts (S2, S13, S39).

    Args:
        suites_dir: Directory containing suite YAML files.

    Returns:
        Mapping of suite ID to number of scenarios.
    """
    dir_path = Path(suites_dir) if suites_dir is not None else DEFAULT_SUITES_DIR
    if not dir_path.is_dir():
        return {}

    result: dict[str, int] = {}
    for p in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            suite = load_suite(p)
            result[suite.id] = len(suite.scenarios)
        except Exception:
            continue
    return result


def resolve_suite_scenarios(
    suite: Suite | str | Path,
    *,
    scenarios_dir: Path | str | None = None,
    suites_dir: Path | str | None = None,
) -> list[Scenario]:
    """Resolve a suite into concrete Scenario instances.

    Args:
        suite: Suite instance, name, or path.
        scenarios_dir: Directory containing scenarios. Defaults to bench/scenarios.
        suites_dir: Directory containing suites. Defaults to bench/suites.

    Returns:
        List of Scenario objects in the suite.

    Raises:
        SuiteError: When a scenario cannot be found or loaded.
    """
    suite_obj = suite if isinstance(suite, Suite) else load_suite(suite, suites_dir=suites_dir)
    scen_dir = Path(scenarios_dir) if scenarios_dir is not None else DEFAULT_SCENARIOS_DIR

    id_map: dict[str, Path] = {}
    if scen_dir.is_dir():
        for f in scen_dir.glob("*/*.yaml"):
            id_map[f.stem] = f

    scenarios: list[Scenario] = []
    for entry in suite_obj.scenarios:
        p = Path(entry)
        if not p.is_file() and not p.is_absolute():
            candidate = ROOT_DIR / entry
            if candidate.is_file():
                p = candidate

        if not p.is_file() and entry in id_map:
            p = id_map[entry]

        if not p.is_file():
            raise SuiteError(
                f"Scenario {entry!r} in suite {suite_obj.id!r} could not be resolved to a file"
            )

        try:
            scenarios.append(load_scenario(p))
        except Exception as exc:
            raise SuiteError(
                f"Failed to load scenario {entry!r} in suite {suite_obj.id!r}: {exc}"
            ) from exc

    return scenarios
