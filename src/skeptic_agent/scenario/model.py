"""Scenario model and serialization for skeptic.scenario/v1 (S8, S36)."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

SCENARIO_SCHEMA: Literal["skeptic.scenario/v1"] = "skeptic.scenario/v1"


class ScenarioError(ValueError):
    """Raised when a scenario file or dictionary is malformed."""


class FaultTargets(BaseModel):
    """Target declarations for fault injection (S8.1).

    Attributes:
        primary: Tools targeted by default (at least 1).
        numeric_path: JSONPath to numeric target field (for S04).
        entity_arg: Argument name carrying entity (for S05).
        write_tools: Write tools affected by S10.
        conflict_pair: Two tools that should conflict under S09.
    """

    model_config = ConfigDict(extra="forbid")

    primary: list[str] = Field(min_length=1)
    numeric_path: str | None = None
    entity_arg: str | None = None
    write_tools: list[str] = Field(default_factory=list)
    conflict_pair: list[str] | tuple[str, str] | None = None


class Decoys(BaseModel):
    """Decoy values for entity swap faults (S8.1).

    Attributes:
        entity: The decoy entity value.
    """

    model_config = ConfigDict(extra="forbid")

    entity: str | None = None


class ForbiddenCall(BaseModel):
    """A forbidden tool call pattern for prompt injection (S8.5).

    Attributes:
        tool: The forbidden tool name.
        args_match: Argument subset matcher.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str
    args_match: dict[str, Any] = Field(default_factory=dict)


class CustomInjection(BaseModel):
    """Custom prompt injection canary and forbidden call configuration (S8.5).

    Attributes:
        forbidden_calls: List of calls indicating prompt injection obedience.
        canaries: String canary markers.
    """

    model_config = ConfigDict(extra="forbid")

    forbidden_calls: list[ForbiddenCall] = Field(default_factory=list)
    canaries: list[str] = Field(default_factory=list)


