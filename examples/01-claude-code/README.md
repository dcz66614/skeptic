# Claude Code MCP Configuration Wrap Example

This example demonstrates how **Skeptic** intercepts and hardens tool calls for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code) through transparent configuration rewriting (`skeptic wrap`).

---

## 1. Background

Claude Code discovers Model Context Protocol (MCP) servers from the project-level configuration file **`.mcp.json`** (per S15 and ADR-0005).

When an agent invokes tools, standard execution directly spawns the upstream server process. If an external service returns corrupted data, stale values, schema violations, or HTTP 503 errors, the agent may hallucinate, crash, or take erroneous destructive actions.

With `skeptic wrap`, tool invocations are rerouted through `skeptic proxy stdio`. The proxy:
1. Injects scheduled chaos faults (silent corruption, loud errors, adversarial inputs).
2. Enforces reliability guards (evidence contract, loop breaker, schema validation, idempotent retries).
3. Records full interaction cassettes to `.skeptic/cassettes/` for deterministic replay.
4. Requires **zero changes** to Claude Code, prompt templates, or upstream tool code.

---

## 2. Configuration Comparison (Before vs. After)

### Before Wrap (`.mcp.json.before`)

Standard Claude Code configuration launching upstream MCP servers directly:

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": [
        "-m",
        "skeptic_agent.sandboxes.sb_weather"
      ]
    },
    "files": {
      "command": "python",
      "args": [
        "-m",
        "skeptic_agent.sandboxes.sb_files"
      ]
    }
  }
}
```

### After Wrap (`.mcp.json.after`)

Rewritten configuration routing each server through Skeptic's stdio proxy:

```json
{
  "mcpServers": {
    "weather": {
      "command": "skeptic",
      "args": [
        "proxy",
        "stdio",
        "--profile",
        "silent-core",
        "--guards",
        "recommended",
        "--record",
        ".skeptic/cassettes",
        "--",
        "python",
        "-m",
        "skeptic_agent.sandboxes.sb_weather"
      ]
    },
    "files": {
      "command": "skeptic",
      "args": [
        "proxy",
        "stdio",
        "--profile",
        "silent-core",
        "--guards",
        "recommended",
        "--record",
        ".skeptic/cassettes",
        "--",
        "python",
        "-m",
        "skeptic_agent.sandboxes.sb_files"
      ]
    }
  }
}
```

### Explanation of Injected Arguments

| Argument | Description |
|---|---|
| `proxy stdio` | Launches Skeptic's bidirectional stdio interception proxy (S4.1). |
| `--profile silent-core` | Applies the fault profile (e.g. `silent-core` for data corruption, `none` for clean baseline). |
| `--guards recommended` | Activates the recommended set of reliability guards (evidence contract, loop breaker, schema guard, etc.). |
| `--record .skeptic/cassettes` | Records all JSON-RPC request/response messages with automatic secret redaction. |
| `--` | Positional delimiter separating Skeptic proxy flags from the upstream command. |
| `python -m ...` | The original upstream MCP server command and arguments, invoked as a child process. |

---

## 3. Running the Example Script

The included runnable script `run.py` executes the entire cycle:
1. Resets `.mcp.json` to the initial unwrapped state.
2. Invokes `skeptic wrap .mcp.json --all --profile silent-core --guards recommended`.
3. Displays the configuration diff and validates against `.mcp.json.after`.
4. Sends an MCP `initialize` JSON-RPC handshake through the wrapped proxy.
5. Invokes `skeptic wrap .mcp.json --undo` and verifies byte-for-byte exact restoration.

```bash
# Run the full automated demonstration
uv run python examples/01-claude-code/run.py

# Or inspect individual stages:
uv run python examples/01-claude-code/run.py --wrap
uv run python examples/01-claude-code/run.py --diff
uv run python examples/01-claude-code/run.py --test-proxy
uv run python examples/01-claude-code/run.py --undo
```

---

## 4. Manual CLI Usage

You can wrap and unwrap configurations directly via the Skeptic CLI:

```bash
# 1. Wrap all servers in .mcp.json
skeptic wrap .mcp.json --all --profile silent-core --guards recommended

# 2. Or wrap only a specific server
skeptic wrap .mcp.json --server weather --profile adversarial-core

# 3. Restore the original file byte-for-byte from .mcp.json.skeptic.bak
skeptic wrap .mcp.json --undo
```

---

## 5. 示例说明

本示例展示了如何针对 Claude Code 的项目级 MCP 配置文件（`.mcp.json`）执行透明代理改写（`skeptic wrap`）：

1. **改写前**：直接运行 `python -m skeptic_agent.sandboxes.*`。
2. **改写后**：命令被重定向至 `skeptic proxy stdio`，无缝注入故障画像（如 `silent-core`）并开启防护守卫（如 `recommended`），交互记录自动落盘至 `.skeptic/cassettes`。
3. **完全无侵入**：不改变 Claude Code 的调用逻辑，不修改上游服务源码。
4. **逐字节恢复**：改写前自动生成 `.mcp.json.skeptic.bak` 备份文件，执行 `skeptic wrap --undo` 后原文件逐字节精准还原。
