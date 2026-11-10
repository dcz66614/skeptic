# Skeptic

Chaos-test the tool layer. Catch agents that believe bad data.

![Demo of skeptic --version, the silent fault list, and an episode count](docs/launch/demo.gif)

Skeptic is an MCP proxy that injects tool faults and scores whether an agent treats a bad result as success.

| Figure | Value | Run |
| --- | --- | --- |
| FSR, no guards | 8.54% (95% CI 3.14% to 15.58%) | `20261103-155316-3e96a4` |
| FSR, all guards | 7.29% (95% CI 1.88% to 14.53%) | `20261103-162358-6c18bb` |
| SKS, no guards | 93.19 (95% CI 89.71 to 96.00), partial | `20261103-155316-3e96a4` |

Model `compat/hy3`, 482 episodes on each of those runs. The two FSR intervals overlap. The matrix profiles set `include_clean` to false, so the runs have no clean episodes, and both SKS values are partial. Full table: [guards-ab.md](docs/en/methodology/guards-ab.md).

## Install

This tree is version 0.0.0. From a checkout:

```bash
uv sync
uv run skeptic --version
```

This repository is the `skeptic-agent` package (import name `skeptic_agent`).
Launch drafts for human review sit in `docs/launch/`.
The project plan is in `docs/plan/`.

The composite GitHub Action is `action.yml`. The FakeLLM workflow is `examples/03-github-action/`.
