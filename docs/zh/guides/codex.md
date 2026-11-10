# Codex

Codex CLI 把 MCP 服务器写在名为 `[mcp_servers.<name>]` 的 TOML 表里。`skeptic init` 同时读取用户文件 `~/.codex/config.toml` 和项目文件 `.codex/config.toml`。Codex 自己只在项目受信任时加载项目文件。init 仍然读取该文件。

一个 stdio 服务器：

```toml
[mcp_servers.weather]
command = "python"
args = ["-m", "skeptic_agent.sandboxes.sb_weather"]
```

HTTP 服务器用 `url`，不用 `command`。可选键是 `env` 和 `http_headers`。

包装项目文件。默认画像是 `silent-core`。原文件会复制为 `.codex/config.toml.skeptic.bak`。

```text
skeptic wrap .codex/config.toml --server weather --profile silent-core
skeptic wrap .codex/config.toml --undo
```

stdio 包装之后，`command` 变成 `skeptic`，`args` 以 `proxy`、`stdio`、`--profile`、画像 id、`--record`、`.skeptic/cassettes`、`--` 开头，后面是原来的命令和参数。

生成的 `skeptic.yaml` 形状见[配置参考](../reference/config.md)。
