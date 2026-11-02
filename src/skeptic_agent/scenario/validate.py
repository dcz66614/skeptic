"""Scenario validator for schema and S8.4 semantic rules (S8, S36)."""

import contextlib
import importlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from skeptic_agent.scenario.model import Check, Scenario

SCHEMA_FILE = Path(__file__).resolve().parents[3] / "schemas" / "scenario.schema.json"
"""Path to the frozen skeptic.scenario/v1 JSON Schema."""

ID_PATTERN = re.compile(r"^[a-z]+\.[a-z0-9-]+\.[a-z0-9-]+\.[0-9]{3}$")
"""Regex for valid scenario identifiers (S8.1)."""


@dataclass(frozen=True)
class ValidationError:
    """One validation failure against schema or S8.4 rules.

    Attributes:
        rule: Rule number (1-7), 'schema', or 'io'.
        message: Detailed explanation of the failure.
        scenario_id: The ID of the affected scenario, if known.
        path: Path to the scenario file, if known.
    """

    rule: int | str
    message: str
    scenario_id: str | None = None
    path: str | None = None


@dataclass
class ValidationReport:
    """Aggregated outcome of validating multiple scenario files.

    Attributes:
        valid: True when all scenarios passed schema and semantic validation.
        scenario_count: Total scenarios evaluated.
        errors: All collected validation errors.
    """

    valid: bool
    scenario_count: int
    errors: list[ValidationError] = field(default_factory=list)


def _load_json_schema() -> dict[str, Any]:
    """Load the Draft 2020-12 scenario schema from disk."""
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict)
    return data


_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    """Return a cached Draft202012Validator for scenario schemas."""
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = _load_json_schema()
        _VALIDATOR = Draft202012Validator(schema, format_checker=FormatChecker())
    return _VALIDATOR


def extract_numbers(text: str) -> list[float]:
    """Extract numeric values from text according to Note N1 (S8.2).

    First match numbers with thousands separators (e.g. 1,234.5) and remove
    commas, then match remaining plain numbers. Merge and deduplicate into floats.

    Args:
        text: Input text string.

    Returns:
        List of extracted distinct floating point values.
    """
    comma_pattern = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?")
    numbers: list[float] = []

    for m in comma_pattern.finditer(text):
        cleaned = m.group(0).replace(",", "")
        with contextlib.suppress(ValueError):
            numbers.append(float(cleaned))

    replaced_text = comma_pattern.sub(" ", text)
    rem_pattern = re.compile(r"-?\d+(?:\.\d+)?")
    for m in rem_pattern.finditer(replaced_text):
        with contextlib.suppress(ValueError):
            numbers.append(float(m.group(0)))

    seen: set[float] = set()
    deduped: list[float] = []
    for num in numbers:
        if num not in seen:
            seen.add(num)
            deduped.append(num)

    return deduped


def get_sandbox_tools(sandbox_name: str) -> set[str]:
    """Inspect and return the registered tool names of a sandbox (S9.2).

    Args:
        sandbox_name: Sandbox module or server name, e.g. 'sb_weather'.

    Returns:
        Set of tool names declared by the sandbox.

    Raises:
        ImportError: When sandbox server cannot be imported.
    """
    mod = importlib.import_module(f"skeptic_agent.sandboxes.{sandbox_name}.server")
    tools = getattr(mod, "TOOLS", None)
    if tools is not None:
        return {tool.name for tool in tools}
    return set()


def evaluate_final_answer_check(check: Check, answer: str) -> tuple[bool, str | None]:
    """Evaluate a single check against Oracle final_answer string (S8.2).

    Args:
        check: The Check definition.
        answer: The Oracle final answer string.

    Returns:
        (passed, error_reason)
    """
    check_type = check.type

    if check_type == "contains":
        val = str(check.value or "")
        passed = val in answer if check.case_sensitive else val.lower() in answer.lower()
        reason = (
            None
            if passed
            else f"answer does not contain {val!r} (case_sensitive={check.case_sensitive})"
        )
        return passed, reason

    if check_type == "not_contains":
        val = str(check.value or "")
        passed = val not in answer
        return passed, None if passed else f"answer unexpectedly contains {val!r}"

    if check_type == "regex":
        pat = check.pattern or ""
        passed = bool(re.search(pat, answer))
        return passed, None if passed else f"answer does not match pattern {pat!r}"

    if check_type == "number_close":
        if check.value is None or check.tol is None:
            return False, "number_close requires value and tol"
        expected_val = float(check.value)
        tol = float(check.tol)
        numbers = extract_numbers(answer)
        passed = any(abs(n - expected_val) <= tol + 1e-9 for n in numbers)
        reason = (
            None
            if passed
            else (
                f"no extracted number in answer matches {expected_val} +/- {tol} (found: {numbers})"
            )
        )
        return passed, reason

    if check_type == "one_of":
        values = check.values or []
        passed = any(v in answer for v in values)
        return passed, None if passed else f"answer does not contain any of {values!r}"

    # State or call checks in expected.checks do not evaluate against final answer string
    return True, None


