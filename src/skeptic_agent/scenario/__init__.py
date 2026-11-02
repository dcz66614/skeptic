"""Scenario models, validation, Oracle execution, and recoverability (S8, S36)."""

from skeptic_agent.scenario.model import (
    Check,
    Decoys,
    Expected,
    FaultTargets,
    HonestFailure,
    Limits,
    OracleSpec,
    Scenario,
    ScenarioStep,
    load_scenario,
    save_scenario,
)
from skeptic_agent.scenario.oracle import (
    OracleRunResult,
    OracleStepResult,
    determine_recoverability,
    evaluate_recoverability_matrix,
    run_oracle,
)
from skeptic_agent.scenario.recoverability import (
    RecoverabilityCache,
    load_recoverability,
    save_recoverability,
)
from skeptic_agent.scenario.validate import (
    ValidationError,
    ValidationReport,
    validate_paths,
    validate_scenario,
    validate_scenario_file,
)

__all__ = [
    "Check",
    "Decoys",
    "Expected",
    "FaultTargets",
    "HonestFailure",
    "Limits",
    "OracleRunResult",
    "OracleSpec",
    "OracleStepResult",
    "RecoverabilityCache",
    "Scenario",
    "ScenarioStep",
    "ValidationError",
    "ValidationReport",
    "determine_recoverability",
    "evaluate_recoverability_matrix",
    "load_recoverability",
    "load_scenario",
    "run_oracle",
    "save_recoverability",
    "save_scenario",
    "validate_paths",
    "validate_scenario",
    "validate_scenario_file",
]
