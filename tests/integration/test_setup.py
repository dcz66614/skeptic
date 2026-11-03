"""Integration tests for skeptic init and skeptic wrap (S15, ADR-0005, K54)."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.setup.discover import (
    DiscoveredServer,
    _parse_codex_toml,
    _parse_standard_json,
    _parse_vscode_json,
    _resolve_claude_paths,
    discover,
    generate_config,
    get_discovery_candidates,
    parse_client_file,
)
from skeptic_agent.setup.wrap import (
    _register_http_upstream,
    _rewrite_toml_section,
    undo_wrap,
    wrap_file,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "client_configs"
CONFIG_SCHEMA_PATH = ROOT / "schemas" / "config.schema.json"
ECHO_SERVER = ROOT / "tests" / "fixtures" / "echo_server.py"

runner = CliRunner()


def _load_config_schema() -> dict[str, object]:
    """Load config.schema.json for validation."""
    return json.loads(CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Acceptance Criterion 1: 6 client configuration formats are discovered
# ---------------------------------------------------------------------------


def test_discover_generic_mcp_json(tmp_path: Path) -> None:
    """Generic .mcp.json stdio and HTTP formats are discovered."""
    src = FIXTURES_DIR / "generic" / ".mcp.json"
    dest = tmp_path / ".mcp.json"
    shutil.copy2(src, dest)

    servers = parse_client_file(dest, client="generic", scope="project")
    assert "generic_stdio" in servers
    assert "generic_http" in servers

    stdio_srv = servers["generic_stdio"]
    assert stdio_srv.transport == "stdio"
    assert stdio_srv.command == ["python", "-m", "echo_server"]
    assert stdio_srv.env == {"GENERIC_ENV": "1"}

    http_srv = servers["generic_http"]
    assert http_srv.transport == "http"
    assert http_srv.url == "https://generic.example.com/mcp"
    assert http_srv.headers == {"Authorization": "Bearer generic-token"}


def test_discover_claude_desktop_config(tmp_path: Path) -> None:
    """Claude Desktop claude_desktop_config.json is discovered."""
    claude_dir = tmp_path / "Claude"
    claude_dir.mkdir(parents=True)
    dest = claude_dir / "claude_desktop_config.json"
    shutil.copy2(FIXTURES_DIR / "claude" / "claude_desktop_config.json", dest)

    servers = parse_client_file(dest, client="claude", scope="user")
    assert "claude_stdio" in servers
    assert "claude_http" in servers
    assert servers["claude_stdio"].transport == "stdio"
    assert servers["claude_http"].transport == "http"


def test_discover_cursor_mcp_json(tmp_path: Path) -> None:
    """Cursor .cursor/mcp.json is discovered."""
    cursor_dir = tmp_path / ".cursor"
    cursor_dir.mkdir(parents=True)
    dest = cursor_dir / "mcp.json"
    shutil.copy2(FIXTURES_DIR / "cursor" / ".cursor" / "mcp.json", dest)

    servers = parse_client_file(dest, client="cursor", scope="project")
    assert "cursor_stdio" in servers
    assert "cursor_http" in servers
    assert servers["cursor_stdio"].transport == "stdio"
    assert servers["cursor_http"].transport == "http"


def test_discover_vscode_mcp_json(tmp_path: Path) -> None:
    """VS Code .vscode/mcp.json servers format is discovered."""
    vscode_dir = tmp_path / ".vscode"
    vscode_dir.mkdir(parents=True)
    dest = vscode_dir / "mcp.json"
    shutil.copy2(FIXTURES_DIR / "vscode" / ".vscode" / "mcp.json", dest)

    servers = parse_client_file(dest, client="vscode", scope="project")
    assert "vscode_stdio" in servers
    assert "vscode_http" in servers
    assert servers["vscode_stdio"].transport == "stdio"
    assert servers["vscode_http"].transport == "http"
    # sse is mapped to transport: http
    assert servers["vscode_http"].url == "https://vscode.example.com/mcp/sse"


def test_discover_codex_config_toml(tmp_path: Path) -> None:
    """Codex CLI .codex/config.toml table format is discovered."""
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(parents=True)
    dest = codex_dir / "config.toml"
    shutil.copy2(FIXTURES_DIR / "codex" / ".codex" / "config.toml", dest)

    servers = parse_client_file(dest, client="codex", scope="project")
    assert "codex_stdio" in servers
    assert "codex_http" in servers
    assert servers["codex_stdio"].transport == "stdio"
    assert servers["codex_http"].transport == "http"
    assert servers["codex_http"].headers == {"Authorization": "Bearer codex_key"}


def test_discover_gemini_settings_json(tmp_path: Path) -> None:
    """Gemini CLI .gemini/settings.json format is discovered."""
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir(parents=True)
    dest = gemini_dir / "settings.json"
    shutil.copy2(FIXTURES_DIR / "gemini" / ".gemini" / "settings.json", dest)

    servers = parse_client_file(dest, client="gemini", scope="project")
    assert "gemini_stdio" in servers
    assert "gemini_http" in servers
    assert servers["gemini_stdio"].transport == "stdio"
    assert servers["gemini_http"].transport == "http"
    assert servers["gemini_http"].url == "https://gemini.example.com/mcp"


def test_discover_all_six_formats_combined(tmp_path: Path) -> None:
    """All 6 client configurations are discovered in a unified project/user setup."""
    proj_dir = tmp_path / "project"
    user_home = tmp_path / "user"
    proj_dir.mkdir()
    user_home.mkdir()

    # 1. Generic project
    shutil.copy2(FIXTURES_DIR / "generic" / ".mcp.json", proj_dir / ".mcp.json")

    # 2. Claude Desktop (user)
    claude_dir = user_home / "AppData" / "Roaming" / "Claude"
    claude_dir.mkdir(parents=True)
    shutil.copy2(
        FIXTURES_DIR / "claude" / "claude_desktop_config.json",
        claude_dir / "claude_desktop_config.json",
    )

    # 3. Cursor (project)
    cursor_dir = proj_dir / ".cursor"
    cursor_dir.mkdir(parents=True)
    shutil.copy2(FIXTURES_DIR / "cursor" / ".cursor" / "mcp.json", cursor_dir / "mcp.json")

    # 4. VS Code (project)
    vscode_dir = proj_dir / ".vscode"
    vscode_dir.mkdir(parents=True)
    shutil.copy2(FIXTURES_DIR / "vscode" / ".vscode" / "mcp.json", vscode_dir / "mcp.json")

    # 5. Codex (project)
    codex_dir = proj_dir / ".codex"
    codex_dir.mkdir(parents=True)
    shutil.copy2(FIXTURES_DIR / "codex" / ".codex" / "config.toml", codex_dir / "config.toml")

    # 6. Gemini (project)
    gemini_dir = proj_dir / ".gemini"
    gemini_dir.mkdir(parents=True)
    shutil.copy2(
        FIXTURES_DIR / "gemini" / ".gemini" / "settings.json",
        gemini_dir / "settings.json",
    )

    discovered = discover(base_dir=proj_dir, home_dir=user_home)

    expected_servers = [
        "generic_stdio",
        "generic_http",
        "claude_stdio",
        "claude_http",
        "cursor_stdio",
        "cursor_http",
        "vscode_stdio",
        "vscode_http",
        "codex_stdio",
        "codex_http",
        "gemini_stdio",
        "gemini_http",
    ]
    for srv in expected_servers:
        assert srv in discovered, f"Expected {srv} in discovered servers"

    # Generated skeptic config validates against schema
    config_dict = generate_config(discovered, project="test-project")
    schema = _load_config_schema()
    jsonschema.validate(config_dict, schema)


def test_precedence_project_overrides_user(tmp_path: Path) -> None:
    """ADR-0005: project-level config overrides user-level for the same server name."""
    proj_dir = tmp_path / "project"
    user_home = tmp_path / "user"
    proj_dir.mkdir()
    user_home.mkdir()

    # User Claude config defines server 'weather' as user stdio
    claude_dir = user_home / "AppData" / "Roaming" / "Claude"
    claude_dir.mkdir(parents=True)
    claude_cfg = {
        "mcpServers": {
            "weather": {
                "command": "claude-weather",
                "args": ["user"],
            }
        }
    }
    (claude_dir / "claude_desktop_config.json").write_text(json.dumps(claude_cfg), encoding="utf-8")

    # Project .mcp.json defines server 'weather' as project stdio
    proj_cfg = {
        "mcpServers": {
            "weather": {
                "command": "project-weather",
                "args": ["override"],
            }
        }
    }
    (proj_dir / ".mcp.json").write_text(json.dumps(proj_cfg), encoding="utf-8")

    discovered = discover(base_dir=proj_dir, home_dir=user_home)
    assert discovered["weather"].command == ["project-weather", "override"]
    assert discovered["weather"].scope == "project"


# ---------------------------------------------------------------------------
# Acceptance Criterion 2: wrap then undo restores byte-for-byte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("client_dir", "subpath"),
    [
        ("generic", ".mcp.json"),
        ("claude", "claude_desktop_config.json"),
        ("cursor", ".cursor/mcp.json"),
        ("vscode", ".vscode/mcp.json"),
        ("codex", ".codex/config.toml"),
        ("gemini", ".gemini/settings.json"),
    ],
)
def test_wrap_and_undo_byte_for_byte_all_formats(
    tmp_path: Path, client_dir: str, subpath: str
) -> None:
    """Wrap any client configuration and verify undo restores exact raw bytes."""
    src = FIXTURES_DIR / client_dir / subpath
    dest = tmp_path / subpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    orig_bytes = dest.read_bytes()

    # Wrap all servers
    wrapped = wrap_file(
        dest,
        all_servers=True,
        profile="silent-core",
        guards="recommended",
        record_dir=str(tmp_path / "cassettes"),
    )
    assert len(wrapped) > 0
    # Content has changed
    assert dest.read_bytes() != orig_bytes
    # Backup exists
    backup = Path(f"{dest}.skeptic.bak")
    assert backup.is_file()

    # Undo
    undo_wrap(dest)
    assert not backup.exists()
    assert dest.read_bytes() == orig_bytes


def test_wrap_single_server_and_guards_flag(tmp_path: Path) -> None:
    """Wrap only selected server and verify skeptic proxy args format (S15)."""
    cfg_file = tmp_path / ".mcp.json"
    initial = {
        "mcpServers": {
            "srv_a": {"command": "npx", "args": ["-y", "srv_a"]},
            "srv_b": {"command": "python", "args": ["-m", "srv_b"]},
        }
    }
    cfg_file.write_text(json.dumps(initial, indent=2), encoding="utf-8")

    wrap_file(
        cfg_file,
        servers=["srv_a"],
        profile="adversarial-core",
        guards="schema_guard,emptiness_guard",
        record_dir=str(tmp_path / "cassettes"),
    )

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    srv_a = data["mcpServers"]["srv_a"]
    srv_b = data["mcpServers"]["srv_b"]

    # srv_a was wrapped
    assert srv_a["command"] == "skeptic"
    assert srv_a["args"] == [
        "proxy",
        "stdio",
        "--profile",
        "adversarial-core",
        "--guards",
        "schema_guard,emptiness_guard",
        "--record",
        str(tmp_path / "cassettes"),
        "--",
        "npx",
        "-y",
        "srv_a",
    ]

    # srv_b was not touched
    assert srv_b["command"] == "python"
    assert srv_b["args"] == ["-m", "srv_b"]


def test_wrap_http_server_registers_in_skeptic_yaml(tmp_path: Path) -> None:
    """Wrapping an HTTP server points client to local proxy and records upstream in skeptic.yaml."""
    cfg_file = tmp_path / ".mcp.json"
    initial = {
        "mcpServers": {
            "remote_crm": {
                "type": "http",
                "url": "https://crm.example.com/mcp",
                "headers": {"Authorization": "Bearer secret"},
            }
        }
    }
    cfg_file.write_text(json.dumps(initial, indent=2), encoding="utf-8")

    wrap_file(cfg_file, servers=["remote_crm"])

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["mcpServers"]["remote_crm"]["url"] == "http://127.0.0.1:8765/mcp"

    yaml_file = tmp_path / "skeptic.yaml"
    assert yaml_file.is_file()
    skeptic_cfg = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    assert skeptic_cfg["servers"]["remote_crm"]["transport"] == "http"
    assert skeptic_cfg["servers"]["remote_crm"]["url"] == "https://crm.example.com/mcp"
    assert skeptic_cfg["servers"]["remote_crm"]["headers"] == {"Authorization": "Bearer secret"}


# ---------------------------------------------------------------------------
# Acceptance Criterion 3: Wrapped config talks to echo server through proxy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrapped_config_calls_echo_server_through_proxy(tmp_path: Path) -> None:
    """A wrapped configuration calls echo server via skeptic proxy and retrieves expected output."""
    config_file = tmp_path / ".mcp.json"
    orig_dict = {
        "mcpServers": {
            "echo": {
                "command": sys.executable,
                "args": [str(ECHO_SERVER)],
            }
        }
    }
    orig_raw = json.dumps(orig_dict, indent=2) + "\n"
    config_file.write_text(orig_raw, encoding="utf-8")
    orig_bytes = config_file.read_bytes()

    cassette_dir = tmp_path / "cassettes"
    wrap_file(
        config_file,
        servers=["echo"],
        profile="none",
        record_dir=str(cassette_dir),
    )

    data = json.loads(config_file.read_text(encoding="utf-8"))
    server_cfg = data["mcpServers"]["echo"]
    assert server_cfg["command"] == "skeptic"
    assert "proxy" in server_cfg["args"]
    assert "stdio" in server_cfg["args"]

    env = dict(os.environ)
    parts = [str(ROOT / "src"), str(ECHO_SERVER.parent)]
    if "PYTHONPATH" in env:
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)

    params = StdioServerParameters(
        command=server_cfg["command"],
        args=server_cfg["args"],
        env=env,
        cwd=str(tmp_path),
    )

    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("echo", {"text": "hello wrapped proxy"})
        assert not result.is_error
        assert isinstance(result.content[0], types.TextContent)
        assert result.content[0].text == "hello wrapped proxy"

    # Verify undo restores file byte-for-byte
    undo_wrap(config_file)
    assert config_file.read_bytes() == orig_bytes


# ---------------------------------------------------------------------------
# CLI Tests: skeptic init and skeptic wrap
# ---------------------------------------------------------------------------


def test_cli_init_dry_run_json(tmp_path: Path) -> None:
    """skeptic init --dry-run --json outputs JSON without writing skeptic.yaml (S2)."""
    shutil.copy2(FIXTURES_DIR / "generic" / ".mcp.json", tmp_path / ".mcp.json")

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--dry-run", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["schema"] == "skeptic.config/v1"
    assert "generic_stdio" in parsed["servers"]
    assert not (tmp_path / "skeptic.yaml").exists()


def test_cli_init_generates_valid_yaml_and_refuses_overwrite_without_yes(
    tmp_path: Path,
) -> None:
    """skeptic init generates valid skeptic.yaml and requires --yes to overwrite."""
    shutil.copy2(FIXTURES_DIR / "generic" / ".mcp.json", tmp_path / ".mcp.json")

    # 1. Normal init creates skeptic.yaml
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    yaml_file = tmp_path / "skeptic.yaml"
    assert yaml_file.is_file()

    cfg = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    jsonschema.validate(cfg, _load_config_schema())

    # 2. Re-running without --yes fails with code 2
    res2 = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert res2.exit_code == 2
    assert "already exists" in res2.stderr

    # 3. Re-running with --yes succeeds
    res3 = runner.invoke(app, ["init", "--path", str(tmp_path), "--yes"])
    assert res3.exit_code == 0


def test_cli_wrap_and_undo(tmp_path: Path) -> None:
    """skeptic wrap rewrites client config and --undo restores byte-for-byte."""
    dest = tmp_path / ".mcp.json"
    shutil.copy2(FIXTURES_DIR / "generic" / ".mcp.json", dest)
    orig_bytes = dest.read_bytes()

    # Wrap via CLI
    res = runner.invoke(app, ["wrap", str(dest), "--all", "--profile", "silent-core"])
    assert res.exit_code == 0
    assert dest.read_bytes() != orig_bytes
    assert Path(f"{dest}.skeptic.bak").is_file()

    # Undo via CLI
    res_undo = runner.invoke(app, ["wrap", str(dest), "--undo"])
    assert res_undo.exit_code == 0
    assert not Path(f"{dest}.skeptic.bak").exists()
    assert dest.read_bytes() == orig_bytes


def test_cli_wrap_validations(tmp_path: Path) -> None:
    """CLI wrap validates missing file, missing targets, unknown servers, missing backup."""
    # File not found
    res = runner.invoke(app, ["wrap", str(tmp_path / "missing.json"), "--all"])
    assert res.exit_code == 2

    # Neither --all nor --server
    dest = tmp_path / ".mcp.json"
    shutil.copy2(FIXTURES_DIR / "generic" / ".mcp.json", dest)
    res2 = runner.invoke(app, ["wrap", str(dest)])
    assert res2.exit_code == 2

    # Server not found
    res3 = runner.invoke(app, ["wrap", str(dest), "--server", "unknown_srv"])
    assert res3.exit_code == 2

    # Undo without backup
    res4 = runner.invoke(app, ["wrap", str(dest), "--undo"])
    assert res4.exit_code == 2


# ---------------------------------------------------------------------------
# Unit and Edge Case Tests
# ---------------------------------------------------------------------------


def test_discovered_server_to_config_dict() -> None:
    """DiscoveredServer formats dictionary for both stdio and http correctly."""
    stdio_srv = DiscoveredServer(
        name="test_stdio",
        client="generic",
        source_path=Path(".mcp.json"),
        scope="project",
        transport="stdio",
        command=["python", "test.py"],
        env={"A": "1"},
    )
    d_stdio = stdio_srv.to_config_dict()
    assert d_stdio == {
        "transport": "stdio",
        "command": ["python", "test.py"],
        "env": {"A": "1"},
    }

    http_srv = DiscoveredServer(
        name="test_http",
        client="generic",
        source_path=Path(".mcp.json"),
        scope="project",
        transport="http",
        url="http://example.com/mcp",
        headers={"H": "v"},
    )
    d_http = http_srv.to_config_dict()
    assert d_http == {
        "transport": "http",
        "url": "http://example.com/mcp",
        "headers": {"H": "v"},
    }


def test_generate_config_empty_raises_value_error() -> None:
    """generate_config raises ValueError if servers dict is empty."""
    with pytest.raises(ValueError, match="without any servers"):
        generate_config({})


def test_resolve_claude_paths(tmp_path: Path) -> None:
    """Claude paths check AppData, Application Support and .config."""
    paths = _resolve_claude_paths(tmp_path)
    assert any("Claude" in str(p) for p in paths)
    assert any("AppData" in str(p) for p in paths)


def test_parse_client_file_missing_file(tmp_path: Path) -> None:
    """Non-existent file returns empty dict."""
    res = parse_client_file(tmp_path / "non_existent.json")
    assert res == {}


def test_parse_client_file_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON returns empty dict."""
    p = tmp_path / ".mcp.json"
    p.write_text("invalid json {{{", encoding="utf-8")
    assert parse_client_file(p) == {}


