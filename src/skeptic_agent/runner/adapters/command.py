"""Universal Command-line Agent Adapter (S13.1, S13.2, S13.4, E45, beta).

Interfaces Skeptic with external CLI agents (Claude Code, Codex CLI, Gemini CLI)
and custom command presets defined in ``skeptic.yaml`` under ``agents.<preset>.cmd``.
Prepares standard MCP configuration files in the episode workdir, executes the command,
and manages subprocess lifecycle and MCP client termination.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

import yaml

from skeptic_agent.runner.adapters.base import (
    AgentRunResult,
    EpisodeTask,
    McpServerSpec,
    Usage,
)
from skeptic_agent.runner.reference_agent import ReferenceAgent
from skeptic_agent.scenario.model import load_scenario

ROOT_DIR = Path(__file__).resolve().parents[4]

ANSI_ESCAPE_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

DEFAULT_PRESETS: dict[str, dict[str, Any]] = {
    "claude": {
        "cmd": ["claude", "-p", "{prompt}", "--dangerously-skip-permissions"],
        "description": "Claude Code CLI non-interactive headless preset (beta)",
        "config_type": "mcp_json",
    },
    "codex": {
        "cmd": ["codex", "exec", "--prompt", "{prompt}", "--approval-level", "full-auto"],
        "description": "Codex CLI non-interactive headless preset (beta)",
        "config_type": "codex_toml",
    },
    "gemini": {
        "cmd": ["gemini", "--prompt", "{prompt}", "--non-interactive"],
        "description": "Gemini CLI non-interactive headless preset (beta)",
        "config_type": "gemini_json",
    },
}


def write_mcp_configs(
    workdir: Path,
    servers: list[McpServerSpec],
    base_env: dict[str, str],
) -> None:
    """Generate configuration files for all supported MCP CLI tools (S15, ADR-0005, E45).

    Files generated in ``workdir``:
        - ``.mcp.json`` (Claude Code, Cursor, and project-level MCP)
        - ``.cursor/mcp.json`` (Cursor IDE)
        - ``.codex/config.toml`` (Codex CLI)
        - ``.gemini/settings.json`` (Gemini CLI)
    """
    workdir.mkdir(parents=True, exist_ok=True)

    # 1. Project-level .mcp.json (Claude Code, Cursor, standard MCP)
    mcp_servers_dict: dict[str, Any] = {}
    for s in servers:
        cmd = s.command[0] if s.command else ""
        args = s.command[1:] if len(s.command) > 1 else []
        env = {**base_env, **s.env}
        mcp_servers_dict[s.name] = {
            "command": cmd,
            "args": args,
            "env": env,
        }

    mcp_json_content = json.dumps({"mcpServers": mcp_servers_dict}, indent=2)
    (workdir / ".mcp.json").write_text(mcp_json_content, encoding="utf-8")

    # 2. .cursor/mcp.json
    cursor_dir = workdir / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    (cursor_dir / "mcp.json").write_text(mcp_json_content, encoding="utf-8")

    # 3. .gemini/settings.json
    gemini_dir = workdir / ".gemini"
    gemini_dir.mkdir(parents=True, exist_ok=True)
    (gemini_dir / "settings.json").write_text(mcp_json_content, encoding="utf-8")

    # 4. .codex/config.toml
    codex_dir = workdir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    toml_lines: list[str] = []
    for s in servers:
        cmd = s.command[0] if s.command else ""
        args = s.command[1:] if len(s.command) > 1 else []
        env = {**base_env, **s.env}
        toml_lines.append(f"[mcp_servers.{s.name}]")
        toml_lines.append(f"command = {json.dumps(cmd)}")
        toml_lines.append(f"args = {json.dumps(args)}")
        if env:
            toml_lines.append(f"[mcp_servers.{s.name}.env]")
            for k, v in env.items():
                toml_lines.append(f"{k} = {json.dumps(v)}")
        toml_lines.append("")
    (codex_dir / "config.toml").write_text("\n".join(toml_lines), encoding="utf-8")


def load_presets_from_config(workdir: Path | None = None) -> dict[str, Any]:
    """Load agent presets defined in skeptic.yaml (S13.1, E45)."""
    candidates: list[Path] = []
    if workdir is not None:
        candidates.append(workdir / "skeptic.yaml")
    candidates.append(Path.cwd() / "skeptic.yaml")
    candidates.append(ROOT_DIR / "skeptic.yaml")

    for path in candidates:
        if path.is_file():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "agents" in data and isinstance(data["agents"], dict):
                    return data["agents"]
            except Exception:
                pass
    return {}


def resolve_preset(
    preset_name: str,
    workdir: Path | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Resolve a command preset into an invocation command template and environment (S13.1, E45).

    Args:
        preset_name: Name of preset (e.g. 'claude', 'codex', 'gemini', 'fake/oracle_follower').
        workdir: Working directory to look for skeptic.yaml.

    Returns:
        (command_template_list, env_dict)
    """
    config_presets = load_presets_from_config(workdir)

    if preset_name in config_presets:
        item = config_presets[preset_name]
        if isinstance(item, dict):
            cmd_val = item.get("cmd")
            env_val = item.get("env", {})
            if isinstance(cmd_val, list):
                return [str(x) for x in cmd_val], {str(k): str(v) for k, v in env_val.items()}
            if isinstance(cmd_val, str):
                return (
                    shlex.split(cmd_val, posix=sys.platform != "win32"),
                    {str(k): str(v) for k, v in env_val.items()},
                )
        elif isinstance(item, list):
            return [str(x) for x in item], {}
        elif isinstance(item, str):
            return shlex.split(item, posix=sys.platform != "win32"), {}

    if preset_name in DEFAULT_PRESETS:
        default_cmd = DEFAULT_PRESETS[preset_name]["cmd"]
        return list(default_cmd), {}

    # Built-in worker CLI for fake scripts, reference agent, or direct models
    if (
        preset_name.startswith("fake/")
        or preset_name in ("fake", "reference")
        or preset_name.startswith(("openrouter/", "openai/", "compat/"))
    ):
        worker_cmd = [
            sys.executable,
            "-m",
            "skeptic_agent.runner.adapters.command",
            "--model",
            preset_name,
            "--workdir",
            "{workdir}",
            "--prompt",
            "{prompt}",
            "--prompt-variant",
            "{prompt_variant}",
            "--max-steps",
            "{max_steps}",
            "--timeout-s",
            "{timeout_s}",
            "--json",
        ]
        return worker_cmd, {}

    # Check if preset looks like a command string or path
    if (
        " " in preset_name
        or "/" in preset_name
        or "\\" in preset_name
        or shutil.which(preset_name) is not None
    ):
        return shlex.split(preset_name, posix=sys.platform != "win32"), {}

    raise ValueError(
        f"Unknown command preset: {preset_name!r}. "
        f"Define it in skeptic.yaml under agents.{preset_name}.cmd "
        f"or use a built-in preset ({list(DEFAULT_PRESETS.keys())})."
    )


