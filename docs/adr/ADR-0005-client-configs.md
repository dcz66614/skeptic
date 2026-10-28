# ADR-0005: 客户端配置的发现与改写

- 状态：采纳
- 日期：2026-10-28
- 提出者：T02　裁决者：R1

## 背景

`skeptic init` 和 `skeptic wrap` 按 S15 发现本机 MCP 客户端配置，再把选中的服务器改成经 `skeptic proxy` 转发。S15 写明各客户端格式可能已经更新，实现前对照官方文档，不一致就记在本 ADR，以文档为准（D4）。2026-10-28 核对了下面这些页面：Claude Desktop 的本地服务器说明（modelcontextprotocol.io 的 connect-local-servers）、Cursor 文档（cursor.com/docs/mcp 与 cursor.com/help/customization/mcp）、VS Code 的 MCP configuration reference（code.visualstudio.com/docs/agents/reference/mcp-configuration）、Codex 的 config basics（developers.openai.com/codex/config-basic）以及 2026-10 的 Codex MCP 配置说明、Gemini CLI 的 MCP 设置说明（geminicli.com 的 settings.json 教程）。

S15 的路径和“stdio 用 command/args、HTTP 用 url”这个大意仍然对。不一致的是 HTTP 条目的字段名，以及 Codex 多了一个项目级文件。

## 选项（至少 2 个，各写优缺点）

### A. 只接受 S15 表里的那一种形状

优点：发现逻辑是一张表，和计划书逐字相同。
缺点：Cursor 的 HTTP 条目没有 `type`。VS Code 的 stdio 条目要求 `type: "stdio"`。Codex 的 HTTP 用 `url`，Gemini 的有些说明用 `httpUrl`。按字面形状会漏掉这些服务器。

### B. 路径以 S15 为底，每个客户端再接受它当前文档里的条目形状

优点：发现结果和用户机器上的文件一致。写入 `skeptic.yaml` 时仍然只有 `transport: stdio|http` 这一套（S3）。
缺点：发现代码要按客户端分几支，而不是共用一个 JSON 解码。

## 决定

采纳 B。`skeptic init` 按下列顺序读文件。同一个服务器名后出现的项目级文件覆盖用户级文件。读不到的路径跳过。

| 客户端 | 路径 | 接受的条目 |
|---|---|---|
| 项目级通用 | `./.mcp.json` | 顶层 `mcpServers`。stdio：`command`、`args`、`env`。HTTP：`url` 加可选 `headers`，`type` 可有可无；`type` 为 `http` 或 `sse` 时同样认作 HTTP |
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`；Windows `%APPDATA%\Claude\claude_desktop_config.json` | 顶层 `mcpServers`，stdio 为 `command`、`args`、`env`。若条目自带 `url`，认作 HTTP |
| Cursor | `./.cursor/mcp.json`、`~/.cursor/mcp.json` | 顶层 `mcpServers`。stdio 为 `command`、`args`、`env`。HTTP 为 `url` 加可选 `headers`，不要求 `type` |
| VS Code | `./.vscode/mcp.json` | 顶层 `servers`。stdio 的 `type` 为 `stdio`，并有 `command`。HTTP 的 `type` 为 `http` 或 `sse`，并有 `url` 与可选 `headers`。`sse` 在 `skeptic.yaml` 里记为 `transport: http` |
| Codex CLI | `~/.codex/config.toml`，以及项目内 `.codex/config.toml`（仅当该项目被 Codex 信任时才由 Codex 自己加载；init 仍读取文件） | 表 `[mcp_servers.<name>]`。stdio 为 `command` 和 `args`。HTTP 为 `url`。可选 `env`、`http_headers` |
| Gemini CLI | `./.gemini/settings.json`、`~/.gemini/settings.json` | 顶层 `mcpServers`。stdio 为 `command`、`args`、`env`。HTTP 的 URL 字段是 `url` 或 `httpUrl` |

环境变量插值保持原样复制，不把 `${env:NAME}` 翻译成 `${NAME}`。`skeptic.yaml` 自己的 `${VAR}` 展开规则仍按 S3，只作用于已经写进 `skeptic.yaml` 的值。

改写规则按 S15，不改：

- stdio `{command: C, args: A}` 改为 `{command: "skeptic", args: ["proxy","stdio","--profile",P] + (有 guards 时加 ["--guards", G]) + ["--record",".skeptic/cassettes","--", C] + A}`。
- HTTP 改为本地 `skeptic proxy http` 的地址，并在 `skeptic.yaml` 里记下上游启动方式。
- 改写前把原文件备份为 `FILE.skeptic.bak`。`--undo` 从备份逐字恢复。

发现结果映射进 S3：有 `command` 的记 `transport: stdio` 和 `command`（`command` 与 `args` 合成一个字符串数组）、`env`；有 URL 的记 `transport: http`、`url`、`headers`。

## 影响（需要修改的规格条目、代码、文档）

- S15 的发现表补上：Cursor HTTP 不要求 `type`；VS Code `servers` 里的 `type`；VS Code 与通用文件里的 `sse` 映射为 `http`；Codex 的项目级 `config.toml` 和 HTTP `url`；Gemini 的 `httpUrl`。
- `skeptic init` / `skeptic wrap`（后续任务）按本表实现。`skeptic.yaml` 的 Schema 仍然只有 `stdio` 和 `http`。
