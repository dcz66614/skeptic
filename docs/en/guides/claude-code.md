# Claude Code

Claude Code reads project MCP servers from `.mcp.json` at the project root, under `mcpServers`. `skeptic init` discovers that file. `skeptic wrap` rewrites a server so its stdio process is `skeptic proxy stdio`.

A weather sandbox entry before wrapping:

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

Discover, then wrap that one server with the `silent-core` profile. Wrapping writes `.mcp.json.skeptic.bak` first.

```text
skeptic init --path . --dry-run
skeptic wrap .mcp.json --server weather --profile silent-core
```

The wrapped entry:

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

`--guards recommended` inserts `--guards recommended` before `--record`. `--all` wraps every server in the file. Restore the backup byte for byte:

```text
skeptic wrap .mcp.json --undo
```

Claude Desktop is a different file: `%APPDATA%\Claude\claude_desktop_config.json` on Windows, and `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS. `skeptic init` reads it too. The same `wrap` command applies. The field names are in the [configuration reference](../reference/config.md).

Codex and Cursor use their own paths. See the [Codex](codex.md) and [Cursor](cursor.md) guides.
