# Configuration

`skeptic init` writes `skeptic.yaml` when it finds at least one MCP server. The document id is `skeptic.config/v1`. Schema file: `schemas/config.schema.json`.

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

`project` is required. `servers` needs at least one entry. `transport` is `stdio` or `http`. `guards` is a list of guard names or a preset string: `none`, `all`, or `recommended`. Strings inside server entries may contain `${VAR}` placeholders; init copies client placeholders through as they appear in the client file.

Cassette recording redacts `Authorization` and `Cookie` headers, and any key whose name matches `api_key`, `token`, `secret`, or `password`, replacing the value with `"***"`.

## Where init looks

The same server name in a later project file replaces a user-level entry. Missing paths are skipped.

| Client | Path | Entry shape |
|---|---|---|
| Project | `./.mcp.json` | `mcpServers`. Stdio: `command`, `args`, `env`. HTTP: `url`, optional `headers`. `type` may be omitted. `http` and `sse` both become `transport: http`. |
| Claude Desktop | macOS `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers`, same stdio keys. An entry with `url` is HTTP. |
| Cursor | `./.cursor/mcp.json`, `~/.cursor/mcp.json` | `mcpServers`. HTTP is `url` plus optional `headers`, with no required `type`. |
| VS Code | `./.vscode/mcp.json` | `servers`. Stdio needs `type: stdio` and `command`. HTTP needs `type: http` or `type: sse`, plus `url`. |
| Codex CLI | `~/.codex/config.toml`, `./.codex/config.toml` | `[mcp_servers.<name>]`. Stdio: `command`, `args`. HTTP: `url`. Optional `env`, `http_headers`. |
| Gemini CLI | `./.gemini/settings.json`, `~/.gemini/settings.json` | `mcpServers`. HTTP URL field is `url` or `httpUrl`. |

`skeptic wrap` edits the client file, not `skeptic.yaml`, except that an HTTP wrap records the upstream URL in `skeptic.yaml`. See the [Claude Code](../guides/claude-code.md), [Codex](../guides/codex.md), and [Cursor](../guides/cursor.md) guides.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SKEPTIC_TMP` | `<system temp dir>/skeptic` | Scratch root for per-episode work directories (`ep_*`) and oracle scratch files. It never defaults to the project checkout, so a run does not fill the repository with temporary directories. The directory is created on first use. |
