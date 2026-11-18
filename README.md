# Skeptic

Chaos-test the tool layer. Catch agents that believe bad data.

> **Preview release (0.1.0a1).** This is an early open-source preview, not v1.0.0. It is not on PyPI yet; install from GitHub with `pip install git+https://github.com/dcz66614/skeptic`. The official S16.2 leaderboard run has not been done, so no official leaderboard results are claimed here; the numbers below come from a single model (`compat/hy3`) and are partial. Feedback is welcome through [issues](https://github.com/dcz66614/skeptic/issues).

![Demo of skeptic --version, the silent fault list, and an episode count](docs/launch/demo.gif)

Skeptic is an MCP proxy that injects tool faults and scores whether an agent treats a bad result as success.

| Figure | Value | Run |
| --- | --- | --- |
| FSR, no guards | 8.54% (95% CI 3.14% to 15.58%) | `20261103-155316-3e96a4` |
| FSR, all guards | 7.29% (95% CI 1.88% to 14.53%) | `20261103-162358-6c18bb` |
| SKS, no guards | 93.19 (95% CI 89.71 to 96.00), partial | `20261103-155316-3e96a4` |

Model `compat/hy3`, 482 episodes on each of those runs. The two FSR intervals overlap. The matrix profiles set `include_clean` to false, so the runs have no clean episodes, and both SKS values are partial. Full table: [guards-ab.md](docs/en/methodology/guards-ab.md).

## Install

This tree is version 0.1.0a1 (preview). It is not on PyPI. From a checkout:

```bash
uv sync
uv run skeptic --version
```

Or install straight from GitHub:

```bash
pip install git+https://github.com/dcz66614/skeptic
```

This repository is the `skeptic-agent` package (import name `skeptic_agent`).
Launch drafts for human review sit in `docs/launch/`.
The project plan is in `docs/plan/`.

The composite GitHub Action is `action.yml`. The FakeLLM workflow is `examples/03-github-action/`.
