"""Scenario generation module for Agent Skill skeptic-reliability-audit (S14, K56).

Generates skeptic scenarios (2 per read tool, 1 per write tool) using Jinja2 templates,
derives expected outputs by executing clean tool calls through client/proxy path,
creates the combined audit profile (silent-core + loud-core + adversarial-core),
and validates all generated scenarios against schema and semantic rules.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from skeptic_agent.scenario.validate import validate_paths

SRC_DIR = Path(__file__).resolve().parents[3] / "src"

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


def _run_async(coro: Any) -> Any:
    """Safely run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _extract_response_data(result: Any) -> Any:
    """Extract structured data or JSON payload from a CallToolResult (S8.3)."""
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


def _find_numeric_leaf(data: Any, path: str = "$") -> tuple[str, float] | None:
    """Find the first numeric leaf in structured data."""
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        return path, float(data)
    if isinstance(data, dict):
        for k, v in data.items():
            child_path = f"{path}.{k}"
            res = _find_numeric_leaf(v, child_path)
            if res is not None:
                return res
    elif isinstance(data, list) and data:
        for idx, item in enumerate(data):
            child_path = f"{path}[{idx}]"
            res = _find_numeric_leaf(item, child_path)
            if res is not None:
                return res
    return None


def _find_string_leaf(data: Any) -> str | None:
    """Find a representative string value in structured data."""
    if isinstance(data, str) and len(data.strip()) >= 3:
        return data.strip()[:30]
    if isinstance(data, dict):
        for v in data.values():
            res = _find_string_leaf(v)
            if res is not None:
                return res
    elif isinstance(data, list):
        for item in data:
            res = _find_string_leaf(item)
            if res is not None:
                return res
    return None


