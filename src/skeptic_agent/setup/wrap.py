"""Rewrite MCP client configurations to route servers through skeptic proxy (S15, ADR-0005, K54).

Rewrite rules:
- stdio: ``{command: C, args: A}`` -> ``{command: "skeptic", args: ["proxy", "stdio",
  "--profile", P] + (guards ? ["--guards", G] : []) + ["--record", record_dir, "--", C] + A}``
- HTTP: ``url`` -> ``http://127.0.0.1:8765/mcp``, and register upstream URL in ``skeptic.yaml``.
- Pre-write: original file backed up to ``FILE.skeptic.bak``.
- Undo: restored from ``FILE.skeptic.bak`` byte-for-byte.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

DEFAULT_LISTEN = "127.0.0.1:8765"
MCP_PATH = "/mcp"
DEFAULT_PROFILE = "silent-core"
DEFAULT_RECORD_DIR = ".skeptic/cassettes"


def undo_wrap(file_path: Path) -> Path:
    """Restore client configuration file byte-for-byte from backup.

    Args:
        file_path: The configuration file path to restore.

    Returns:
        The restored file path.

    Raises:
        FileNotFoundError: If the backup file FILE.skeptic.bak does not exist.
    """
    backup_path = Path(f"{file_path}.skeptic.bak")
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Byte-for-byte restoration
    file_path.write_bytes(backup_path.read_bytes())
    backup_path.unlink()
    return file_path


def _register_http_upstream(
    base_dir: Path,
    server_name: str,
    upstream_url: str,
    headers: dict[str, Any] | None = None,
) -> None:
    """Record upstream HTTP server in skeptic.yaml (S15, ADR-0005)."""
    candidates = [
        base_dir / "skeptic.yaml",
        base_dir.parent / "skeptic.yaml",
        Path.cwd() / "skeptic.yaml",
    ]
    target_yaml: Path | None = None
    for cand in candidates:
        if cand.is_file():
            target_yaml = cand
            break

    if target_yaml is not None:
        try:
            config = yaml.safe_load(target_yaml.read_text(encoding="utf-8")) or {}
        except Exception:
            config = {}
    else:
        target_yaml = base_dir / "skeptic.yaml"
        config = {
            "schema": "skeptic.config/v1",
            "project": base_dir.name or "my-agent",
            "servers": {},
            "profile": DEFAULT_PROFILE,
            "guards": [],
            "record": {
                "dir": DEFAULT_RECORD_DIR,
                "redact_keys": [
                    "authorization",
                    "cookie",
                    "api_key",
                    "token",
                    "secret",
                    "password",
                ],
            },
            "gate": {"min_sks": 70, "max_fsr": 0.10, "max_icr": 0.00},
            "budget": {"max_cost_usd_per_run": 5},
            "judge": {"enabled": False, "model": None},
        }

    if "servers" not in config or not isinstance(config["servers"], dict):
        config["servers"] = {}

    entry: dict[str, Any] = {
        "transport": "http",
        "url": upstream_url,
    }
    if headers:
        entry["headers"] = dict(headers)
    config["servers"][server_name] = entry

    target_yaml.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _rewrite_toml_section(
    lines: list[str],
    server_name: str,
    new_command: str | None = None,
    new_args: list[str] | None = None,
    new_url: str | None = None,
) -> list[str]:
    """Rewrite a specific [mcp_servers.<name>] section in TOML lines."""
    header_regex = re.compile(rf"^\s*\[\s*mcp_servers\.{re.escape(server_name)}\s*\]\s*(#.*)?$")
    next_section_regex = re.compile(r"^\s*\[")

    result: list[str] = []
    in_section = False
    section_updated = False
    seen_command = False
    seen_args = False
    seen_url = False

    for line in lines:
        if header_regex.match(line):
            in_section = True
            result.append(line)
            continue

        if in_section and next_section_regex.match(line):
            # Exiting our section; insert any missing keys before leaving
            if new_command is not None and not seen_command:
                result.append(f'command = "{new_command}"\n')
            if new_args is not None and not seen_args:
                result.append(f"args = {json.dumps(new_args)}\n")
            if new_url is not None and not seen_url:
                result.append(f'url = "{new_url}"\n')
            in_section = False
            section_updated = True
            result.append(line)
            continue

        if in_section:
            if new_command is not None and re.match(r"^\s*command\s*=", line):
                result.append(f'command = "{new_command}"\n')
                seen_command = True
                continue
            if new_args is not None and re.match(r"^\s*args\s*=", line):
                result.append(f"args = {json.dumps(new_args)}\n")
                seen_args = True
                continue
            if new_url is not None and re.match(r"^\s*url\s*=", line):
                result.append(f'url = "{new_url}"\n')
                seen_url = True
                continue
            result.append(line)
        else:
            result.append(line)

    if in_section and not section_updated:
        if new_command is not None and not seen_command:
            result.append(f'command = "{new_command}"\n')
        if new_args is not None and not seen_args:
            result.append(f"args = {json.dumps(new_args)}\n")
        if new_url is not None and not seen_url:
            result.append(f'url = "{new_url}"\n')

    return result


def wrap_file(
    file_path: Path,
    servers: list[str] | None = None,
    all_servers: bool = False,
    profile: str = DEFAULT_PROFILE,
    guards: str | None = None,
    record_dir: str = DEFAULT_RECORD_DIR,
    undo: bool = False,
) -> list[str]:
    """Wrap MCP client server entries to route via skeptic proxy.

    Args:
        file_path: Configuration file to wrap.
        servers: List of server names to wrap.
        all_servers: When true, wrap all discovered servers in the file.
        profile: Fault profile identifier (default: silent-core).
        guards: Guard preset name or comma-separated guard list.
        record_dir: Cassette output directory (default: .skeptic/cassettes).
        undo: When true, restore file from backup instead of wrapping.

    Returns:
        List of server names that were wrapped.

    Raises:
        FileNotFoundError: If file_path does not exist (or backup on undo).
        ValueError: If neither all_servers nor servers is given, or if
            a requested server name is not found in file_path.
    """
    if undo:
        undo_wrap(file_path)
        return []

    if not file_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    if not all_servers and not servers:
        raise ValueError("Must specify either all_servers=True or at least one server name")

    # Determine file type
    is_toml = file_path.suffix == ".toml" or ".codex" in file_path.parts

    raw_text = file_path.read_text(encoding="utf-8")
    wrapped_names: list[str] = []

    if is_toml:
        data = tomllib.loads(raw_text)
        servers_table = data.get("mcp_servers")
        if not isinstance(servers_table, dict):
            raise ValueError(f"No mcp_servers table found in {file_path}")

        if all_servers:
            targets = list(servers_table.keys())
        else:
            targets = list(servers or [])
            for target in targets:
                if target not in servers_table:
                    raise ValueError(f"Server '{target}' not found in {file_path}")

        # Pre-read and backup before modifying
        backup_path = Path(f"{file_path}.skeptic.bak")
        if not backup_path.exists():
            backup_path.write_bytes(file_path.read_bytes())

        lines = raw_text.splitlines(keepends=True)
        for target in targets:
            entry = servers_table[target]
            if "command" in entry:
                cmd = entry["command"]
                cmd_list = [str(cmd)] if isinstance(cmd, (str, int)) else [str(c) for c in cmd]
                orig_args = entry.get("args") or []
                c_0 = cmd_list[0]
                c_rest = cmd_list[1:]
                all_a = c_rest + [str(a) for a in orig_args]

                new_args = ["proxy", "stdio", "--profile", profile]
                if guards:
                    new_args.extend(["--guards", guards])
                new_args.extend(["--record", record_dir, "--", c_0])
                new_args.extend(all_a)

                lines = _rewrite_toml_section(
                    lines,
                    server_name=target,
                    new_command="skeptic",
                    new_args=new_args,
                )
                wrapped_names.append(target)
            elif "url" in entry:
                orig_url = str(entry["url"])
                proxy_url = f"http://{DEFAULT_LISTEN}{MCP_PATH}"
                lines = _rewrite_toml_section(
                    lines,
                    server_name=target,
                    new_url=proxy_url,
                )
                _register_http_upstream(
                    file_path.parent,
                    server_name=target,
                    upstream_url=orig_url,
                    headers=entry.get("http_headers") or entry.get("headers"),
                )
                wrapped_names.append(target)

        new_toml_text = "".join(lines)
        # Verify valid TOML before writing
        tomllib.loads(new_toml_text)
        file_path.write_text(new_toml_text, encoding="utf-8")
        return wrapped_names

    # JSON handling
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level object in {file_path}")

    # Determine dictionary key (VS Code uses 'servers', others use 'mcpServers')
    if "servers" in data and isinstance(data["servers"], dict):
        dict_key = "servers"
    elif "mcpServers" in data and isinstance(data["mcpServers"], dict):
        dict_key = "mcpServers"
    else:
        raise ValueError(f"No servers or mcpServers dictionary found in {file_path}")

    server_dict: dict[str, Any] = data[dict_key]
    if all_servers:
        targets = list(server_dict.keys())
    else:
        targets = list(servers or [])
        for target in targets:
            if target not in server_dict:
                raise ValueError(f"Server '{target}' not found in {file_path}")

    # Pre-read and backup before modifying
    backup_path = Path(f"{file_path}.skeptic.bak")
    if not backup_path.exists():
        backup_path.write_bytes(file_path.read_bytes())

    for target in targets:
        entry = server_dict[target]
        if not isinstance(entry, dict):
            continue

        if "command" in entry or entry.get("type") == "stdio":
            cmd = entry.get("command", "")
            cmd_list = [str(cmd)] if isinstance(cmd, (str, int)) else [str(c) for c in cmd]
            orig_args = entry.get("args") or []
            c_0 = cmd_list[0] if cmd_list else ""
            c_rest = cmd_list[1:] if len(cmd_list) > 1 else []
            all_a = c_rest + [str(a) for a in orig_args]

            new_args = ["proxy", "stdio", "--profile", profile]
            if guards:
                new_args.extend(["--guards", guards])
            new_args.extend(["--record", record_dir, "--", c_0])
            new_args.extend(all_a)

            entry["command"] = "skeptic"
            entry["args"] = new_args
            wrapped_names.append(target)
        elif "url" in entry or "httpUrl" in entry or entry.get("type") in ("http", "sse"):
            url_key = "httpUrl" if "httpUrl" in entry and "url" not in entry else "url"
            orig_url = str(entry.get(url_key, ""))
            proxy_url = f"http://{DEFAULT_LISTEN}{MCP_PATH}"
            entry[url_key] = proxy_url
            _register_http_upstream(
                file_path.parent,
                server_name=target,
                upstream_url=orig_url,
                headers=entry.get("headers"),
            )
            wrapped_names.append(target)

    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return wrapped_names
