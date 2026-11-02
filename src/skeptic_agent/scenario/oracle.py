"""Scripted Oracle client and recoverability evaluator (S8.3, S36)."""

import asyncio
import contextlib
import json
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import MCPError

from skeptic_agent.jsonsel import get_first
from skeptic_agent.scenario.model import Scenario, ScenarioStep, load_scenario

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
TMP_DIR = ROOT_DIR / ".tmp"


@dataclass
class OracleStepResult:
    """Result of executing one step in an Oracle script.

    Attributes:
        call: The tool called.
        args: Tool arguments.
        success: Whether the step succeeded (including after retry).
        retried: Whether the step had to be retried.
        error: Error message if failed.
        response: Received structured or parsed content.
    """

    call: str
    args: dict[str, Any]
    success: bool
    retried: bool = False
    error: str | None = None
    response: Any = None


@dataclass
class OracleRunResult:
    """Outcome of running an Oracle script on a scenario.

    Attributes:
        scenario_id: The scenario identifier.
        fault_id: The tested fault ID, or None for clean run.
        success: Whether the execution path succeeded.
        path: Execution path ('steps', 'recovery.<fault>', 'recovery.default', 'none').
        recoverability: Outcome ('unaffected', 'recoverable', 'unrecoverable').
        step_results: Details of each step executed.
    """

    scenario_id: str
    fault_id: str | None
    success: bool
    path: str
    recoverability: str
    step_results: list[OracleStepResult] = field(default_factory=list)


def _check_step_expectations(data: Any, expect: dict[str, Any]) -> tuple[bool, str | None]:
    """Check a tool call response against expect JSONPath mapping (S8.3).

    Numeric values allow 1e-6 error.

    Args:
        data: Response document (dict or list).
        expect: Mapping of JSONPath expression to expected value.

    Returns:
        (passed, error_reason)
    """
    for path, expected in expect.items():
        actual = get_first(data, path)
        if actual is None and expected is not None:
            return False, f"JSONPath {path!r} matched nothing in {data}"

        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            if abs(actual - expected) > 1e-6:
                return (
                    False,
                    f"JSONPath {path!r} expected {expected} (tol 1e-6), got {actual}",
                )
        elif actual != expected:
            return False, f"JSONPath {path!r} expected {expected!r}, got {actual!r}"

    return True, None


