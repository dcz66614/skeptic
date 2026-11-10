# 快速开始

大约五分钟。从本仓库的检出开始，项目环境已经装好（`uv sync`）。文档工作流会实际执行下面代码块里的每一条命令。模型是 FakeLLM（`reference:fake/oracle_follower`），运行留在本机，不需要 API 密钥。

```bash
uv run skeptic --version
uv run skeptic faults list
uv run skeptic scenario validate bench/scenarios/weather/weather.forecast.paris-max.001.yaml
uv run skeptic run --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml --agent reference:fake/oracle_follower --profile none --seeds 1 --max-cost-usd 0.1 --out runs/quickstart
uv run skeptic report runs/quickstart
uv run skeptic gate runs/quickstart --min-sks 70
```

`skeptic --version` 打印包版本。`faults list` 打印 20 个故障 id。`scenario validate` 按 Schema 和语义规则检查一个天气场景。`skeptic run` 在干净的 `none` 画像下把这个场景跑一遍，结果写到 `runs/quickstart`（已被 git 忽略）。`skeptic report` 把报告文件写进同一目录。`skeptic gate --min-sks 70` 在 Skeptic Score 不低于 70 时退出码为 0，低于 70 时退出码为 10。

真实模型的智能体规格形如 `reference:openrouter/<厂商>/<模型>`，并设置 `OPENROUTER_API_KEY`。全部命令见[命令行参考](reference/cli.md)。把代理放到客户端前面的步骤见 [Claude Code 指南](guides/claude-code.md)。