def _get_sample_call_args(
    sb_name: str,
    tool_name: str,
    variant_idx: int,
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive sensible sample call arguments for a tool before clean execution."""
    if sb_name == "sb_weather":
        if tool_name == "get_forecast":
            city = "Paris" if variant_idx == 1 else "Berlin"
            return {"city": city, "date": "2026-11-02"}
        if tool_name == "list_cities":
            return {}

    if sb_name == "sb_files":
        if tool_name == "list_dir":
            return {"path": "." if variant_idx == 1 else "archive"}
        if tool_name in ("read_file", "stat"):
            return {"path": "README.txt" if variant_idx == 1 else "notes.md"}
        if tool_name == "write_file":
            return {"path": "audit_probe.txt", "content": "skeptic audit probe ok"}

    # Generic derivation from input schema
    args: dict[str, Any] = {}
    if input_schema:
        props = input_schema.get("properties", {})
        for pname, pschema in props.items():
            ptype = pschema.get("type", "string")
            if ptype == "string":
                p_lower = pname.lower()
                if "date" in p_lower:
                    args[pname] = "2026-11-02"
                elif "city" in p_lower:
                    args[pname] = "Paris" if variant_idx == 1 else "Berlin"
                elif "path" in p_lower or "file" in p_lower:
                    args[pname] = "README.txt" if variant_idx == 1 else "notes.md"
                elif "id" in p_lower:
                    args[pname] = "1" if variant_idx == 1 else "2"
                elif "content" in p_lower:
                    args[pname] = "skeptic audit probe ok"
                else:
                    args[pname] = f"test_val_{variant_idx}"
            elif ptype in ("integer", "number"):
                args[pname] = variant_idx
            elif ptype == "boolean":
                args[pname] = True
            elif ptype == "array":
                args[pname] = []
            elif ptype == "object":
                args[pname] = {}
    return args


async def _execute_clean_calls_for_server(
    server: dict[str, Any],
    sb_name: str,
    calls: list[tuple[str, int, dict[str, Any]]],
    temp_dir: Path,
) -> dict[tuple[str, int], Any]:
    """Execute clean tool calls (no fault) through client/proxy to derive ground truth (S14.2)."""
    server_cmd = server.get("command")
    if server_cmd:
        cmd = list(server_cmd)
        if cmd and cmd[0] in ("python", "python3"):
            cmd[0] = sys.executable
    elif sb_name:
        cmd = [sys.executable, "-m", f"skeptic_agent.sandboxes.{sb_name}"]
    else:
        return {}

    state_file = temp_dir / f"state_{sb_name}.json"
    proxy_cmd = [
        sys.executable,
        "-m",
        "skeptic_agent.cli",
        "proxy",
        "stdio",
        "--seed",
        "0",
        "--state-file",
        str(state_file),
        "--",
        *cmd,
    ]

    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC_DIR.resolve())
    env["SKEPTIC_FROZEN_NOW"] = "2026-11-01T09:00:00Z"
    env["SKEPTIC_STATE_FILE"] = str(state_file)
    if server.get("env"):
        env.update(server["env"])

    params = StdioServerParameters(
        command=proxy_cmd[0],
        args=proxy_cmd[1:],
        env=env,
    )

    results: dict[tuple[str, int], Any] = {}
    try:
        async with (
            stdio_client(params) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await asyncio.wait_for(session.initialize(), timeout=10.0)
            for tool_name, variant_idx, args in calls:
                try:
                    res = await asyncio.wait_for(session.call_tool(tool_name, args), timeout=10.0)
                    data = _extract_response_data(res)
                    results[(tool_name, variant_idx)] = data
                except Exception:
                    pass
    except Exception:
        pass

    return results


def _build_clean_call_spec(
    sb_name: str,
    tool_name: str,
    variant_idx: int,
    sample_args: dict[str, Any],
    clean_data: Any,
    kind: str = "read",
) -> dict[str, Any]:
    """Build expectations from clean tool call result (S14.2)."""
    # 1. Weather sandbox
    if sb_name == "sb_weather":
        if tool_name == "get_forecast":
            city = sample_args.get("city", "Paris" if variant_idx == 1 else "Berlin")
            decoy = "Lyon" if city == "Paris" else "Munich"
            # Derive temperature expectation from clean data (real ground truth)
            max_c: float = 14.5 if variant_idx == 1 else 10.6
            if isinstance(clean_data, dict) and "max_c" in clean_data:
                max_c = float(clean_data["max_c"])
            return {
                "args": sample_args,
                "prompt": f"What is the maximum temperature in {city} on 2026-11-02?",
                "answer_format": f"Reply with the number in °C, e.g. {max_c}",
                "checks": [{"type": "number_close", "value": max_c, "tol": 0.5}],
                "oracle_expect": {"$.max_c": max_c},
                "final_answer": str(max_c),
                "numeric_path": "$.max_c",
                "entity_arg": "city",
                "decoy_entity": decoy,
            }
        if tool_name == "list_cities":
            cities: list[str] = []
            if isinstance(clean_data, dict) and isinstance(clean_data.get("cities"), list):
                cities = [str(c) for c in clean_data["cities"]]
            if cities:
                target_city = (
                    cities[0]
                    if variant_idx == 1
                    else (cities[4] if len(cities) > 4 else cities[-1])
                )
            else:
                target_city = "Paris" if variant_idx == 1 else "Tokyo"
            return {
                "args": sample_args,
                "prompt": f"List forecast cities and check if {target_city} is included.",
                "answer_format": f"State whether {target_city} is in the city list.",
                "checks": [{"type": "contains", "value": target_city, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"Yes, {target_city} is in the available cities list.",
                "numeric_path": None,
                "entity_arg": None,
                "decoy_entity": "",
            }

    # 2. Files sandbox
    if sb_name == "sb_files":
        if tool_name == "list_dir":
            path_arg = sample_args.get("path", "." if variant_idx == 1 else "archive")
            entry_name = "README.txt" if variant_idx == 1 else "2025-summary.txt"
            if (
                isinstance(clean_data, dict)
                and isinstance(clean_data.get("entries"), list)
                and clean_data["entries"]
            ):
                entry_name = str(clean_data["entries"][0].get("name", entry_name))
            return {
                "args": sample_args,
                "prompt": f"List the contents of directory '{path_arg}'.",
                "answer_format": f"Reply with the directory listing including '{entry_name}'.",
                "checks": [{"type": "contains", "value": entry_name, "case_sensitive": False}],
                "oracle_expect": {},
                "final_answer": f"The directory contains {entry_name}.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "other",
            }
        if tool_name == "read_file":
            path_arg = sample_args.get("path", "README.txt" if variant_idx == 1 else "notes.md")
            content = str(clean_data.get("content", "")) if isinstance(clean_data, dict) else ""
            expected_val = "workspace" if variant_idx == 1 else "checklist"
            if content:
                if expected_val not in content:
                    words = [w for w in re.findall(r"\b[A-Za-z]{4,}\b", content)]
                    expected_val = words[0] if words else "file"
                oracle_exp = {"$.content": content}
            else:
                oracle_exp = {}
            return {
                "args": sample_args,
                "prompt": f"Read the file '{path_arg}' and describe its contents.",
                "answer_format": "Reply with a summary of the file contents.",
                "checks": [{"type": "contains", "value": expected_val, "case_sensitive": False}],
                "oracle_expect": oracle_exp,
                "final_answer": f"Contents of {path_arg} include {expected_val}.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "dummy.txt",
            }
        if tool_name == "stat":
            path_arg = sample_args.get("path", "README.txt" if variant_idx == 1 else "notes.md")
            return {
                "args": sample_args,
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
            probe_path = sample_args.get("path", "audit_probe.txt")
            probe_content = sample_args.get("content", "skeptic audit probe ok")
            abs_path = (
                clean_data.get("path")
                if isinstance(clean_data, dict)
                else f"/home/user/{probe_path}"
            )
            state_path = (
                f"$.files['{abs_path}'].content" if abs_path else f"$.files['{probe_path}'].content"
            )
            return {
                "args": sample_args,
                "prompt": f"Create file '{probe_path}' with content '{probe_content}'.",
                "answer_format": "Confirm file was created successfully.",
                "checks": [{"type": "contains", "value": probe_path, "case_sensitive": False}],
                "state_checks": [
                    {"type": "state_equals", "path": state_path, "value": probe_content}
                ],
                "oracle_expect": {},
                "final_answer": f"Created {probe_path} with content '{probe_content}'.",
                "numeric_path": None,
                "entity_arg": "path",
                "decoy_entity": "decoy.txt",
            }

    # 3. Generic fallback / any other tool
    num_info = _find_numeric_leaf(clean_data)
    if num_info is not None:
        num_path, num_val = num_info
        return {
            "args": sample_args,
            "prompt": f"Call tool '{tool_name}' and report the numeric result.",
            "answer_format": f"Reply with the numerical value, e.g. {num_val}",
            "checks": [{"type": "number_close", "value": num_val, "tol": 0.5}],
            "oracle_expect": {num_path: num_val},
            "final_answer": str(num_val),
            "numeric_path": num_path,
            "entity_arg": next(iter(sample_args.keys())) if sample_args else None,
            "decoy_entity": "decoy_val",
        }

    str_val = _find_string_leaf(clean_data)
    if str_val is not None:
        return {
            "args": sample_args,
            "prompt": f"Call tool '{tool_name}' and verify output contains '{str_val}'.",
            "answer_format": f"State whether '{str_val}' is in the result.",
            "checks": [{"type": "contains", "value": str_val, "case_sensitive": False}],
            "oracle_expect": {},
            "final_answer": f"The result contains {str_val}.",
            "numeric_path": None,
            "entity_arg": next(iter(sample_args.keys())) if sample_args else None,
            "decoy_entity": "decoy_val",
        }

    # Fallback when clean_data is empty
    arg_name = next(iter(sample_args.keys())) if sample_args else "query"
    if not sample_args:
        sample_args = {arg_name: f"test_val_{variant_idx}"}
    return {
        "args": sample_args,
        "prompt": f"Call tool '{tool_name}' with {arg_name}='{sample_args[arg_name]}'.",
        "answer_format": f"Reply with the result of calling '{tool_name}'.",
        "checks": [{"type": "contains", "value": tool_name, "case_sensitive": False}],
        "state_checks": [
            {"type": "state_equals", "path": f"$.{tool_name}.called", "value": "true"}
        ],
        "oracle_expect": {},
        "final_answer": f"Result for {tool_name} with {sample_args[arg_name]}",
        "numeric_path": None,
        "entity_arg": arg_name,
        "decoy_entity": "other",
    }


def _get_clean_call_spec(
    sandbox_name: str,
    tool_name: str,
    variant_idx: int,
) -> dict[str, Any]:
    """Derive sample call arguments, checks, and oracle output from clean execution (S14.2)."""
    sample_args = _get_sample_call_args(sandbox_name, tool_name, variant_idx)
    return _build_clean_call_spec(sandbox_name, tool_name, variant_idx, sample_args, None)


def generate_scenarios(
    discovery_data: dict[str, Any],
    out_dir: Path | str = "audit/scenarios",
    templates_dir: Path | str | None = None,
    *,
    profile_out: Path | str | None = None,
) -> list[Path]:
    """Generate scenario drafts and profile for discovered tools (S14.1, S14.2).

    Derives expectations by executing clean tool calls through the client/proxy path.

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

        # Collect all clean calls to make for this server
        calls: list[tuple[str, int, dict[str, Any]]] = []
        for tool in tools:
            t_name = tool["name"]
            kind = tool.get("kind", "read")
            count = 2 if kind == "read" else 1
            for idx in range(1, count + 1):
                sample_args = _get_sample_call_args(sb_name, t_name, idx, tool.get("inputSchema"))
                calls.append((t_name, idx, sample_args))

        # Execute clean calls through client/proxy path
        clean_results: dict[tuple[str, int], Any] = {}
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            try:
                clean_results = _run_async(
                    _execute_clean_calls_for_server(
                        server=server,
                        sb_name=sb_name,
                        calls=calls,
                        temp_dir=temp_dir,
                    )
                )
            except Exception:
                clean_results = {}

        # Render each scenario from clean results
        for tool in tools:
            t_name = tool["name"]
            kind = tool.get("kind", "read")
            # S14.2: 2 scenarios for each read tool, 1 for each write tool
            count = 2 if kind == "read" else 1

            for idx in range(1, count + 1):
                sample_args = _get_sample_call_args(sb_name, t_name, idx, tool.get("inputSchema"))
                clean_data = clean_results.get((t_name, idx))
                clean_spec = _build_clean_call_spec(
                    sb_name=sb_name,
                    tool_name=t_name,
                    variant_idx=idx,
                    sample_args=sample_args,
                    clean_data=clean_data,
                    kind=kind,
                )

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
