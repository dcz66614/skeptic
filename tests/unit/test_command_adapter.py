"""Unit tests for CommandAdapter (S13.1, S13.2, S13.4, E45)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from skeptic_agent.runner.adapters import ADAPTERS, get_adapter
from skeptic_agent.runner.adapters.base import EpisodeTask, McpServerSpec
from skeptic_agent.runner.adapters.command import (
    DEFAULT_PRESETS,
    CommandAdapter,
    _parse_cli_output,
    format_command,
    resolve_preset,
    write_mcp_configs,
)

pytestmark = pytest.mark.unit

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_adapter_registration() -> None:
    """Verify command is registered in ADAPTERS and conforms to AgentAdapter protocol."""
    assert "command" in ADAPTERS
    adapter = get_adapter("command")
    assert isinstance(adapter, CommandAdapter)
    assert adapter.name == "command"
    assert hasattr(adapter, "run")
    assert callable(adapter.run)


def test_default_presets_definitions() -> None:
    """Verify built-in default presets for Claude Code, Codex CLI, and Gemini CLI."""
    assert "claude" in DEFAULT_PRESETS
    assert "codex" in DEFAULT_PRESETS
    assert "gemini" in DEFAULT_PRESETS

    claude_cmd = DEFAULT_PRESETS["claude"]["cmd"]
    assert "claude" in claude_cmd
    assert "-p" in claude_cmd
    assert "--dangerously-skip-permissions" in claude_cmd

    codex_cmd = DEFAULT_PRESETS["codex"]["cmd"]
    assert "codex" in codex_cmd
    assert "exec" in codex_cmd
    assert "--approval-level" in codex_cmd

    gemini_cmd = DEFAULT_PRESETS["gemini"]["cmd"]
    assert "gemini" in gemini_cmd
    assert "--non-interactive" in gemini_cmd


def test_write_mcp_configs(tmp_path: Path) -> None:
    """Verify MCP configuration files generated in workdir (ADR-0005, S15)."""
    servers = [
        McpServerSpec(
            name="weather",
            command=["python", "-m", "skeptic_agent.sandboxes.sb_weather"],
            env={"SERVER_KEY": "val1"},
        ),
        McpServerSpec(
            name="mail",
            command=["node", "mail_server.js"],
            env={"MAIL_PORT": "5000"},
        ),
    ]
    base_env = {"BASE_VAR": "base_val"}

    write_mcp_configs(tmp_path, servers, base_env)

    # 1. Check .mcp.json
    mcp_file = tmp_path / ".mcp.json"
    assert mcp_file.is_file()
    mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "mcpServers" in mcp_data
    assert "weather" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["weather"]["command"] == "python"
    assert mcp_data["mcpServers"]["weather"]["args"] == [
        "-m",
        "skeptic_agent.sandboxes.sb_weather",
    ]
    assert mcp_data["mcpServers"]["weather"]["env"]["BASE_VAR"] == "base_val"
    assert mcp_data["mcpServers"]["weather"]["env"]["SERVER_KEY"] == "val1"

    # 2. Check .cursor/mcp.json
    cursor_file = tmp_path / ".cursor" / "mcp.json"
    assert cursor_file.is_file()
    cursor_data = json.loads(cursor_file.read_text(encoding="utf-8"))
    assert "weather" in cursor_data["mcpServers"]

    # 3. Check .gemini/settings.json
    gemini_file = tmp_path / ".gemini" / "settings.json"
    assert gemini_file.is_file()
    gemini_data = json.loads(gemini_file.read_text(encoding="utf-8"))
    assert "mail" in gemini_data["mcpServers"]

    # 4. Check .codex/config.toml
    codex_file = tmp_path / ".codex" / "config.toml"
    assert codex_file.is_file()
    codex_text = codex_file.read_text(encoding="utf-8")
    assert "[mcp_servers.weather]" in codex_text
    assert 'command = "python"' in codex_text
    assert "[mcp_servers.weather.env]" in codex_text
    assert 'SERVER_KEY = "val1"' in codex_text


def test_resolve_preset_with_skeptic_yaml(tmp_path: Path) -> None:
    """Verify preset resolution loads custom presets from skeptic.yaml."""
    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "custom_list": {
                "cmd": ["my-agent", "--prompt", "{prompt}"],
                "env": {"MODE": "test"},
            },
            "custom_str": {
                "cmd": "agent-cli -q '{prompt}'",
            },
            "custom_bare_list": ["bare-runner", "{prompt}"],
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    # List cmd with env
    cmd1, env1 = resolve_preset("custom_list", workdir=tmp_path)
    assert cmd1 == ["my-agent", "--prompt", "{prompt}"]
    assert env1 == {"MODE": "test"}

    # String cmd
    cmd2, env2 = resolve_preset("custom_str", workdir=tmp_path)
    assert cmd2[0] == "agent-cli"
    assert env2 == {}

    # Bare list
    cmd3, env3 = resolve_preset("custom_bare_list", workdir=tmp_path)
    assert cmd3 == ["bare-runner", "{prompt}"]
    assert env3 == {}


def test_resolve_preset_builtin_and_fallback(tmp_path: Path) -> None:
    """Verify built-in presets and worker CLI fallback."""
    # Built-in claude
    cmd_claude, env_claude = resolve_preset("claude", workdir=tmp_path)
    assert cmd_claude[0] == "claude"
    assert env_claude == {}

    # Fake script resolves to worker CLI
    cmd_fake, _ = resolve_preset("fake/oracle_follower", workdir=tmp_path)
    assert cmd_fake[0] == sys.executable
    assert "skeptic_agent.runner.adapters.command" in cmd_fake
    assert "--model" in cmd_fake
    assert "fake/oracle_follower" in cmd_fake

    # Unknown preset raises ValueError
    with pytest.raises(ValueError, match="Unknown command preset"):
        resolve_preset("nonexistent_unknown_preset_123", workdir=tmp_path)


def test_format_command(tmp_path: Path) -> None:
    """Verify substitution of template variables into command arguments."""
    task = EpisodeTask(
        episode_id="ep-001",
        prompt="Find weather in Paris\n\nReturn number",
        servers=[],
        model="codex",
        max_steps=10,
        timeout_s=60,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    template = ["agent", "-p", "{prompt}", "--workdir", "{workdir}", "--timeout", "{timeout_s}"]
    formatted, prompt_in_args = format_command(template, task)

    assert prompt_in_args is True
    assert formatted[0] == "agent"
    assert formatted[1] == "-p"
    assert formatted[2] == "Find weather in Paris\n\nReturn number"
    assert formatted[4] == str(tmp_path.resolve())
    assert formatted[6] == "60"

    # Template without {prompt}
    template_no_prompt = ["agent", "--auto"]
    _, prompt_in_args2 = format_command(template_no_prompt, task)
    assert prompt_in_args2 is False


def test_parse_cli_output() -> None:
    """Verify parsing stdout into final_answer, usage, and step counts."""
    # 1. Plain text with ANSI escape codes
    ansi_text = "\x1b[32m14.5\x1b[0m"
    ans1, _, steps1 = _parse_cli_output(ansi_text)
    assert ans1 == "14.5"
    assert steps1 == 1

    # 2. JSON structured output
    json_text = json.dumps(
        {
            "final_answer": "14.5",
            "steps": 3,
            "usage": {
                "tokens_in": 150,
                "tokens_out": 30,
                "cost_usd": 0.001,
                "tool_calls": 2,
            },
        }
    )
    ans2, usage2, steps2 = _parse_cli_output(json_text)
    assert ans2 == "14.5"
    assert steps2 == 3
    assert usage2.tokens_in == 150
    assert usage2.tokens_out == 30
    assert usage2.cost_usd == 0.001
    assert usage2.tool_calls == 2

    # 3. Empty output
    ans3, _, steps3 = _parse_cli_output("")
    assert ans3 == ""
    assert steps3 == 0


@pytest.mark.asyncio
async def test_run_success_plain_python(tmp_path: Path) -> None:
    """Verify CommandAdapter executes a simple python subprocess and captures output."""
    adapter = CommandAdapter()

    # Create a skeptic.yaml with a custom python runner
    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "py_echo": {
                "cmd": [sys.executable, "-c", "import sys; print('14.5')"],
            }
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    task = EpisodeTask(
        episode_id="ep-test-echo",
        prompt="Tell me temperature",
        servers=[],
        model="py_echo",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "14.5"
    assert result.steps == 1
    assert len(result.transcript) == 2
    assert result.transcript[0]["role"] == "user"
    assert result.transcript[1] == {"role": "assistant", "content": "14.5"}


@pytest.mark.asyncio
async def test_run_stdin_prompt(tmp_path: Path) -> None:
    """Verify CommandAdapter writes task.prompt to stdin when {prompt} is not in cmd args."""
    adapter = CommandAdapter()

    code = "import sys; content = sys.stdin.read().strip(); print(f'ECHO: {content}')"
    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "py_stdin": {
                "cmd": [sys.executable, "-c", code],
            }
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    task = EpisodeTask(
        episode_id="ep-test-stdin",
        prompt="Hello from skeptic",
        servers=[],
        model="py_stdin",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == "ECHO: Hello from skeptic"


@pytest.mark.asyncio
async def test_run_timeout_handling(tmp_path: Path) -> None:
    """Verify CommandAdapter terminates hung processes and returns empty answer (S13.3)."""
    adapter = CommandAdapter()

    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "py_sleep": {
                "cmd": [sys.executable, "-c", "import time; time.sleep(10)"],
            }
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    task = EpisodeTask(
        episode_id="ep-test-timeout",
        prompt="Quick task",
        servers=[],
        model="py_sleep",
        max_steps=7,
        timeout_s=1,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is None
    assert result.final_answer == ""
    assert result.steps == 7


@pytest.mark.asyncio
async def test_run_nonzero_exit_code_captured_as_error(tmp_path: Path) -> None:
    """Verify non-zero process exit codes are captured as infra errors (S10.2 rule 2)."""
    adapter = CommandAdapter()

    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "py_fail": {
                "cmd": [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('Fatal crash occurred'); sys.exit(42)",
                ],
            }
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    task = EpisodeTask(
        episode_id="ep-test-fail",
        prompt="Crash test",
        servers=[],
        model="py_fail",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is not None
    assert "exited with code 42" in result.error
    assert "Fatal crash occurred" in result.error
    assert result.final_answer == ""


@pytest.mark.asyncio
async def test_run_executable_not_found(tmp_path: Path) -> None:
    """Verify missing binary on PATH returns descriptive error without crashing."""
    adapter = CommandAdapter()

    config_data = {
        "schema": "skeptic.config/v1",
        "project": "test-agent",
        "agents": {
            "missing_cli": {
                "cmd": ["nonexistent_binary_xyz_12345", "--opt"],
            }
        },
    }
    (tmp_path / "skeptic.yaml").write_text(yaml.safe_dump(config_data), encoding="utf-8")

    task = EpisodeTask(
        episode_id="ep-test-missing",
        prompt="Missing test",
        servers=[],
        model="missing_cli",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    result = await adapter.run(task)
    assert result.error is not None
    assert "Command executable not found on PATH" in result.error
