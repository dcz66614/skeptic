# 配置

`skeptic init` 在发现至少一个 MCP 服务器时写出 `skeptic.yaml`。文档 id 是 `skeptic.config/v1`。Schema 文件是 `schemas/config.schema.json`。

```yaml
schema: skeptic.config/v1
project: my-agent
servers:
  weather:
    transport: stdio
    command: ["python", "-m", "skeptic_agent.sandboxes.sb_weather"]
    env: {}
  crm:
    transport: http
    url: "https://crm.example.com/mcp"
    headers: {Authorization: "Bearer ${CRM_TOKEN}"}
profile: silent-core
guards: []
record:
  dir: .skeptic/cassettes
  redact_keys: ["authorization", "cookie", "api_key", "token", "secret", "password"]
gate:
  min_sks: 70
  max_fsr: 0.10
  max_icr: 0.00
budget:
  max_cost_usd_per_run: 5
judge:
  enabled: false
  model: null
```

`project` 必填。`servers` 至少一条。`transport` 是 `stdio` 或 `http`。`guards` 是防护名列表，或预设字符串：`none`、`all`、`recommended`。服务器条目里的字符串可以含有 `${VAR}` 占位符；init 按客户端文件里的原样复制这些占位符。

录制卡带时，`Authorization` 和 `Cookie` 头，以及键名匹配 `api_key`、`token`、`secret` 或 `password` 的值，都会换成 `"***"`。

## init 查找的位置

同一个服务器名，后出现的项目级文件覆盖用户级文件。读不到的路径会跳过。

| 客户端 | 路径 | 条目形状 |
|---|---|---|
| 项目级通用 | `./.mcp.json` | `mcpServers`。stdio：`command`、`args`、`env`。HTTP：`url`，可选 `headers`。`type` 可以没有。`http` 和 `sse` 都记成 `transport: http`。 |
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`；Windows `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers`，stdio 键相同。带 `url` 的条目是 HTTP。 |
| Cursor | `./.cursor/mcp.json`、`~/.cursor/mcp.json` | `mcpServers`。HTTP 是 `url` 加可选 `headers`，不要求 `type`。 |
| VS Code | `./.vscode/mcp.json` | `servers`。stdio 需要 `type: stdio` 和 `command`。HTTP 需要 `type: http` 或 `type: sse`，以及 `url`。 |
| Codex CLI | `~/.codex/config.toml`、`./.codex/config.toml` | `[mcp_servers.<name>]`。stdio：`command`、`args`。HTTP：`url`。可选 `env`、`http_headers`。 |
| Gemini CLI | `./.gemini/settings.json`、`~/.gemini/settings.json` | `mcpServers`。HTTP 的 URL 字段是 `url` 或 `httpUrl`。 |

`skeptic wrap` 改的是客户端文件，不是 `skeptic.yaml`。HTTP 包装会把上游 URL 记进 `skeptic.yaml`。见 [Claude Code](../guides/claude-code.md)、[Codex](../guides/codex.md) 和 [Cursor](../guides/cursor.md) 指南。
