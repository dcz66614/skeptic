# Cursor

Cursor stores MCP servers in `.cursor/mcp.json` (project) and `~/.cursor/mcp.json` (user), under `mcpServers`. A later project entry with the same name replaces the user entry during discovery.

Stdio uses `command`, `args`, and `env`. HTTP uses `url` and optional `headers`. Cursor HTTP entries do not need a `type` field. `skeptic init` still records them as `transport: http`.

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

`--all` requires the file to exist and rewrites every server. The backup is `.cursor/mcp.json.skeptic.bak`. The stdio command becomes `skeptic` with `proxy stdio` arguments, as in the [Claude Code guide](claude-code.md).

The `skeptic.yaml` that `init` writes is described in the [configuration reference](../reference/config.md).
