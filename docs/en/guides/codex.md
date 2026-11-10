# Codex

Codex CLI stores MCP servers in TOML tables named `[mcp_servers.<name>]`. `skeptic init` reads both the user file `~/.codex/config.toml` and the project file `.codex/config.toml`. Codex itself loads the project file when that project is trusted. Init still reads the file.

A stdio server:

```toml
[mcp_servers.weather]
command = "python"
args = ["-m", "skeptic_agent.sandboxes.sb_weather"]
```

An HTTP server uses `url` instead of `command`. Optional keys are `env` and `http_headers`.

Wrap the project file. The default profile is `silent-core`. The original file is copied to `.codex/config.toml.skeptic.bak`.

```text
skeptic wrap .codex/config.toml --server weather --profile silent-core
skeptic wrap .codex/config.toml --undo
```

After a stdio wrap, `command` is `skeptic` and `args` starts with `proxy`, `stdio`, `--profile`, the profile id, `--record`, `.skeptic/cassettes`, `--`, then the original command and arguments.

The generated `skeptic.yaml` shape is in the [configuration reference](../reference/config.md).