def format_command(
    cmd_template: list[str],
    task: EpisodeTask,
) -> tuple[list[str], bool]:
    """Substitute template variables into the command arguments list.

    Returns:
        (formatted_cmd_args, prompt_was_substituted_in_args)
    """
    substitutions: dict[str, str] = {
        "{prompt}": task.prompt,
        "{workdir}": str(task.workdir.resolve()),
        "{timeout_s}": str(task.timeout_s),
        "{model}": task.model,
        "{preset}": task.model,
        "{episode_id}": task.episode_id,
        "{prompt_variant}": task.prompt_variant,
        "{max_steps}": str(task.max_steps),
    }

    formatted: list[str] = []
    prompt_substituted = False

    for arg in cmd_template:
        val = arg
        if "{prompt}" in val:
            prompt_substituted = True
        for placeholder, replacement in substitutions.items():
            if placeholder in val:
                val = val.replace(placeholder, replacement)
        formatted.append(val)

    return formatted, prompt_substituted


def _parse_cli_output(
    raw_stdout: str,
    default_steps: int = 1,
) -> tuple[str, Usage, int]:
    """Parse CLI stdout into final_answer, usage, and step counts."""
    clean = ANSI_ESCAPE_RE.sub("", raw_stdout).strip()
    if not clean:
        return "", Usage(), 0

    # 1. Try parsing full string as JSON
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            final_ans = str(data.get("final_answer", data.get("answer", data.get("output", ""))))
            steps = int(data.get("steps", default_steps))
            usage_dict = data.get("usage", {})
            usage = Usage(
                tokens_in=int(usage_dict.get("tokens_in", 0)),
                tokens_out=int(usage_dict.get("tokens_out", 0)),
                cost_usd=float(usage_dict.get("cost_usd", 0.0)),
                steps=steps,
                tool_calls=int(usage_dict.get("tool_calls", 0)),
            )
            return final_ans, usage, steps
    except Exception:
        pass

    # 2. Try parsing embedded JSON object
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "final_answer" in data:
                final_ans = str(data["final_answer"])
                steps = int(data.get("steps", default_steps))
                usage_dict = data.get("usage", {})
                usage = Usage(
                    tokens_in=int(usage_dict.get("tokens_in", 0)),
                    tokens_out=int(usage_dict.get("tokens_out", 0)),
                    cost_usd=float(usage_dict.get("cost_usd", 0.0)),
                    steps=steps,
                    tool_calls=int(usage_dict.get("tool_calls", 0)),
                )
                return final_ans, usage, steps
        except Exception:
            pass

    # 3. Plain text fallback
    return clean, Usage(steps=default_steps), default_steps