def test_parse_client_file_non_dict_json(tmp_path: Path) -> None:
    """JSON with top-level array returns empty dict."""
    p = tmp_path / ".mcp.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert parse_client_file(p) == {}


def test_parse_standard_json_missing_mcp_servers(tmp_path: Path) -> None:
    """Missing mcpServers in standard JSON returns empty dict."""
    p = tmp_path / ".mcp.json"
    res = _parse_standard_json(p, {"other": {}}, client="generic", scope="project")
    assert res == {}


def test_parse_vscode_json_missing_servers(tmp_path: Path) -> None:
    """Missing servers in VS Code JSON returns empty dict."""
    p = tmp_path / ".vscode" / "mcp.json"
    res = _parse_vscode_json(p, {"other": {}}, scope="project")
    assert res == {}


def test_parse_codex_toml_invalid(tmp_path: Path) -> None:
    """Invalid TOML or missing mcp_servers table returns empty dict."""
    p = tmp_path / "config.toml"
    p.write_text("invalid toml === [[[", encoding="utf-8")
    assert _parse_codex_toml(p, scope="project") == {}

    p.write_text("key = 'value'\n", encoding="utf-8")
    assert _parse_codex_toml(p, scope="project") == {}


def test_get_discovery_candidates_order(tmp_path: Path) -> None:
    """get_discovery_candidates returns candidates in canonical order."""
    candidates = get_discovery_candidates(base_dir=tmp_path, home_dir=tmp_path / "home")
    clients = [c[0] for c in candidates]
    assert clients[0] == "generic"
    assert "claude" in clients
    assert "cursor" in clients
    assert "vscode" in clients
    assert "codex" in clients
    assert "gemini" in clients


