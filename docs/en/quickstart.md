# Quickstart

About five minutes, from a checkout of this repository with the project environment already installed (`uv sync`). The docs workflow runs the commands in the block below. The model is FakeLLM (`reference:fake/oracle_follower`), so the run stays on this machine and does not need an API key.

```bash
uv run skeptic --version
uv run skeptic faults list
uv run skeptic scenario validate bench/scenarios/weather/weather.forecast.paris-max.001.yaml
uv run skeptic run --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml --agent reference:fake/oracle_follower --profile none --seeds 1 --max-cost-usd 0.1 --out runs/quickstart
uv run skeptic report runs/quickstart
uv run skeptic gate runs/quickstart --min-sks 70
```

`skeptic --version` prints the package version. `faults list` prints the twenty fault ids. `scenario validate` checks one weather scenario against the schema and the semantic rules. `skeptic run` plays that scenario once under the clean `none` profile and writes `runs/quickstart` (gitignored). `skeptic report` writes the report files into that same directory. `skeptic gate --min-sks 70` exits 0 when the Skeptic Score is at least 70, and exits 10 when the score is lower.

A live model uses an agent spec such as `reference:openrouter/<vendor>/<model>` plus `OPENROUTER_API_KEY`. The [CLI reference](reference/cli.md) lists every command. The [Claude Code guide](guides/claude-code.md) shows how to put the proxy in front of a client.
