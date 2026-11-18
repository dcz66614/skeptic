# Skeptic

Chaos-test the tool layer. Catch agents that believe bad data.

Skeptic is a proxy and benchmark for MCP tool calls. It records traffic, injects loud, silent, and adversarial faults, scores what the agent does with the result, and can rewrite tool output through guards.

> **Preview release (0.1.0a1).** Early open-source preview, not v1.0.0, not on PyPI yet (`pip install git+https://github.com/dcz66614/skeptic`). The official S16.2 leaderboard run has not been done, so no official leaderboard results are claimed.

The package name is `skeptic-agent`. The command is `skeptic`.

## Start here

- [Quickstart](quickstart.md) runs one scenario with FakeLLM.
- [Concepts](concepts/faults.md) covers faults, guards, and the Skeptic Score.
- [Guides](guides/claude-code.md) connect Claude Code, Codex, Cursor, LangGraph, and CI.
- [Reference](reference/cli.md) is the CLI, the config file, the schemas, the fault catalogue, and the guards.
- [Methodology](methodology/faults.md) records the catalogue, the realistic profile, and the guard experiment.
- [Leaderboard](leaderboard.md) links to the Agent Skepticism Leaderboard.
- [FAQ](faq.md)
- [Changelog](changelog.md)
