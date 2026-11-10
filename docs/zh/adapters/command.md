# 通用命令行适配器（`command`，beta）

> **状态：Beta**
> `command` 适配器处于 beta。它把 Skeptic 接到外部命令行智能体和无界面 CLI。

本文记录通用命令行适配器（`command`）的配置、版本、默认提示词、预设命令和超时，对应 S13.1、S13.2、S13.4 和 E45。

## 1. 概述

- **适配器 id**：`command`（`command:<预设>`）
- **状态**：Beta
- **规格**：S13.1、S13.2、S13.4、E45
- **作用**：把任务交给外部命令行智能体、无界面 CLI 或脚本包装。
- **接入结构**：
  - 配置生成：执行命令前，在回合工作目录（`task.workdir`）写好标准 MCP 配置：
    - `.mcp.json`（项目级，Claude Code、Cursor）
    - `.cursor/mcp.json`（Cursor IDE）
    - `.codex/config.toml`（Codex CLI）
    - `.gemini/settings.json`（Gemini CLI）
  - 进程：用 `asyncio.create_subprocess_exec` 异步启动，标准输入输出走管道。
  - 监督：跟踪超时，排空并清理 stdout/stderr（去掉 ANSI 转义），结束或出错时关掉子进程和 stdio 会话。

## 2. 预设与无界面命令

内置预设可以在 `skeptic.yaml` 的 `agents.<预设>.cmd` 里覆盖或扩展。

### 2.1 Claude Code（`claude`）

- **CLI 包**：`@anthropic-ai/claude-code`（npm）
- **命令模板**：

```bash
claude -p "{prompt}" --dangerously-skip-permissions
```

- **无界面**：`-p`（或 `--print`）以打印模式运行，输出到 stdout，结束后退出。`--dangerously-skip-permissions` 在自动评测里跳过交互式批准。
- **MCP 配置**：读取 `task.workdir` 里生成的 `./.mcp.json`。

### 2.2 Codex CLI（`codex`）

- **CLI 包**：`@openai/codex` / `codex-cli`
- **命令模板**：

```bash
codex exec --prompt "{prompt}" --approval-level full-auto
```

- **无界面**：`codex exec` 不打开 TUI，`--approval-level full-auto` 用于自动执行工具。
- **MCP 配置**：读取 `task.workdir` 里生成的 `.codex/config.toml`。

### 2.3 Gemini CLI（`gemini`）

- **CLI 包**：`@google/gemini-cli`
- **命令模板**：

```bash
gemini --prompt "{prompt}" --non-interactive
```

- **无界面**：`--non-interactive` 不等人操作，把完成结果写到 stdout。
- **MCP 配置**：读取 `task.workdir` 里生成的 `.gemini/settings.json` 或 `.mcp.json`。

### 2.4 内置 worker（`fake/*`、`reference`、`python`）

- **命令模板**：

```bash
python -m skeptic_agent.runner.adapters.command --model {model} --workdir {workdir} --prompt {prompt} --prompt-variant {prompt_variant} --max-steps {max_steps} --timeout-s {timeout_s} --json
```

- **作用**：用 FakeLLM 脚本（`fake/oracle_follower` 等）或参考 ReAct 循环做离线评测，不需要外部 CLI 或 API 密钥。结束时用 `AsyncExitStack` 关掉 MCP 客户端会话。

## 3. `skeptic.yaml` 里的配置

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

可替换的模板变量：

- `{prompt}`：场景 prompt 接上答案格式。
- `{workdir}`：回合临时工作目录的绝对路径。
- `{timeout_s}`：回合墙钟超时，单位秒。
- `{model}` / `{preset}`：配置的模型或预设名。
- `{episode_id}`：回合 id。
- `{prompt_variant}`：`plain` 或 `evidence_contract`。
- `{max_steps}`：场景的回合上限。

`cmd` 里没有 `{prompt}` 时，prompt 写到子进程的标准输入。

## 4. 默认提示词与框架行为（S13.4）

适配器不往外部 CLI 调用里注入评分提示词、隐藏人设或评测作弊。传给命令的 prompt 就是任务 prompt（`task.prompt`）。外部框架用自己的 ReAct 和决策循环。

## 5. 超时与进程生命周期

- **进程监督**：`asyncio.create_subprocess_exec`，标准管道。
- **超时**：墙钟超时后 `proc.terminate()`（SIGTERM），3 秒仍无响应再 SIGKILL。按 S13.3，返回空的 `final_answer`，`steps = task.max_steps`，结局为 `NO_ANSWER`。
- **MCP 关闭**：结束时关掉子进程管道。内置 worker 用 `contextlib.AsyncExitStack` 管理 MCP 客户端会话。
- **输出清理**：去掉 ANSI 转义；如果输出是结构化 JSON，就解析它。
