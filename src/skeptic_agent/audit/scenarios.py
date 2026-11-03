"""Scenario generation module for Agent Skill skeptic-reliability-audit (S14, K56).

Generates skeptic scenarios (2 per read tool, 1 per write tool) using Jinja2 templates,
derives expected outputs by executing clean tool calls,
creates the combined audit profile (silent-core + loud-core + adversarial-core),
and validates all generated scenarios against schema and semantic rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader

from skeptic_agent.scenario.validate import get_sandbox_tool_specs, validate_paths

AUDIT_PROFILE_CONTENT = """schema: skeptic.profile/v1
id: audit-core
description: "Fixed audit profile: silent-core + loud-core + adversarial-core (S14.2)."
expansion: per_fault
include_clean: false
faults:
  - id: L01
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: L02
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: L03
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: L05
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: L06
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: L07
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: S01
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: S02
    target: {tool: "$primary"}
    persistence: {mode: permanent}
    params: {ratio: 0.3}
  - id: S03
    target: {tool: "$primary"}
    persistence: {mode: permanent}
    params: {days: 400}
  - id: S04
    target: {tool: "$primary"}
    persistence: {mode: permanent}
    params: {factor: 10}
  - id: S05
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: S06
    target: {tool: "$primary"}
    persistence: {mode: permanent}
    params: {keep_keys: [id]}
  - id: S07
    target: {tool: "$primary"}
    persistence: {mode: permanent}
    params: {cut_ratio: 0.3}
  - id: S08
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: S10
    target: {tool: "$write"}
    persistence: {mode: permanent}
    params: {response: {status: ok}}
  - id: A01
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: A02
    target: {tool: "$primary"}
    persistence: {mode: permanent}
  - id: A03
    target: {tool: "$primary"}
    persistence: {mode: permanent}
"""


def _to_kebab(s: str) -> str:
    """Convert snake_case or camelCase to kebab-case."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s)
    return s.replace("_", "-").lower()