def test_discover_empty_dir(tmp_path: Path) -> None:
    """discover on empty dir returns empty mapping."""
    res = discover(base_dir=tmp_path, home_dir=tmp_path / "empty_home")
    assert res == {}


def test_undo_wrap_missing_backup_raises(tmp_path: Path) -> None:
    """undo_wrap raises FileNotFoundError if backup does not exist."""
    f = tmp_path / "test.json"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Backup file not found"):
        undo_wrap(f)


def test_wrap_file_missing_file_raises(tmp_path: Path) -> None:
    """wrap_file raises FileNotFoundError if target file does not exist."""
    with pytest.raises(FileNotFoundError, match="not found"):
        wrap_file(tmp_path / "missing.json", all_servers=True)


def test_wrap_file_no_servers_specified_raises(tmp_path: Path) -> None:
    """wrap_file raises ValueError if neither all_servers nor servers is given."""
    f = tmp_path / "test.json"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Must specify either all_servers"):
        wrap_file(f)


def test_wrap_file_invalid_json_raises(tmp_path: Path) -> None:
    """wrap_file raises ValueError on malformed JSON."""
    f = tmp_path / "test.json"
    f.write_text("invalid json {{{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        wrap_file(f, all_servers=True)


def test_wrap_file_unsupported_json_structure_raises(tmp_path: Path) -> None:
    """wrap_file raises ValueError when JSON lacks servers and mcpServers."""
    f = tmp_path / "test.json"
    f.write_text(json.dumps({"unknownKey": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="No servers or mcpServers"):
        wrap_file(f, all_servers=True)


def test_wrap_file_unknown_server_name_raises(tmp_path: Path) -> None:
    """wrap_file raises ValueError if requested server is not present."""
    f = tmp_path / "test.json"
    f.write_text(json.dumps({"mcpServers": {"known": {"command": "cmd"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Server 'missing' not found"):
        wrap_file(f, servers=["missing"])


def test_wrap_file_toml_missing_table_raises(tmp_path: Path) -> None:
    """wrap_file raises ValueError on TOML lacking mcp_servers table."""
    f = tmp_path / "config.toml"
    f.write_text("model = 'gpt-4o'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No mcp_servers table found"):
        wrap_file(f, all_servers=True)


def test_rewrite_toml_section_missing_keys_inserted() -> None:
    """_rewrite_toml_section inserts missing command/args before next section."""
    lines = [
        "[mcp_servers.test]\n",
        "# comment\n",
        "[other_section]\n",
        "key = 1\n",
    ]
    res = _rewrite_toml_section(
        lines,
        server_name="test",
        new_command="skeptic",
        new_args=["proxy", "stdio"],
    )
    res_text = "".join(res)
    assert 'command = "skeptic"' in res_text
    assert 'args = ["proxy", "stdio"]' in res_text


def test_register_http_upstream_creates_new_yaml(tmp_path: Path) -> None:
    """_register_http_upstream creates valid skeptic.yaml if none exists."""
    _register_http_upstream(
        base_dir=tmp_path,
        server_name="test_remote",
        upstream_url="https://upstream.example.com/mcp",
        headers={"X-Test": "1"},
    )
    yaml_file = tmp_path / "skeptic.yaml"
    assert yaml_file.is_file()
    content = yaml_file.read_text(encoding="utf-8")
    assert "https://upstream.example.com/mcp" in content
    assert "X-Test" in content
