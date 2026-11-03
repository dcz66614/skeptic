"""Discover MCP client configurations across known tools (S15, ADR-0005, K54).

Reads configuration files in the canonical order defined by ADR-0005:
1. Generic project: ``./.mcp.json``
2. Claude Desktop: ``~/Library/Application Support/Claude/claude_desktop_config.json``
   (macOS) or ``%APPDATA%\\Claude\\claude_desktop_config.json`` (Windows)
3. Cursor: ``./.cursor/mcp.json``, ``~/.cursor/mcp.json``
4. VS Code: ``./.vscode/mcp.json``
5. Codex CLI: ``~/.codex/config.toml``, ``./.codex/config.toml``
6. Gemini CLI: ``./.gemini/settings.json``, ``~/.gemini/settings.json``

Precedence: Project-level configurations override earlier user-level configurations
for the same server name. Missing or unreadable files are skipped.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiscoveredServer:
    """An MCP server discovered from a client configuration."""

    name: str
    client: str
    source_path: Path
    scope: str
    transport: str
    command: list[str] | None = None
    env: dict[str, Any] | None = None
    url: str | None = None
    headers: dict[str, Any] | None = None

    def to_config_dict(self) -> dict[str, Any]:
        """Convert to a server dictionary conforming to skeptic.config/v1.

        Returns:
            Dictionary matching the skeptic.config/v1 server definition schema.
        """
        if self.transport == "stdio":
            result: dict[str, Any] = {
                "transport": "stdio",
                "command": list(self.command) if self.command else [],
            }
            if self.env is not None:
                result["env"] = dict(self.env)
            return result
        result = {
            "transport": "http",
            "url": self.url or "",
        }
        if self.headers is not None:
            result["headers"] = dict(self.headers)
        return result


def _resolve_claude_paths(home: Path) -> list[Path]:
    """Resolve possible Claude Desktop configuration paths.

    Args:
        home: User home directory to search relative to.

    Returns:
        List of candidate configuration file paths in precedence order.
    """
    candidates: list[Path] = []
    # 1. Windows %APPDATA%
    appdata = os.environ.get("APPDATA")
    if appdata and home == Path.home():
        candidates.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    candidates.append(home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json")
    # 2. macOS Application Support
    candidates.append(
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    )
    # 3. Linux / XDG
    candidates.append(home / ".config" / "Claude" / "claude_desktop_config.json")
    return candidates


def parse_client_file(
    path: Path,
    client: str | None = None,
    scope: str = "project",
) -> dict[str, DiscoveredServer]:
    """Parse MCP servers from a specific client configuration file.

    Args:
        path: Path to the configuration file.
        client: Client identifier (detected from path if None).
        scope: Configuration scope ("project" or "user").

    Returns:
        Mapping of server name to DiscoveredServer.
    """
    if not path.is_file():
        return {}

    detected_client = client
    if detected_client is None:
        if path.suffix == ".toml" or ".codex" in path.parts:
            detected_client = "codex"
        elif ".vscode" in path.parts:
            detected_client = "vscode"
        elif ".cursor" in path.parts:
            detected_client = "cursor"
        elif ".gemini" in path.parts:
            detected_client = "gemini"
        elif "Claude" in path.parts or path.name == "claude_desktop_config.json":
            detected_client = "claude"
        else:
            detected_client = "generic"

    if detected_client == "codex" or path.suffix == ".toml":
        return _parse_codex_toml(path, scope=scope)

    raw_text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    if detected_client == "vscode":
        return _parse_vscode_json(path, data, scope=scope)
    return _parse_standard_json(path, data, client=detected_client, scope=scope)


def _parse_standard_json(
    path: Path,
    data: dict[str, Any],
    client: str,
    scope: str,
) -> dict[str, DiscoveredServer]:
    """Parse standard mcpServers JSON dictionary."""
    servers_dict = data.get("mcpServers")
    if not isinstance(servers_dict, dict):
        return {}

    results: dict[str, DiscoveredServer] = {}
    for name, entry in servers_dict.items():
        if not isinstance(entry, dict):
            continue

        # Check HTTP first for Gemini or Claude or entries with explicit url
        is_gemini = client == "gemini"
        url = entry.get("url") or (entry.get("httpUrl") if is_gemini else None)
        entry_type = entry.get("type")

        if url or entry_type in ("http", "sse"):
            results[name] = DiscoveredServer(
                name=name,
                client=client,
                source_path=path,
                scope=scope,
                transport="http",
                url=str(url) if url else "",
                headers=entry.get("headers"),
            )
            continue

        if "command" in entry:
            cmd = entry["command"]
            cmd_list = [str(cmd)] if isinstance(cmd, (str, int)) else [str(c) for c in cmd]
            args = entry.get("args")
            if isinstance(args, list):
                cmd_list.extend(str(a) for a in args)

            env = entry.get("env")
            results[name] = DiscoveredServer(
                name=name,
                client=client,
                source_path=path,
                scope=scope,
                transport="stdio",
                command=cmd_list,
                env=dict(env) if isinstance(env, dict) else None,
            )

    return results


def _parse_vscode_json(
    path: Path,
    data: dict[str, Any],
    scope: str,
) -> dict[str, DiscoveredServer]:
    """Parse VS Code .vscode/mcp.json servers dictionary."""
    servers_dict = data.get("servers")
    if not isinstance(servers_dict, dict):
        return {}

    results: dict[str, DiscoveredServer] = {}
    for name, entry in servers_dict.items():
        if not isinstance(entry, dict):
            continue

        entry_type = entry.get("type", "")
        if entry_type in ("http", "sse") or ("url" in entry and entry_type != "stdio"):
            results[name] = DiscoveredServer(
                name=name,
                client="vscode",
                source_path=path,
                scope=scope,
                transport="http",
                url=str(entry.get("url", "")),
                headers=entry.get("headers"),
            )
            continue

        if entry_type == "stdio" or "command" in entry:
            cmd = entry.get("command", "")
            cmd_list = [str(cmd)] if isinstance(cmd, (str, int)) else [str(c) for c in cmd]
            args = entry.get("args")
            if isinstance(args, list):
                cmd_list.extend(str(a) for a in args)

            env = entry.get("env")
            results[name] = DiscoveredServer(
                name=name,
                client="vscode",
                source_path=path,
                scope=scope,
                transport="stdio",
                command=cmd_list,
                env=dict(env) if isinstance(env, dict) else None,
            )

    return results


def _parse_codex_toml(
    path: Path,
    scope: str,
) -> dict[str, DiscoveredServer]:
    """Parse Codex CLI config.toml mcp_servers table."""
    raw_text = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(raw_text)
    except Exception:
        return {}

    servers_dict = data.get("mcp_servers")
    if not isinstance(servers_dict, dict):
        return {}

    results: dict[str, DiscoveredServer] = {}
    for name, entry in servers_dict.items():
        if not isinstance(entry, dict):
            continue

        if "url" in entry:
            headers = entry.get("http_headers") or entry.get("headers")
            results[name] = DiscoveredServer(
                name=name,
                client="codex",
                source_path=path,
                scope=scope,
                transport="http",
                url=str(entry["url"]),
                headers=dict(headers) if isinstance(headers, dict) else None,
            )
            continue

        if "command" in entry:
            cmd = entry["command"]
            cmd_list = [str(cmd)] if isinstance(cmd, (str, int)) else [str(c) for c in cmd]
            args = entry.get("args")
            if isinstance(args, list):
                cmd_list.extend(str(a) for a in args)

            env = entry.get("env")
            results[name] = DiscoveredServer(
                name=name,
                client="codex",
                source_path=path,
                scope=scope,
                transport="stdio",
                command=cmd_list,
                env=dict(env) if isinstance(env, dict) else None,
            )

    return results


def get_discovery_candidates(
    base_dir: Path,
    home_dir: Path | None = None,
) -> list[tuple[str, Path, str]]:
    """Return discovery candidates in canonical ADR-0005 order.

    Order:
    1. Generic project: ``./.mcp.json``
    2. Claude Desktop (user)
    3. Cursor: project ``./.cursor/mcp.json``, user ``~/.cursor/mcp.json``
    4. VS Code: project ``./.vscode/mcp.json``
    5. Codex CLI: user ``~/.codex/config.toml``, project ``./.codex/config.toml``
    6. Gemini CLI: project ``./.gemini/settings.json``, user ``~/.gemini/settings.json``

    Args:
        base_dir: Base project directory.
        home_dir: User home directory (defaults to Path.home()).

    Returns:
        List of tuples: (client, file_path, scope).
    """
    home = home_dir if home_dir is not None else Path.home()
    candidates: list[tuple[str, Path, str]] = []

    # 1. Project generic
    candidates.append(("generic", base_dir / ".mcp.json", "project"))

    # 2. Claude Desktop (user)
    claude_paths = _resolve_claude_paths(home)
    for p in claude_paths:
        if p.is_file():
            candidates.append(("claude", p, "user"))
            break
    else:
        # If none exist, still record the primary one for completeness
        if claude_paths:
            candidates.append(("claude", claude_paths[0], "user"))

    # 3. Cursor
    candidates.append(("cursor", base_dir / ".cursor" / "mcp.json", "project"))
    candidates.append(("cursor", home / ".cursor" / "mcp.json", "user"))

    # 4. VS Code
    candidates.append(("vscode", base_dir / ".vscode" / "mcp.json", "project"))

    # 5. Codex CLI
    candidates.append(("codex", home / ".codex" / "config.toml", "user"))
    candidates.append(("codex", base_dir / ".codex" / "config.toml", "project"))

    # 6. Gemini CLI
    candidates.append(("gemini", base_dir / ".gemini" / "settings.json", "project"))
    candidates.append(("gemini", home / ".gemini" / "settings.json", "user"))

    return candidates


def discover(
    base_dir: Path = Path("."),
    home_dir: Path | None = None,
) -> dict[str, DiscoveredServer]:
    """Discover all MCP servers across known client configurations.

    Follows the precedence rule:
    - Same server name in later project-level file overrides earlier user-level file.
    - User-level file does not override project-level file.
    - Files with the same scope resolve in file candidate order (later overrides earlier).

    Args:
        base_dir: The project root directory to inspect.
        home_dir: The user home directory (defaults to Path.home()).

    Returns:
        Mapping of server name to DiscoveredServer.
    """
    base = base_dir.resolve()
    candidates = get_discovery_candidates(base_dir=base, home_dir=home_dir)

    discovered: dict[str, DiscoveredServer] = {}

    for client, file_path, scope in candidates:
        if not file_path.is_file():
            continue

        try:
            servers = parse_client_file(file_path, client=client, scope=scope)
        except Exception:
            # S15 / ADR-0005: 读不到的路径跳过
            continue

        for name, server in servers.items():
            if name not in discovered:
                discovered[name] = server
            else:
                existing = discovered[name]
                if (
                    existing.scope == "user" and server.scope == "project"
                ) or existing.scope == server.scope:
                    discovered[name] = server

    return discovered


def generate_config(
    servers: dict[str, DiscoveredServer],
    project: str = "my-agent",
    profile: str = "silent-core",
) -> dict[str, Any]:
    """Generate a skeptic.yaml config dictionary from discovered servers (S3).

    Args:
        servers: Discovered MCP servers mapping.
        project: Project name string.
        profile: Default fault profile identifier.

    Returns:
        Configuration dictionary conforming to skeptic.config/v1.

    Raises:
        ValueError: If servers dictionary is empty.
    """
    if not servers:
        raise ValueError("Cannot generate skeptic config without any servers")

    return {
        "schema": "skeptic.config/v1",
        "project": project,
        "servers": {name: s.to_config_dict() for name, s in servers.items()},
        "profile": profile,
        "guards": [],
        "record": {
            "dir": ".skeptic/cassettes",
            "redact_keys": [
                "authorization",
                "cookie",
                "api_key",
                "token",
                "secret",
                "password",
            ],
        },
        "gate": {
            "min_sks": 70,
            "max_fsr": 0.10,
            "max_icr": 0.00,
        },
        "budget": {
            "max_cost_usd_per_run": 5,
        },
        "judge": {
            "enabled": False,
            "model": None,
        },
    }