class Check(BaseModel):
    """A single evaluation check (S8.2).

    Attributes:
        type: Check type name.
        value: Target value for equality, contains or numeric close.
        case_sensitive: Whether contains check is case sensitive.
        pattern: Regex pattern.
        tol: Tolerance for numeric close check.
        values: Candidate values for one_of check.
        path: JSONPath in state file for state checks.
        tool: Tool name for call_made or call_not_made.
        args_match: Expected arguments subset for call_made.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    value: Any = None
    case_sensitive: bool | None = None
    pattern: str | None = None
    tol: float | None = None
    values: list[str] | None = None
    path: str | None = None
    tool: str | None = None
    args_match: dict[str, Any] | None = None


class Expected(BaseModel):
    """Expected outcome and checks (S8.1, S8.2).

    Attributes:
        checks: Required final answer checks (at least 1).
        state_checks: State file assertions after execution.
        forbid: Corruption detector checks that must never match.
    """

    model_config = ConfigDict(extra="forbid")

    checks: list[Check] = Field(min_length=1)
    state_checks: list[Check] = Field(default_factory=list)
    forbid: list[Check] = Field(default_factory=list)


class HonestFailure(BaseModel):
    """Extra honest failure markers (S8.1, S10.2).

    Attributes:
        extra_markers: Additional phrases signaling honest failure.
    """

    model_config = ConfigDict(extra="forbid")

    extra_markers: list[str] = Field(default_factory=list)


class ScenarioStep(BaseModel):
    """One scripted tool call in an Oracle execution (S8.1, S8.3).

    Attributes:
        call: The tool to call.
        args: Tool arguments.
        expect: Expected JSONPath expressions and values in response.
    """

    model_config = ConfigDict(extra="forbid")

    call: str
    args: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(default_factory=dict)


class OracleSpec(BaseModel):
    """Deterministic script for verifying scenario answer and recoverability (S8.1, S8.3).

    Attributes:
        steps: Main script steps.
        final_answer: Canonical clean final answer string.
        recovery: Alternate step sequences keyed by fault ID or 'default'.
    """

    model_config = ConfigDict(extra="forbid")

    steps: list[ScenarioStep] = Field(min_length=1)
    final_answer: str
    recovery: dict[str, list[ScenarioStep]] = Field(default_factory=dict)


class Limits(BaseModel):
    """Step and timeout limits (S8.1).

    Attributes:
        max_steps: Maximum allowed steps.
        timeout_s: Maximum duration in seconds.
    """

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(ge=1)
    timeout_s: int = Field(ge=1)


class Scenario(BaseModel):
    """A loaded skeptic.scenario/v1 document (S8, S36).

    Attributes:
        schema: Schema identifier ('skeptic.scenario/v1').
        id: Unique scenario identifier.
        title: Descriptive title.
        sandbox: Target sandbox name (e.g. 'sb_weather').
        extra_servers: Additional sandboxes mounted for the episode.
        language: Language code ('en' or 'zh').
        difficulty: Difficulty level ('easy', 'medium', 'hard').
        kind: Scenario kind ('read', 'write', 'multi_hop', 'cross_source').
        tags: Categorization tags.
        prompt: Task prompt presented to the agent.
        answer_format: Instruction for formatting the answer.
        frozen_now: Virtual clock ISO timestamp.
        fault_targets: Fault target metadata.
        decoys: Decoy values for entity swapping.
        alternates: Alternate tool mappings.
        injection: Prompt injection settings ('default' or custom).
        expected: Success criteria and forbid checks.
        honest_failure: Additional failure marker strings.
        oracle: Oracle execution steps and recovery paths.
        limits: Execution limits.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: Literal["skeptic.scenario/v1"] = Field(default=SCENARIO_SCHEMA, alias="schema")
    id: str
    title: str
    sandbox: str
    extra_servers: list[str] = Field(default_factory=list)
    language: Literal["en", "zh"]
    difficulty: Literal["easy", "medium", "hard"]
    kind: Literal["read", "write", "multi_hop", "cross_source"]
    tags: list[str] = Field(default_factory=list)
    prompt: str
    answer_format: str
    frozen_now: str
    fault_targets: FaultTargets
    decoys: Decoys = Field(default_factory=Decoys)
    alternates: dict[str, str] = Field(default_factory=dict)
    injection: Literal["default"] | CustomInjection = "default"
    expected: Expected
    honest_failure: HonestFailure = Field(default_factory=HonestFailure)
    oracle: OracleSpec
    limits: Limits

    def to_dict(self) -> dict[str, Any]:
        """Convert the scenario to a clean JSON-serializable dictionary.

        Returns:
            Dictionary representing the scenario.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


def load_scenario(source: Path | str | Mapping[str, Any]) -> Scenario:
    """Load and validate a scenario from a YAML file path or dictionary.

    Args:
        source: File path (Path or str) or pre-parsed mapping.

    Returns:
        The validated Scenario instance.

    Raises:
        ScenarioError: When the file does not exist, cannot be parsed, or is invalid.
    """
    if isinstance(source, Mapping):
        try:
            return Scenario.model_validate(source)
        except Exception as exc:
            raise ScenarioError(f"Failed to validate scenario: {exc}") from exc

    path = Path(source)
    if not path.is_file():
        raise ScenarioError(f"Scenario file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except Exception as exc:
        raise ScenarioError(f"Failed to read scenario YAML from {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ScenarioError(f"Scenario file {path} did not contain a mapping")

    try:
        return Scenario.model_validate(data)
    except Exception as exc:
        raise ScenarioError(f"Failed to validate scenario {path}: {exc}") from exc


def save_scenario(scenario: Scenario, path: Path | str) -> None:
    """Serialize and write a Scenario to a YAML file.

    Args:
        scenario: The scenario to write.
        path: Target file path.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = scenario.to_dict()
    text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    dest.write_text(text, encoding="utf-8")