def _extract_response_data(result: Any) -> Any:
    """Extract structured data or JSON payload from a CallToolResult."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if content and isinstance(content, list) and len(content) > 0:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except Exception:
                return text

    return None


async def _execute_step(
    session: ClientSession,
    step: ScenarioStep,
) -> OracleStepResult:
    """Execute one step with rational retry-once on failure (S8.3).

    Args:
        session: Active MCP client session.
        step: Scenario step specification.

    Returns:
        OracleStepResult.
    """
    call = step.call
    args = step.args or {}
    expect = step.expect or {}

    async def attempt() -> tuple[bool, Any, str | None]:
        try:
            res = await session.call_tool(call, args)
            if getattr(res, "is_error", False):
                content = _extract_response_data(res)
                return False, content, f"Tool {call} returned isError=True: {content}"
            data = _extract_response_data(res)
            passed, reason = _check_step_expectations(data, expect)
            return passed, data, reason
        except MCPError as exc:
            return False, None, f"MCP JSON-RPC error: {exc}"
        except Exception as exc:
            return False, None, f"Exception during tool call: {exc}"

    # First attempt
    passed, data, err = await attempt()
    if passed:
        return OracleStepResult(
            call=call,
            args=args,
            success=True,
            retried=False,
            response=data,
        )

    # Retry once
    retry_passed, retry_data, retry_err = await attempt()
    if retry_passed:
        return OracleStepResult(
            call=call,
            args=args,
            success=True,
            retried=True,
            response=retry_data,
        )

    return OracleStepResult(
        call=call,
        args=args,
        success=False,
        retried=True,
        error=retry_err or err,
        response=retry_data or data,
    )


async def _run_steps_sequence(
    scenario: Scenario,
    steps: Sequence[ScenarioStep],
    fault_id: str | None = None,
    seed: int = 0,
    state_file: Path | None = None,
) -> tuple[bool, list[OracleStepResult]]:
    """Run a sequence of steps over stdio proxy in a fresh sandbox process.

    Args:
        scenario: Scenario under test.
        steps: Steps to execute.
        fault_id: Fault to inject, or None.
        seed: Random seed.
        state_file: State file path, or None.

    Returns:
        (all_passed, step_results)
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    session_id = uuid.uuid4().hex[:8]
    temp_scenario_path = TMP_DIR / f"scen_{session_id}.yaml"
    temp_state_path = state_file or (TMP_DIR / f"state_{session_id}.json")

    try:
        # Write scenario YAML so proxy stdio can read it
        text = yaml.safe_dump(scenario.to_dict(), sort_keys=False, allow_unicode=True)
        temp_scenario_path.write_text(text, encoding="utf-8")

        args = [
            "-m",
            "skeptic_agent.cli",
            "proxy",
            "stdio",
            "--scenario",
            str(temp_scenario_path),
            "--seed",
            str(seed),
        ]
        if fault_id and fault_id.lower() != "none":
            args += ["--profile", fault_id]
        if temp_state_path:
            args += ["--state-file", str(temp_state_path)]

        args += ["--", sys.executable, "-m", f"skeptic_agent.sandboxes.{scenario.sandbox}"]

        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC_DIR.resolve())
        if scenario.frozen_now:
            env["SKEPTIC_FROZEN_NOW"] = scenario.frozen_now
        if temp_state_path:
            env["SKEPTIC_STATE_FILE"] = str(temp_state_path)

        params = StdioServerParameters(
            command=sys.executable,
            args=args,
            env=env,
            cwd=str(ROOT_DIR),
        )

        results: list[OracleStepResult] = []
        async with (
            stdio_client(params) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            for step in steps:
                step_res = await _execute_step(session, step)
                results.append(step_res)
                if not step_res.success:
                    return False, results

        return True, results
    finally:
        if temp_scenario_path.is_file():
            with contextlib.suppress(OSError):
                temp_scenario_path.unlink()
        if state_file is None and temp_state_path.is_file():
            with contextlib.suppress(OSError):
                temp_state_path.unlink()


async def run_oracle_async(
    scenario: Scenario | Path | str,
    fault: str | None = None,
    *,
    seed: int = 0,
    state_file: Path | str | None = None,
) -> OracleRunResult:
    """Execute Oracle on a scenario under an optional fault (S8.3).

    Args:
        scenario: Scenario model instance or file path.
        fault: Fault ID (e.g. 'S04'), 'none', or None.
        seed: Random seed for this run.
        state_file: Optional explicit state file.

    Returns:
        OracleRunResult with recoverability judgment.
    """
    scen = load_scenario(scenario) if not isinstance(scenario, Scenario) else scenario
    target_fault = None if (fault is None or fault.lower() == "none") else fault
    state_path = Path(state_file) if state_file is not None else None

    # Step 1: Execute primary steps
    steps_passed, step_results = await _run_steps_sequence(
        scen,
        scen.oracle.steps,
        fault_id=target_fault,
        seed=seed,
        state_file=state_path,
    )

    if steps_passed:
        return OracleRunResult(
            scenario_id=scen.id,
            fault_id=target_fault,
            success=True,
            path="steps",
            recoverability="unaffected",
            step_results=step_results,
        )

    # If this was a clean run (fault=None), steps failure means the scenario is invalid
    if target_fault is None:
        return OracleRunResult(
            scenario_id=scen.id,
            fault_id=None,
            success=False,
            path="steps",
            recoverability="unrecoverable",
            step_results=step_results,
        )

    # Step 2: Under fault, try recovery paths in order: recovery[fault], then recovery.default
    recovery = scen.oracle.recovery or {}

    # Try recovery[fault]
    if target_fault in recovery:
        rec_steps = recovery[target_fault]
        rec_passed, rec_results = await _run_steps_sequence(
            scen,
            rec_steps,
            fault_id=target_fault,
            seed=seed,
            state_file=state_path,
        )
        if rec_passed:
            return OracleRunResult(
                scenario_id=scen.id,
                fault_id=target_fault,
                success=True,
                path=f"recovery.{target_fault}",
                recoverability="recoverable",
                step_results=rec_results,
            )

    # Try recovery.default
    if "default" in recovery:
        rec_steps = recovery["default"]
        rec_passed, rec_results = await _run_steps_sequence(
            scen,
            rec_steps,
            fault_id=target_fault,
            seed=seed,
            state_file=state_path,
        )
        if rec_passed:
            return OracleRunResult(
                scenario_id=scen.id,
                fault_id=target_fault,
                success=True,
                path="recovery.default",
                recoverability="recoverable",
                step_results=rec_results,
            )

    # Neither passed -> unrecoverable
    return OracleRunResult(
        scenario_id=scen.id,
        fault_id=target_fault,
        success=False,
        path="none",
        recoverability="unrecoverable",
        step_results=step_results,
    )


def run_oracle(
    scenario: Scenario | Path | str,
    fault: str | None = None,
    *,
    seed: int = 0,
    state_file: Path | str | None = None,
) -> OracleRunResult:
    """Synchronous entry point for running Oracle on a scenario (S8.3).

    Args:
        scenario: Scenario model instance or file path.
        fault: Fault ID, 'none', or None.
        seed: Random seed.
        state_file: Optional explicit state file.

    Returns:
        OracleRunResult.
    """
    return asyncio.run(run_oracle_async(scenario, fault=fault, seed=seed, state_file=state_file))


def determine_recoverability(
    scenario: Scenario | Path | str,
    fault: str,
    *,
    seed: int = 0,
) -> str:
    """Determine the recoverability of a scenario under a fault (S8.3).

    Args:
        scenario: Scenario instance or file path.
        fault: The fault identifier (e.g. 'S04').
        seed: Episode seed.

    Returns:
        'unaffected', 'recoverable', or 'unrecoverable'.
    """
    result = run_oracle(scenario, fault=fault, seed=seed)
    return result.recoverability


def evaluate_recoverability_matrix(
    scenarios: Sequence[Scenario | Path | str],
    faults: Sequence[str],
    *,
    seed: int = 0,
) -> dict[str, dict[str, str]]:
    """Evaluate recoverability for multiple scenarios across faults (S8.3, S39).

    Args:
        scenarios: List of scenario instances or file paths.
        faults: Fault IDs to evaluate.
        seed: Random seed.

    Returns:
        Mapping of scenario_id -> {fault_id -> recoverability}.
    """
    matrix: dict[str, dict[str, str]] = {}
    for item in scenarios:
        scen = load_scenario(item) if not isinstance(item, Scenario) else item
        matrix[scen.id] = {}
        for fault in faults:
            rec = determine_recoverability(scen, fault, seed=seed)
            matrix[scen.id][fault] = rec
    return matrix
