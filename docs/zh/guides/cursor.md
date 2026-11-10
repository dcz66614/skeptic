# Cursor

Cursor 把 MCP 服务器放在 `.cursor/mcp.json`（项目）和 `~/.cursor/mcp.json`（用户），键名是 `mcpServers`。发现时，同名的项目级条目覆盖用户级条目。

stdio 使用 `command`、`args` 和 `env`。HTTP 使用 `url` 和可选的 `headers`。Cursor 的 HTTP 条目不需要 `type` 字段。`skeptic init` 仍把它们记成 `transport: http`。

```json
{
  "mcpServers": {
    "weather": {
      "command": "python",
      "args": ["-m", "skeptic_agent.sandboxes.sb_weather"]
    }
  }
}
```

```text
skeptic init --path .
skeptic wrap .cursor/mcp.json --all --profile silent-core
skeptic wrap .cursor/mcp.json --undo
```

`--all` 要求文件存在，并改写其中每个服务器。备份是 `.cursor/mcp.json.skeptic.bak`。stdio 命令会变成 `skeptic`，参数是 `proxy stdio`，与 [Claude Code 指南](claude-code.md) 相同。

`init` 写出的 `skeptic.yaml` 见[配置参考](../reference/config.md)。
