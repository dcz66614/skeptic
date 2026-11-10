# Claude Code

Claude Code 从项目根目录的 `.mcp.json` 读取 MCP 服务器，键名是 `mcpServers`。`skeptic init` 会发现这个文件。`skeptic wrap` 把选中的服务器改成经 `skeptic proxy stdio` 启动。

包装前的天气沙箱条目：

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

先发现，再用 `silent-core` 画像包装这一个服务器。包装前会写入 `.mcp.json.skeptic.bak`。

```text
skeptic init --path . --dry-run
skeptic wrap .mcp.json --server weather --profile silent-core
```

包装后的条目：

```json
{
  "mcpServers": {
    "weather": {
      "command": "skeptic",
      "args": [
        "proxy", "stdio", "--profile", "silent-core",
        "--record", ".skeptic/cassettes", "--",
        "python", "-m", "skeptic_agent.sandboxes.sb_weather"
      ]
    }
  }
}
```

`--guards recommended` 会在 `--record` 之前插入 `--guards recommended`。`--all` 包装文件里的每个服务器。从备份逐字节恢复：

```text
skeptic wrap .mcp.json --undo
```

Claude Desktop 是另一个文件：Windows 上是 `%APPDATA%\Claude\claude_desktop_config.json`，macOS 上是 `~/Library/Application Support/Claude/claude_desktop_config.json`。`skeptic init` 也会读它。同一条 `wrap` 命令适用。字段名见[配置参考](../reference/config.md)。

Codex 和 Cursor 用各自的路径。见 [Codex](codex.md) 和 [Cursor](cursor.md) 指南。