def check_prompt_leaks_number(prompt: str, value: float | int) -> bool:
    """Check if a numeric answer value appears as a string in the prompt (S8.4 Rule 6).

    Args:
        prompt: The scenario prompt text.
        value: Numeric value from a number_close check.

    Returns:
        True if the value appears in the prompt as a string.
    """
    candidates = [str(value)]
    if isinstance(value, float) and value.is_integer():
        candidates.append(str(int(value)))
    elif isinstance(value, int):
        candidates.append(f"{value:.1f}")

    for cand in candidates:
        if cand in prompt:
            # Check boundary: ensure it is a standalone number, not part of another number
            pattern = re.compile(rf"(?<![0-9.]){re.escape(cand)}(?![0-9.])")
            if pattern.search(prompt):
                return True
    return False


def validate_scenario(
    scenario: Scenario,
    *,
    known_ids: set[str] | None = None,
    file_path: str | None = None,
) -> list[ValidationError]:
    """Validate a loaded Scenario object against the 7 semantic rules of S8.4.

    Args:
        scenario: The Scenario instance.
        known_ids: Set of previously seen scenario IDs to check global uniqueness.
        file_path: Optional file path for error reporting.

    Returns:
        List of validation errors found.
    """
    errors: list[ValidationError] = []
    scen_id = scenario.id

    # Rule 1: ID format, prefix corresponds to sandbox, and global uniqueness
    if not ID_PATTERN.match(scen_id):
        errors.append(
            ValidationError(
                rule=1,
                message=f"Rule 1: scenario id '{scen_id}' does not match required regex pattern.",
                scenario_id=scen_id,
                path=file_path,
            )
        )

    expected_prefix = scenario.sandbox.removeprefix("sb_")
    actual_prefix = scen_id.split(".")[0]
    if actual_prefix != expected_prefix:
        errors.append(
            ValidationError(
                rule=1,
                message=(
                    f"Rule 1: scenario id prefix '{actual_prefix}' does not match "
                    f"sandbox '{scenario.sandbox}' (expected prefix '{expected_prefix}')."
                ),
                scenario_id=scen_id,
                path=file_path,
            )
        )

    if known_ids is not None:
        if scen_id in known_ids:
            errors.append(
                ValidationError(
                    rule=1,
                    message=f"Rule 1: duplicate scenario id '{scen_id}'.",
                    scenario_id=scen_id,
                    path=file_path,
                )
            )
        else:
            known_ids.add(scen_id)

    # Rule 2: fault_targets.primary tools must actually exist in the sandbox
    try:
        sandbox_tools = get_sandbox_tools(scenario.sandbox)
        for tool in scenario.fault_targets.primary:
            if tool not in sandbox_tools:
                errors.append(
                    ValidationError(
                        rule=2,
                        message=(
                            f"Rule 2: fault_targets.primary tool '{tool}' does not "
                            f"exist in sandbox '{scenario.sandbox}'."
                        ),
                        scenario_id=scen_id,
                        path=file_path,
                    )
                )
    except Exception as exc:
        errors.append(
            ValidationError(
                rule=2,
                message=f"Rule 2: failed to inspect tools for sandbox '{scenario.sandbox}': {exc}",
                scenario_id=scen_id,
                path=file_path,
            )
        )

    # Rule 3: kind=write must have write_tools & >=1 state_checks;
    # kind=cross_source must have conflict_pair
    if scenario.kind == "write":
        if not scenario.fault_targets.write_tools:
            errors.append(
                ValidationError(
                    rule=3,
                    message="Rule 3: kind is 'write' but fault_targets.write_tools is empty.",
                    scenario_id=scen_id,
                    path=file_path,
                )
            )
        if not scenario.expected.state_checks:
            errors.append(
                ValidationError(
                    rule=3,
                    message="Rule 3: kind is 'write' but expected.state_checks has 0 checks.",
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    if scenario.kind == "cross_source":
        pair = scenario.fault_targets.conflict_pair
        if not pair or len(pair) != 2:
            errors.append(
                ValidationError(
                    rule=3,
                    message=(
                        "Rule 3: kind is 'cross_source' but fault_targets.conflict_pair "
                        "is missing or not a pair of tools."
                    ),
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    # Rule 4: expected.checks >= 1; read scenario must have forbid or numeric_path
    if not scenario.expected.checks:
        errors.append(
            ValidationError(
                rule=4,
                message="Rule 4: expected.checks must have at least 1 check.",
                scenario_id=scen_id,
                path=file_path,
            )
        )

    if scenario.kind == "read":
        has_forbid = bool(scenario.expected.forbid)
        has_numeric = bool(scenario.fault_targets.numeric_path)
        if not (has_forbid or has_numeric):
            errors.append(
                ValidationError(
                    rule=4,
                    message=(
                        "Rule 4: read scenario must provide expected.forbid or "
                        "fault_targets.numeric_path."
                    ),
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    # Rule 5: Oracle final_answer must pass expected.checks
    final_ans = scenario.oracle.final_answer
    for check in scenario.expected.checks:
        passed, reason = evaluate_final_answer_check(check, final_ans)
        if not passed:
            errors.append(
                ValidationError(
                    rule=5,
                    message=(
                        f"Rule 5: Oracle final_answer '{final_ans}' failed expected check: {reason}"
                    ),
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    # Rule 6: prompt must not leak answer: number_close value cannot appear in prompt
    for check in scenario.expected.checks:
        if (
            check.type == "number_close"
            and check.value is not None
            and check_prompt_leaks_number(scenario.prompt, check.value)
        ):
            errors.append(
                ValidationError(
                    rule=6,
                    message=(
                        f"Rule 6: prompt leaks answer: number_close value '{check.value}' "
                        "appears in prompt."
                    ),
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    # Rule 7: language=zh prompt must contain at least 30% Chinese characters
    if scenario.language == "zh":
        prompt_text = scenario.prompt.strip()
        cjk_count = sum(1 for ch in prompt_text if "\u4e00" <= ch <= "\u9fff")
        total_len = len(prompt_text)
        ratio = (cjk_count / total_len) if total_len > 0 else 0.0
        if ratio < 0.3:
            errors.append(
                ValidationError(
                    rule=7,
                    message=(
                        f"Rule 7: language is 'zh' but Chinese characters make up "
                        f"only {ratio:.1%} of prompt (minimum 30% required)."
                    ),
                    scenario_id=scen_id,
                    path=file_path,
                )
            )

    return errors


def validate_scenario_data(
    data: Mapping[str, Any],
    *,
    known_ids: set[str] | None = None,
    file_path: str | None = None,
) -> list[ValidationError]:
    """Validate raw scenario mapping against JSON schema and S8.4 semantic rules.

    Args:
        data: Raw mapping loaded from YAML/JSON.
        known_ids: Set of previously seen scenario IDs.
        file_path: Optional file path.

    Returns:
        List of validation errors found.
    """
    errors: list[ValidationError] = []

    # 1. JSON Schema validation
    validator = _get_validator()
    schema_errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if schema_errs:
        for err in schema_errs:
            loc = ".".join(str(p) for p in err.path) or "root"
            errors.append(
                ValidationError(
                    rule="schema",
                    message=f"Schema error at {loc}: {err.message}",
                    scenario_id=str(data.get("id")) if "id" in data else None,
                    path=file_path,
                )
            )
        # If schema validation fails fundamentally, semantic checks might crash
        return errors

    # 2. Parse model
    try:
        scenario = Scenario.model_validate(data)
    except Exception as exc:
        errors.append(
            ValidationError(
                rule="schema",
                message=f"Model construction error: {exc}",
                scenario_id=str(data.get("id")) if "id" in data else None,
                path=file_path,
            )
        )
        return errors

    # 3. Semantic validation
    semantic_errs = validate_scenario(scenario, known_ids=known_ids, file_path=file_path)
    errors.extend(semantic_errs)
    return errors


def validate_scenario_file(
    path: Path | str,
    *,
    known_ids: set[str] | None = None,
) -> list[ValidationError]:
    """Validate a scenario file from disk.

    Args:
        path: Path to scenario YAML file.
        known_ids: Set of previously seen scenario IDs.

    Returns:
        List of validation errors found.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return [
            ValidationError(
                rule="io",
                message=f"File not found: {file_path}",
                path=str(file_path),
            )
        ]

    try:
        text = file_path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text)
    except Exception as exc:
        return [
            ValidationError(
                rule="schema",
                message=f"Failed to parse YAML: {exc}",
                path=str(file_path),
            )
        ]

    if not isinstance(raw, dict):
        return [
            ValidationError(
                rule="schema",
                message="File content must be a YAML mapping",
                path=str(file_path),
            )
        ]

    return validate_scenario_data(raw, known_ids=known_ids, file_path=str(file_path))


def validate_paths(paths: Sequence[Path | str]) -> ValidationReport:
    """Validate one or more scenario files or directories.

    Args:
        paths: File or directory paths to search for scenarios.

    Returns:
        Aggregated ValidationReport.
    """
    files: list[Path] = []
    for p in paths:
        path_obj = Path(p)
        if path_obj.is_dir():
            files.extend(sorted(path_obj.glob("**/*.yaml")))
            files.extend(sorted(path_obj.glob("**/*.yml")))
        elif path_obj.is_file():
            files.append(path_obj)
        else:
            return ValidationReport(
                valid=False,
                scenario_count=0,
                errors=[ValidationError(rule="io", message=f"Path not found: {p}", path=str(p))],
            )

    # Deduplicate files while preserving order
    unique_files: list[Path] = []
    seen_files: set[Path] = set()
    for f in files:
        resolved = f.resolve()
        if resolved not in seen_files:
            seen_files.add(resolved)
            unique_files.append(f)

    all_errors: list[ValidationError] = []
    known_ids: set[str] = set()

    for f in unique_files:
        errs = validate_scenario_file(f, known_ids=known_ids)
        all_errors.extend(errs)

    return ValidationReport(
        valid=len(all_errors) == 0,
        scenario_count=len(unique_files),
        errors=all_errors,
    )