class CommandAdapter:
    """Universal Command-line Agent Adapter (S13.1, S13.2, S13.4, E45, beta).

    Executes external headless CLI agents (e.g. Claude Code, Codex CLI, Gemini CLI)
    or custom commands configured in ``skeptic.yaml`` under ``agents.<preset>.cmd``.
    Prepares standard MCP configuration files in the episode working directory
    and manages subprocess execution, timeouts, and clean resource termination.
    """

    name: str = "command"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Execute the command agent task (S13.2, E45)."""
        # 1. Prepare MCP server configurations in task.workdir (ADR-0005, S15)
        write_mcp_configs(task.workdir, task.servers, task.env)

        # 2. Resolve preset command template and environment
        try:
            cmd_template, extra_env = resolve_preset(task.model, task.workdir)
        except Exception as exc:
            return AgentRunResult(
                final_answer="",
                usage=Usage(),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=f"Failed to resolve command preset {task.model!r}: {exc}",
            )

        # 3. Format command arguments with placeholders
        formatted_cmd, prompt_in_args = format_command(cmd_template, task)
        if not formatted_cmd:
            return AgentRunResult(
                final_answer="",
                usage=Usage(),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error="Resolved command argument list is empty",
            )

        # 4. Resolve executable on PATH
        raw_exe = formatted_cmd[0]
        resolved_exe = shutil.which(raw_exe)
        if resolved_exe is None:
            return AgentRunResult(
                final_answer="",
                usage=Usage(),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=f"Command executable not found on PATH: {raw_exe!r}",
            )

        cmd_exec = list(formatted_cmd)
        cmd_exec[0] = resolved_exe

        # On Windows, batch/cmd scripts must be launched via cmd.exe /c
        if sys.platform == "win32" and resolved_exe.lower().endswith((".cmd", ".bat")):
            cmd_exec = ["cmd.exe", "/c", *cmd_exec]

        # 5. Prepare environment variables
        env = dict(os.environ)
        env.update(task.env)
        env.update(extra_env)
        env["MCP_CONFIG_PATH"] = str((task.workdir / ".mcp.json").resolve())
        env["SKEPTIC_EPISODE_ID"] = task.episode_id
        env["SKEPTIC_PROMPT"] = task.prompt

        # Determine stdin input
        stdin_bytes: bytes | None = None
        if not prompt_in_args:
            stdin_bytes = task.prompt.encode("utf-8")

        # 6. Execute subprocess with timeout and process lifecycle control
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_exec,
                stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(task.workdir),
                env=env,
            )
        except Exception as exc:
            return AgentRunResult(
                final_answer="",
                usage=Usage(),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=f"Failed to spawn command process {cmd_exec[0]!r}: {exc}",
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_bytes),
                timeout=float(task.timeout_s),
            )
        except TimeoutError:
            with contextlib.suppress(Exception):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except Exception:
                with contextlib.suppress(Exception):
                    proc.kill()
                    await proc.wait()

            # Per S13.3: when max_steps / timeout is reached, return empty answer
            return AgentRunResult(
                final_answer="",
                usage=Usage(steps=task.max_steps),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=task.max_steps,
                error=None,
            )
        finally:
            if proc.returncode is None:
                with contextlib.suppress(Exception):
                    proc.terminate()

        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()

        # 7. Check non-zero exit code (infra error)
        if proc.returncode != 0:
            err_msg = stderr_text or stdout_text or f"Process exited with code {proc.returncode}"
            return AgentRunResult(
                final_answer="",
                usage=Usage(),
                transcript=[{"role": "user", "content": task.prompt}],
                steps=0,
                error=f"Command exited with code {proc.returncode}: {err_msg}",
            )

        # 8. Parse output and return result
        final_answer, usage, steps = _parse_cli_output(stdout_text, default_steps=1)
        transcript: list[dict[str, Any]] = [
            {"role": "user", "content": task.prompt},
        ]
        if final_answer:
            transcript.append({"role": "assistant", "content": final_answer})

        return AgentRunResult(
            final_answer=final_answer,
            usage=usage,
            transcript=transcript,
            steps=steps,
            error=None,
        )


async def _run_worker(
    prompt: str,
    model: str,
    workdir: Path,
    prompt_variant: Literal["plain", "evidence_contract"] = "plain",
    max_steps: int = 12,
    timeout_s: int = 180,
    mcp_config_path: Path | None = None,
    as_json: bool = False,
) -> int:
    """Subprocess worker CLI executing ReferenceAgent / FakeLLM with MCP clients (S13.3, E45)."""
    config_file = mcp_config_path or (workdir / ".mcp.json")
    servers: list[McpServerSpec] = []
    if config_file.is_file():
        try:
            data = json.loads(config_file.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, s_cfg in mcp_servers.items():
                cmd = s_cfg.get("command", "")
                args = s_cfg.get("args", [])
                full_cmd = [cmd, *args] if isinstance(args, list) else [cmd]
                env = s_cfg.get("env", {})
                servers.append(McpServerSpec(name=name, command=full_cmd, env=env))
        except Exception as exc:
            sys.stderr.write(f"Failed to read MCP config {config_file}: {exc}\n")
            return 1

    scenario_file = workdir / "scenario.yaml"
    scenario_obj = None
    if scenario_file.is_file():
        with contextlib.suppress(Exception):
            scenario_obj = load_scenario(scenario_file)

    task = EpisodeTask(
        episode_id="command_worker",
        prompt=prompt,
        servers=servers,
        model=model,
        max_steps=max_steps,
        timeout_s=timeout_s,
        prompt_variant=prompt_variant,
        workdir=workdir,
        env=dict(os.environ),
        scenario=scenario_obj,
    )

    agent = ReferenceAgent()
    res = await agent.run(task)

    if res.error:
        sys.stderr.write(f"Worker agent error: {res.error}\n")
        return 1

    if as_json:
        out = {
            "final_answer": res.final_answer,
            "steps": res.steps,
            "usage": {
                "tokens_in": res.usage.tokens_in,
                "tokens_out": res.usage.tokens_out,
                "cost_usd": res.usage.cost_usd,
                "tool_calls": res.usage.tool_calls,
            },
        }
        sys.stdout.write(json.dumps(out) + "\n")
    else:
        sys.stdout.write(res.final_answer + "\n")

    return 0


def main() -> None:
    """CLI entrypoint for running command worker (E45)."""
    parser = argparse.ArgumentParser(description="Skeptic Command Adapter Worker (E45)")
    parser.add_argument("--model", "--preset", dest="model", default="fake/oracle_follower")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--prompt-variant", default="plain", choices=["plain", "evidence_contract"])
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--mcp-config", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    exit_code = asyncio.run(
        _run_worker(
            prompt=args.prompt,
            model=args.model,
            workdir=Path(args.workdir).resolve(),
            prompt_variant=args.prompt_variant,
            max_steps=args.max_steps,
            timeout_s=args.timeout_s,
            mcp_config_path=Path(args.mcp_config).resolve() if args.mcp_config else None,
            as_json=args.json,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