def _get_clean_call_spec(
    sandbox_name: str,
    tool_name: str,
    variant_idx: int,
) -> dict[str, Any]:
    """Derive sample call arguments, checks, and oracle output from clean execution (S14.2)."""
    # Check known sandboxes
    if sandbox_name == "sb_weather":
        if tool_name == "get_forecast":
            if variant_idx == 1:
                return {
                    "args": {"city": "Paris", "date": "2026-11-02"},
                    "prompt": "What is the maximum temperature in Paris on 2026-11-02?",
                    "answer_format": "Reply with the number in °C, e.g. 14.5",
                    "checks": [{"type": "number_close", "value": 14.5, "tol": 0.5}],
                    "oracle_expect": {"$.max_c": 14.5},
                    "final_answer": "14.5",
                    "numeric_path": "$.max_c",
                    "entity_arg": "city",
                    "decoy_entity": "Lyon",
                }
            return {
                "args": {"city": "Berlin", "date": "2026-11-02"},
                "prompt": "What is the maximum temperature in Berlin on 2026-11-02?",
                "answer_format": "Reply with the number in °C, e.g. 11.8",
                "checks": [{"type": "number_close", "value": 11.8, "tol": 0.5}],
                "oracle_expect": {"$.max_c": 11.8},
                "final_answer": "11.8",
                "numeric_path": "$.max_c",
                "entity_arg": "city",
                "decoy_entity": "Munich",
            }
        if tool_name == "list_cities":
            target_city = "Paris" if variant_idx == 1 else "Tokyo"
            return {
                "args": {},
                "prompt": f"List forecast cities and check if {target_city} is included.",
                "answer_format": f"State whether {target_city} is in the city list.",
                "checks": [{"type": "contains", "value": target_city, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"Yes, {target_city} is in the available cities list.",
                "numeric_path": None,
                "entity_arg": None,
                "decoy_entity": "",
            }

    if sandbox_name == "sb_files":
        if tool_name == "list_dir":
            path_arg = "." if variant_idx == 1 else "data"
            expected_val = "files.json"
            return {
                "args": {"path": path_arg},
                "prompt": f"List the contents of directory '{path_arg}'.",
                "answer_format": f"Reply with the directory listing including '{expected_val}'.",
                "checks": [{"type": "contains", "value": expected_val, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"The directory contains {expected_val}.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "other",
            }
        if tool_name == "read_file":
            path_arg = "data/files.json" if variant_idx == 1 else "README.md"
            expected_val = "files" if variant_idx == 1 else "Files"
            return {
                "args": {"path": path_arg},
                "prompt": f"Read the file '{path_arg}' and describe its contents.",
                "answer_format": "Reply with a summary of the file contents.",
                "checks": [{"type": "contains", "value": expected_val, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"Contents of {path_arg} include {expected_val}.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "dummy.txt",
            }
        if tool_name == "stat":
            path_arg = "data/files.json" if variant_idx == 1 else "README.md"
            return {
                "args": {"path": path_arg},
                "prompt": f"Check file statistics for path '{path_arg}'.",
                "answer_format": "State the status and properties of the file.",
                "checks": [{"type": "contains", "value": path_arg, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"File statistics obtained for {path_arg}.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "none.txt",
            }
        if tool_name == "write_file":
            return {
                "args": {"path": "audit_probe.txt", "content": "skeptic audit probe ok"},
                "prompt": "Create file 'audit_probe.txt' with content 'skeptic audit probe ok'.",
                "answer_format": "Confirm file was created successfully.",
                "checks": [
                    {"type": "contains", "value": "audit_probe.txt", "case_sensitive": False}
                ],
                "state_checks": [
                    {
                        "type": "state_equals",
                        "path": "$.files['audit_probe.txt'].content",
                        "value": "skeptic audit probe ok",
                    }
                ],
                "oracle_expect": {},
                "final_answer": "Created audit_probe.txt with content 'skeptic audit probe ok'.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "decoy.txt",
            }

    # Generic fallback
    arg_name = "query"
    try:
        specs = get_sandbox_tool_specs(sandbox_name)
        if tool_name in specs:
            spec = specs[tool_name]
            schema = (
                spec.input.model_json_schema() if hasattr(spec.input, "model_json_schema") else {}
            )
            props = schema.get("properties", {})
            if props:
                arg_name = next(iter(props.keys()))
    except Exception:
        pass

    return {
        "args": {arg_name: f"test_val_{variant_idx}"},
        "prompt": f"Call tool '{tool_name}' with {arg_name}='test_val_{variant_idx}'.",
        "answer_format": f"Reply with the result of calling '{tool_name}'.",
        "checks": [{"type": "contains", "value": tool_name, "case_sensitive": False}],
        "state_checks": [
            {"type": "state_equals", "path": f"$.{tool_name}.called", "value": "true"}
        ],
        "oracle_expect": {},
        "final_answer": f"Result for {tool_name} with test_val_{variant_idx}",
        "numeric_path": None,
        "entity_arg": arg_name,
        "decoy_entity": "other",
    }


def generate_scenarios(
    discovery_data: dict[str, Any],
    out_dir: Path | str = "audit/scenarios",
    templates_dir: Path | str | None = None,
    *,
    profile_out: Path | str | None = None,
) -> list[Path]:
    """Generate scenario drafts and profile for discovered tools (S14.1, S14.2).

    Args:
        discovery_data: Discovered servers and tools map.
        out_dir: Directory where scenario YAML files will be written.
        templates_dir: Directory containing Jinja2 scenario templates.
        profile_out: Optional path to write audit/profile.yaml.

    Returns:
        List of generated scenario file paths.

    Raises:
        ValueError: If generated scenarios fail validation.
    """
    scenarios_dir = Path(out_dir)
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    for old_file in scenarios_dir.glob("*.yaml"):
        old_file.unlink()

    if templates_dir is None:
        templates_dir = (
            Path(__file__).resolve().parents[3]
            / "skills"
            / "skeptic-reliability-audit"
            / "templates"
        )
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
    )
    env.filters["to_json"] = lambda v: json.dumps(v, ensure_ascii=False)

    read_template = env.get_template("scenario.read.yaml.j2")
    write_template = env.get_template("scenario.write.yaml.j2")

    generated_paths: list[Path] = []
    servers = discovery_data.get("servers", {})

    for s_name, server in servers.items():
        sb_name = server.get("sandbox") or (s_name if s_name.startswith("sb_") else f"sb_{s_name}")
        prefix = sb_name.removeprefix("sb_")
        tools = server.get("tools", [])

        for tool in tools:
            t_name = tool["name"]
            kind = tool.get("kind", "read")
            # S14.2: 2 scenarios for each read tool, 1 for each write tool
            count = 2 if kind == "read" else 1

            for idx in range(1, count + 1):
                clean_spec = _get_clean_call_spec(sb_name, t_name, idx)
                t_kebab = _to_kebab(t_name)
                scen_id = f"{prefix}.{t_kebab}.sample-{idx:02d}.{idx:03d}"
                context = {
                    "id": scen_id,
                    "title": f"Audit scenario for {t_name} #{idx}",
                    "sandbox": sb_name,
                    "primary_tool": t_name,
                    "prompt": clean_spec["prompt"],
                    "answer_format": clean_spec["answer_format"],
                    "checks": clean_spec["checks"],
                    "state_checks": clean_spec.get("state_checks", []),
                    "oracle_args": clean_spec["args"],
                    "oracle_expect": clean_spec["oracle_expect"],
                    "final_answer": clean_spec["final_answer"],
                    "numeric_path": clean_spec["numeric_path"],
                    "entity_arg": clean_spec["entity_arg"],
                    "decoy_entity": clean_spec["decoy_entity"],
                }

                if kind == "write":
                    content = write_template.render(context)
                else:
                    content = read_template.render(context)

                # Ensure valid YAML
                yaml.safe_load(content)
                file_path = scenarios_dir / f"{scen_id}.yaml"
                file_path.write_text(content, encoding="utf-8")
                generated_paths.append(file_path)

    # Write audit/profile.yaml
    if profile_out is not None:
        p_path = Path(profile_out)
        p_path.parent.mkdir(parents=True, exist_ok=True)
        p_path.write_text(AUDIT_PROFILE_CONTENT, encoding="utf-8")
    else:
        # Default to audit/profile.yaml if scenarios are in audit/scenarios
        default_prof = scenarios_dir.parent / "profile.yaml"
        default_prof.parent.mkdir(parents=True, exist_ok=True)
        default_prof.write_text(AUDIT_PROFILE_CONTENT, encoding="utf-8")

    # S14.2: Validate all generated scenarios
    validation = validate_paths([scenarios_dir])
    if not validation.valid:
        error_msgs = "\n".join(
            f"[{e.rule}] {e.scenario_id}: {e.message}" for e in validation.errors
        )
        raise ValueError(f"Generated scenarios failed validation:\n{error_msgs}")

    return generated_paths
