# Universal Command-Line Agent Adapter (`command`, beta)

> **Status: Beta**
> The `command` adapter is in beta. It interfaces Skeptic with external command-line agent binaries and headless CLI tools.

This document records the configuration, versioning, default prompt settings, preset command templates, and timeout controls for the Universal Command-line Agent adapter (`command`), satisfying S13.1, S13.2, S13.4, and E45 specifications.

## 1. Framework Version and Overview

- **Adapter Identifier**: `command` (`command:<preset>`)
- **Status**: Beta
- **Specification**: S13.1, S13.2, S13.4, E45
- **Role**: Dispatches tasks to external command-line agent processes, headless CLI tools, or script wrappers.
- **Integration Architecture**:
  - Configuration Generator: Before executing the command, the adapter prepares standard MCP configuration files in the episode working directory (`task.workdir`):
    - `.mcp.json` (Project-level, Claude Code, Cursor)
    - `.cursor/mcp.json` (Cursor IDE)
    - `.codex/config.toml` (Codex CLI)
    - `.gemini/settings.json` (Gemini CLI)
  - Process Runner: Executes the agent command as an asynchronous subprocess via `asyncio.create_subprocess_exec` with piped standard I/O.
  - Lifecycle Supervision: Tracks process timeouts, drains and sanitizes stdout/stderr (stripping ANSI escapes), and cleans up child processes and stdio sessions upon completion or error.

## 2. Presets & Headless Command Templates

The adapter provides built-in default presets for the leading agent CLIs, which can be overridden or extended in `skeptic.yaml` under `agents.<preset>.cmd`:

### 2.1 Claude Code (`claude`)
- **CLI Package**: `@anthropic-ai/claude-code` (npm)
- **Command Template**:
  ```bash
  claude -p "{prompt}" --dangerously-skip-permissions
  ```
- **Headless Mode**: The `-p` (or `--print`) flag runs Claude Code in non-interactive print mode, streaming output directly to stdout and terminating when finished. The `--dangerously-skip-permissions` flag disables interactive user approval prompts for tool execution in automated benchmarking environments.
- **MCP Config**: Automatically detects and loads `./.mcp.json` generated in `task.workdir`.

### 2.2 Codex CLI (`codex`)
- **CLI Package**: `@openai/codex` / `codex-cli`
- **Command Template**:
  ```bash
  codex exec --prompt "{prompt}" --approval-level full-auto
  ```
- **Headless Mode**: `codex exec` executes the prompt non-interactively without launching the TUI terminal interface, using `--approval-level full-auto` for autonomous tool execution.
- **MCP Config**: Automatically detects and loads `.codex/config.toml` generated in `task.workdir`.

### 2.3 Gemini CLI (`gemini`)
- **CLI Package**: `@google/gemini-cli`
- **Command Template**:
  ```bash
  gemini --prompt "{prompt}" --non-interactive
  ```
- **Headless Mode**: The `--non-interactive` flag runs without human intervention and outputs the agent's completion to stdout.
- **MCP Config**: Automatically detects and loads `.gemini/settings.json` or `.mcp.json` generated in `task.workdir`.

### 2.4 Built-in Worker Runner (`fake/*`, `reference`, `python`)
- **Command Template**:
  ```bash
  python -m skeptic_agent.runner.adapters.command --model {model} --workdir {workdir} --prompt {prompt} --prompt-variant {prompt_variant} --max-steps {max_steps} --timeout-s {timeout_s} --json
  ```
- **Role**: Provides deterministic offline evaluation with `FakeLLM` scripts (`fake/oracle_follower`, etc.) or reference ReAct agent loop against MCP stdio servers without requiring external CLI installations or API keys. Properly closes all MCP client sessions upon termination via `AsyncExitStack`.

## 3. Configuration in `skeptic.yaml`

Custom presets are configured in `skeptic.yaml`:
```yaml
schema: skeptic.config/v1
project: my-project
servers:
  weather:
    transport: stdio
    command: ["python", "-m", "skeptic_agent.sandboxes.sb_weather"]

agents:
  claude:
    cmd: ["claude", "-p", "{prompt}", "--dangerously-skip-permissions"]
  codex:
    cmd: ["codex", "exec", "--prompt", "{prompt}", "--approval-level", "full-auto"]
  gemini:
    cmd: ["gemini", "--prompt", "{prompt}", "--non-interactive"]
  custom_cli:
    cmd: ["my-agent", "--task", "{prompt}", "--mcp-config", "{workdir}/.mcp.json"]
    env:
      AGENT_MODE: "headless"
```

Template variables available for interpolation:
- `{prompt}`: The scenario prompt concatenated with answer format.
- `{workdir}`: Absolute path to the episode scratch working directory.
- `{timeout_s}`: Episode wall-clock timeout in seconds.
- `{model}` / `{preset}`: Configured model or preset name.
- `{episode_id}`: Episode identifier string.
- `{prompt_variant}`: `plain` or `evidence_contract`.
- `{max_steps}`: Scenario turn limit.

If `{prompt}` is omitted from `cmd`, the prompt is written to the child process's standard input (`stdin`).

## 4. Default Prompt & Framework Behaviors (S13.4)

Per S13.4:
- The adapter does not inject scoring prompts, hidden personas, or benchmark cheats into external CLI invocations.
- The prompt passed to the command consists solely of the task prompt (`task.prompt`).
- External frameworks use their native ReAct and decision-making loops.

## 5. Timeout & Process Lifecycle Management

- **Process Supervision**: Subprocesses are spawned asynchronously with standard pipes (`asyncio.create_subprocess_exec`).
- **Timeout Handling**: When wall-clock timeout is exceeded, the process is terminated gracefully via SIGTERM (`proc.terminate()`), followed by SIGKILL if unresponsive after 3 seconds. Per S13.3, `final_answer = ""` with `steps = task.max_steps` is returned, leading to a `NO_ANSWER` outcome without crashing the benchmark harness.
- **Clean MCP Shutdown**: Subprocess stdio pipes are properly closed upon completion. In the built-in worker runner, all MCP client sessions are managed via `contextlib.AsyncExitStack` to ensure clean shutdown.
- **Output Sanitization**: ANSI escape sequences are stripped from CLI output, and structured JSON results are parsed when emitted.
