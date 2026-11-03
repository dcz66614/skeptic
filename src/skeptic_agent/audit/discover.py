"""Discovery module for Agent Skill skeptic-reliability-audit (S14, K56).

Discovers MCP servers from client configuration files or skeptic.yaml,
connects to each server to enumerate its tools and schemas,
and classifies tools as 'read' or 'write'.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from skeptic_agent.scenario.validate import get_sandbox_tool_specs
from skeptic_agent.setup.discover import discover

SRC_PATH = str(Path(__file__).resolve().parents[3] / "src")

WRITE_VERB_PATTERN = re.compile(
    r"\b(write|create|delete|update|set|add|remove|insert|modify|post|put|send|patch|drop|clear|append)\b",
    re.IGNORECASE,
)


def classify_tool_kind(name: str, description: str = "") -> str:
    """Classify a tool as 'read' or 'write' based on name and description.

    Args:
        name: Name of the tool.
        description: Description of the tool.

    Returns:
        'write' if write verbs are present, otherwise 'read'.
    """
    clean_name = name.replace("_", " ").replace("-", " ")
    if WRITE_VERB_PATTERN.search(clean_name):
        return "write"
    if WRITE_VERB_PATTERN.search(description):
        return "write"
    return "read"


def _extract_sandbox_name(command: list[str]) -> str | None:
    """Extract sandbox module name (e.g. 'sb_weather') from a command line if applicable."""
    for arg in command:
        if "skeptic_agent.sandboxes.sb_" in arg:
            match = re.search(r"skeptic_agent\.sandboxes\.(sb_[a-z0-9_]+)", arg)
            if match:
                return match.group(1)
        if arg.startswith("sb_"):
            return arg
    return None


async def _inspect_stdio_server(
    command: list[str],
    env: dict[str, Any] | None = None,
    cwd: Path | None = None,
) -> list[dict[str, Any]]:
    """Inspect an MCP stdio server using MCP SDK stdio_client."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)

    parts = [SRC_PATH]
    if cwd:
        parts.append(str(cwd))
    if "PYTHONPATH" in full_env:
        parts.append(full_env["PYTHONPATH"])
    full_env["PYTHONPATH"] = os.pathsep.join(parts)

    params = StdioServerParameters(
        command=command[0],
        args=command[1:],
        env=full_env,
        cwd=str(cwd) if cwd else None,
    )

    try:
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            res = await session.list_tools()
            tools: list[dict[str, Any]] = []
            for t in res.tools:
                schema = (
                    getattr(t, "input_schema", None)
                    or getattr(t, "inputSchema", None)
                    or {"type": "object", "properties": {}}
                )
                desc = t.description or ""
                kind = classify_tool_kind(t.name, desc)
                tools.append(
                    {
                        "name": t.name,
                        "description": desc,
                        "kind": kind,
                        "inputSchema": schema,
                    }
                )
            return tools
    except Exception as exc:
        sys.stderr.write(f"Warning: failed to query stdio server {command}: {exc}\n")
        return []


def discover_servers_and_tools(
    project_dir: Path | str = ".",
    output_file: Path | str | None = None,
    *,
    home_dir: Path | None = None,
    project_scope_only: bool = True,
) -> dict[str, Any]:
    """Discover all MCP servers in the project and list their tools (S14.1, S14.2).

    Args:
        project_dir: Directory containing project MCP configs or skeptic.yaml.
        output_file: Optional path to write audit/discovery.json.
        home_dir: Optional user home directory for configuration scanning.
        project_scope_only: Whether to restrict to project-scoped servers (default True).

    Returns:
        Structured dictionary conforming to discovery specifications.
    """
    proj_path = Path(project_dir).resolve()
    discovered_servers = discover(base_dir=proj_path, home_dir=home_dir)

    # Filter to project scope if requested or if project servers exist
    if project_scope_only:
        project_servers = {k: v for k, v in discovered_servers.items() if v.scope == "project"}
        if project_servers:
            discovered_servers = project_servers

    # Also check skeptic.yaml in project dir if no servers found via client configs
    skeptic_yaml = proj_path / "skeptic.yaml"
    if not discovered_servers and skeptic_yaml.is_file():
        import yaml

        try:
            cfg = yaml.safe_load(skeptic_yaml.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and "servers" in cfg:
                from skeptic_agent.setup.discover import DiscoveredServer

                for name, s_cfg in cfg["servers"].items():
                    transport = s_cfg.get("transport", "stdio")
                    cmd = s_cfg.get("command", [])
                    url = s_cfg.get("url")
                    headers = s_cfg.get("headers")
                    env = s_cfg.get("env")
                    discovered_servers[name] = DiscoveredServer(
                        name=name,
                        client="skeptic",
                        source_path=skeptic_yaml,
                        scope="project",
                        transport=transport,
                        command=cmd,
                        url=url,
                        headers=headers,
                        env=env,
                    )
        except Exception:
            pass

    project_name = proj_path.name or "my-agent"
    servers_dict: dict[str, Any] = {}

    for s_name, server in discovered_servers.items():
        server_info: dict[str, Any] = {
            "transport": server.transport,
            "scope": server.scope,
            "client": server.client,
        }
        if server.command:
            server_info["command"] = list(server.command)
        if server.url:
            server_info["url"] = server.url
        if server.headers:
            server_info["headers"] = dict(server.headers)
        if server.env:
            server_info["env"] = dict(server.env)

        # Check if server maps to a known sandbox
        sb_name = _extract_sandbox_name(server.command or [])
        if not sb_name and s_name.startswith("sb_"):
            sb_name = s_name
        elif not sb_name and f"sb_{s_name}" in (
            "sb_weather",
            "sb_files",
            "sb_calendar",
            "sb_crm",
            "sb_docs",
            "sb_fx",
            "sb_mail",
            "sb_orders",
            "sb_sqlshop",
            "sb_stocks",
        ):
            sb_name = f"sb_{s_name}"

        server_info["sandbox"] = sb_name
        tools: list[dict[str, Any]] = []

        if sb_name:
            try:
                specs = get_sandbox_tool_specs(sb_name)
                for t_name, spec in specs.items():
                    # Skip internal v2 alternates or consensus if not primary
                    if t_name.endswith("_v2") or t_name.endswith("_consensus"):
                        continue
                    schema = (
                        spec.input.model_json_schema()
                        if hasattr(spec.input, "model_json_schema")
                        else {"type": "object", "properties": {}}
                    )
                    desc = spec.description or ""
                    tools.append(
                        {
                            "name": t_name,
                            "description": desc,
                            "kind": classify_tool_kind(t_name, desc),
                            "inputSchema": schema,
                        }
                    )
            except Exception:
                pass

        if not tools and server.transport == "stdio" and server.command:
            # Query the running server via stdio
            tools = asyncio.run(_inspect_stdio_server(server.command, server.env, cwd=proj_path))

        server_info["tools"] = tools
        servers_dict[s_name] = server_info

    result: dict[str, Any] = {
        "project": project_name,
        "servers": servers_dict,
    }

    if output_file is not None:
        out_path = Path(output_file)
        if not out_path.is_absolute():
            # If out_path is already relative to cwd and points into proj_path,
            # resolve it against cwd rather than duplicating proj_path.
            cwd_candidate = Path.cwd() / out_path
            try:
                if proj_path != Path.cwd() and cwd_candidate.resolve().is_relative_to(proj_path):
                    out_path = cwd_candidate
                else:
                    out_path = proj_path / out_path
            except (ValueError, AttributeError):
                out_path = proj_path / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result
