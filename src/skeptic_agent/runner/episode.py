"""Episode runner executing one (scenario, fault, seed) turn (S7.4, S10.1, S10.2, S13, E40).

Creates an isolated temporary workdir for each episode, wraps MCP server commands
via `skeptic proxy stdio`, applies timeout and budget control, captures cassette
and state files, and produces a validated `skeptic.result/v1` record.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import jsonschema
import yaml

from skeptic_agent.faults.catalog import catalogue
from skeptic_agent.record.cassette import cassette_path
from skeptic_agent.runner.adapters import get_adapter
from skeptic_agent.runner.adapters.base import AgentAdapter, EpisodeTask, McpServerSpec
from skeptic_agent.runner.budget import BudgetTracker
from skeptic_agent.runner.llm import calculate_cost, parse_agent_spec
from skeptic_agent.scenario.model import Scenario, load_scenario
from skeptic_agent.scoring.checks import evaluate_check
from skeptic_agent.scoring.outcome import (
    HONEST_FAILURE_MARKERS,
    matches_honest_failure,
    score_episode,
)

__all__ = [
    "HONEST_FAILURE_MARKERS",
    "_evaluate_check",
    "generate_run_id",
    "matches_honest_failure",
    "resolve_episode_timeout",
    "run_episode",
]

_evaluate_check = evaluate_check

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
TMP_DIR = ROOT_DIR / ".tmp"
SCHEMA_PATH = ROOT_DIR / "schemas" / "result.schema.json"
RECOVERABILITY_PATH = ROOT_DIR / "bench" / "recoverability.json"


def resolve_episode_timeout(override: int | str | None = None) -> int | None:
    """Resolve and validate an episode timeout override (L71fix).

    Precedence:
    1. Explicit override parameter (if not None).
    2. Environment variable SKEPTIC_EPISODE_TIMEOUT_S (if set).
    3. None (falls back to scenario timeout_s).

    Validation:
    Must be an integer in range [1, 1800]. Values outside this range or invalid
    types raise ValueError.

    Args:
        override: Optional explicit timeout value in seconds.

    Returns:
        The validated integer timeout in seconds (1..1800), or None if unset.

    Raises:
        ValueError: If the override or env var is invalid or out of range.
    """
    raw: Any = override
    if raw is None:
        raw = os.getenv("SKEPTIC_EPISODE_TIMEOUT_S")
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None

    try:
        val = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid episode timeout: {raw!r}. Must be an integer between 1 and 1800."
        ) from exc

    if val < 1 or val > 1800:
        raise ValueError(f"Episode timeout override must be between 1 and 1800 seconds, got {val}.")

    return val


def generate_run_id() -> str:
    """Generate a run ID conforming to ^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$ (S10.1)."""
    now = datetime.now(UTC)
    random_hex = uuid.uuid4().hex[:6]
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{random_hex}"


def _load_result_schema() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _load_recoverability_cache() -> dict[str, dict[str, str]]:
    if RECOVERABILITY_PATH.is_file():
        try:
            data = json.loads(RECOVERABILITY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


async def run_episode(
    scenario: Scenario | Path | str,
    *,
    fault_id: str | None = None,
    seed: int = 1,
    run_id: str | None = None,
    agent: str = "reference:fake/oracle_follower",
    prompt_variant: Literal["plain", "evidence_contract"] = "plain",
    guards: Sequence[str] = (),
    out_dir: Path | str | None = None,
    workdir: Path | str | None = None,
    budget_tracker: BudgetTracker | None = None,
    adapter: AgentAdapter | None = None,
    recoverability: str | None = None,
    episode_timeout_s: int | None = None,
) -> dict[str, Any]:
    """Execute one complete episode and return the validated result record (E40, S7.4, S10.1).

    Args:
        scenario: Scenario model or path to scenario YAML.
        fault_id: Fault to inject (e.g. 'S04'), or None / 'clean' for clean baseline.
        seed: Episode random seed.
        run_id: Overall run identifier.
        agent: Agent specification ('adapter:model').
        prompt_variant: 'plain' or 'evidence_contract'.
        guards: Enabled guards sequence.
        out_dir: Directory where results.jsonl and cassettes are accumulated.
        workdir: Directory for temporary episode scratch files.
        budget_tracker: Optional BudgetTracker enforcing cost limits.
        adapter: Optional custom AgentAdapter instance.
        recoverability: Explicit recoverability string, or looked up from cache.
        episode_timeout_s: Optional per-episode timeout override in seconds (1..1800).

    Returns:
        A validated skeptic.result/v1 dictionary.

    Raises:
        BudgetExceededError: When cumulative spending exceeds configured limit.
    """
    if budget_tracker is not None:
        budget_tracker.check_can_dispatch()

    # Load scenario
    scenario_obj = load_scenario(scenario) if isinstance(scenario, (str, Path)) else scenario

    effective_run_id = run_id or generate_run_id()
    fault_clean = not fault_id or fault_id.lower() in ("none", "clean")
    fault_tag = "clean" if fault_clean else fault_id
    episode_id = f"{effective_run_id}:{scenario_obj.id}:{fault_tag}:{seed}"

    # Prepare workdir
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    ep_workdir = Path(workdir) if workdir is not None else TMP_DIR / f"ep_{uuid.uuid4().hex[:10]}"
    ep_workdir.mkdir(parents=True, exist_ok=True)

    # Output directories
    cassette_dir = (Path(out_dir) / "cassettes") if out_dir else (ep_workdir / "cassettes")
    cassette_dir.mkdir(parents=True, exist_ok=True)

    state_file = ep_workdir / "state.json"
    scenario_file = ep_workdir / "scenario.yaml"
    scenario_file.write_text(
        yaml.safe_dump(scenario_obj.to_dict(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    # Primary wrapped server command (E40)
    primary_server_name = scenario_obj.sandbox.removeprefix("sb_")
    primary_cmd = [
        sys.executable,
        "-m",
        "skeptic_agent.cli",
        "proxy",
        "stdio",
        "--episode-id",
        episode_id,
        "--scenario",
        str(scenario_file),
        "--seed",
        str(seed),
    ]
    if not fault_clean and fault_id:
        primary_cmd += ["--profile", fault_id]
    if guards:
        guards_arg = ",".join(guards) if isinstance(guards, (list, tuple)) else str(guards)
        primary_cmd += ["--guards", guards_arg]
    primary_cmd += [
        "--record",
        str(cassette_dir),
        "--state-file",
        str(state_file),
        "--",
        sys.executable,
        "-m",
        f"skeptic_agent.sandboxes.{scenario_obj.sandbox}",
    ]

    server_env: dict[str, str] = {
        "PYTHONPATH": str(SRC_DIR.resolve()),
        "SKEPTIC_STATE_FILE": str(state_file),
    }
    if scenario_obj.frozen_now:
        server_env["SKEPTIC_FROZEN_NOW"] = scenario_obj.frozen_now

    servers: list[McpServerSpec] = [
        McpServerSpec(name=primary_server_name, command=primary_cmd, env=server_env)
    ]

    # Extra servers (e.g. sb_mail or scenario.extra_servers per S8.5)
    extra_sandboxes = list(scenario_obj.extra_servers)
    if fault_id in ("A01", "A02", "A03") and "sb_mail" not in extra_sandboxes:
        extra_sandboxes.append("sb_mail")

    for extra_sandbox in extra_sandboxes:
        extra_name = extra_sandbox.removeprefix("sb_")
        extra_state = ep_workdir / f"state_{extra_name}.json"
        extra_cmd = [
            sys.executable,
            "-m",
            "skeptic_agent.cli",
            "proxy",
            "stdio",
            "--episode-id",
            f"{episode_id}:{extra_name}",
            "--seed",
            str(seed),
        ]
        if guards:
            guards_arg = ",".join(guards) if isinstance(guards, (list, tuple)) else str(guards)
            extra_cmd += ["--guards", guards_arg]
        extra_cmd += [
            "--record",
            str(cassette_dir),
            "--state-file",
            str(extra_state),
            "--",
            sys.executable,
            "-m",
            f"skeptic_agent.sandboxes.{extra_sandbox}",
        ]
        extra_env = {
            "PYTHONPATH": str(SRC_DIR.resolve()),
            "SKEPTIC_STATE_FILE": str(extra_state),
        }
        if scenario_obj.frozen_now:
            extra_env["SKEPTIC_FROZEN_NOW"] = scenario_obj.frozen_now
        servers.append(McpServerSpec(name=extra_name, command=extra_cmd, env=extra_env))

    # Parse agent specification
    adapter_name, model_name = parse_agent_spec(agent)
    active_adapter = adapter or get_adapter(adapter_name)

    prompt = f"{scenario_obj.prompt}\n\n{scenario_obj.answer_format}"
    max_steps = scenario_obj.limits.max_steps if scenario_obj.limits else 12
    override_timeout = resolve_episode_timeout(episode_timeout_s)
    if override_timeout is not None:
        timeout_s = override_timeout
    else:
        timeout_s = scenario_obj.limits.timeout_s if scenario_obj.limits else 180

    task = EpisodeTask(
        episode_id=episode_id,
        prompt=prompt,
        servers=servers,
        model=model_name,
        max_steps=max_steps,
        timeout_s=timeout_s,
        prompt_variant=prompt_variant,
        workdir=ep_workdir,
        env=server_env,
        scenario=scenario_obj,
    )

    # Execute adapter with timeout control
    start_time = time.perf_counter()
    timed_out = False
    infra_error: str | None = None
    final_answer = ""
    agent_steps = 0
    tokens_in = 0
    tokens_out = 0
    cost_usd = 0.0

    try:
        run_res = await asyncio.wait_for(active_adapter.run(task), timeout=task.timeout_s)
        final_answer = run_res.final_answer
        agent_steps = run_res.steps
        tokens_in = run_res.usage.tokens_in
        tokens_out = run_res.usage.tokens_out
        cost_usd = run_res.usage.cost_usd
        infra_error = run_res.error
    except TimeoutError:
        timed_out = True
        infra_error = f"Episode exceeded timeout of {task.timeout_s}s"
    except Exception as exc:
        infra_error = f"Adapter failure: {exc}"

    latency_s = round(time.perf_counter() - start_time, 2)

    # Cost calculation fallback
    if cost_usd <= 0.0 and (tokens_in > 0 or tokens_out > 0):
        cost_usd = calculate_cost(model_name, tokens_in, tokens_out)

    if budget_tracker is not None:
        budget_tracker.record_spend(cost_usd, tokens_in, tokens_out)

    # Parse cassette
    expected_cassette = cassette_path(cassette_dir, episode_id)
    cassette_records: list[dict[str, Any]] = []
    recorded_tool_calls: list[str] = []

    if expected_cassette.is_file():
        try:
            for line in expected_cassette.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    cassette_records.append(rec)
                    raw = rec.get("raw", {})
                    if rec.get("dir") == "c2s" and raw.get("method") == "tools/call":
                        params = raw.get("params", {})
                        tname = params.get("name", "")
                        recorded_tool_calls.append(tname)
        except Exception:
            pass

    # Read state
    state_data: Any = None
    if state_file.is_file():
        with contextlib.suppress(Exception):
            state_data = json.loads(state_file.read_text(encoding="utf-8"))

    # Fault info
    fault_info: dict[str, Any] | None = None
    if not fault_clean and fault_id:
        cat_match = next((e for e in catalogue() if e["id"] == fault_id), None)
        f_class = cat_match["class"] if cat_match else "silent"
        f_persistence = cat_match["persistence"] if cat_match else "permanent"
        fault_info = {
            "id": fault_id,
            "class": f_class,
            "persistence": f_persistence,
        }

    # Recoverability resolution
    recov_val: str | None = recoverability
    if recov_val is None:
        recov_cache = _load_recoverability_cache()
        if not fault_clean and fault_id:
            recov_val = recov_cache.get(scenario_obj.id, {}).get(fault_id)
        else:
            recov_val = "unaffected"

    # Score episode (E46, S8.2, S10.2)
    score = score_episode(
        scenario=scenario_obj,
        final_answer=final_answer,
        cassette=cassette_records,
        state_data=state_data,
        fault=fault_info,
        infra_error=infra_error,
        timed_out=timed_out,
    )

    # Relative cassette path for record
    if out_dir:
        try:
            rel_cassette = str(expected_cassette.relative_to(Path(out_dir).parent))
        except ValueError:
            rel_cassette = str(expected_cassette)
    else:
        rel_cassette = str(expected_cassette)

    # Build skeptic.result/v1 document
    result_doc: dict[str, Any] = {
        "schema": "skeptic.result/v1",
        "run_id": effective_run_id,
        "episode_id": episode_id,
        "scenario_id": scenario_obj.id,
        "sandbox": scenario_obj.sandbox,
        "language": scenario_obj.language,
        "kind": scenario_obj.kind,
        "fault": fault_info,
        "recoverability": recov_val,
        "agent": {
            "adapter": adapter_name,
            "model": model_name,
            "prompt_variant": prompt_variant,
            "guards": list(guards),
        },
        "seed": seed,
        "outcome": score.outcome,
        "flags": score.flags,
        "checks": score.checks,
        "forbid_hits": score.forbid_hits,
        "final_answer": final_answer,
        "usage": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "latency_s": latency_s,
            "steps": agent_steps,
            "tool_calls": len(recorded_tool_calls),
        },
        "cassette": rel_cassette,
        "error": infra_error,
    }

    # Validate against frozen JSON Schema
    jsonschema.validate(instance=result_doc, schema=_load_result_schema())

    # Write to results.jsonl if requested
    if out_dir:
        res_file = Path(out_dir) / "results.jsonl"
        with res_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result_doc, ensure_ascii=False) + "\n")

    return result_doc
