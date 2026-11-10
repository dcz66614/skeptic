# CI

Run Skeptic in GitHub Actions with FakeLLM so the job does not need a model key. `profile: none` is the clean baseline. `smoke` is the twenty-scenario suite (one English and one Chinese scenario per sandbox).

```yaml
name: skeptic
on: [push, pull_request]
jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --locked
      - run: uv run skeptic run --suite smoke --agent reference:fake/oracle_follower --profile none --seeds 1 --max-cost-usd 0.1 --out runs/ci
      - run: uv run skeptic report runs/ci
      - run: uv run skeptic gate runs/ci --min-sks 70
```

`skeptic gate` exits 10 when the score is under the threshold. Point the job at that exit code when a red check is what you want.

This repository's docs workflow (`.github/workflows/docs.yml`) builds the MkDocs site with `mkdocs build --strict`, checks that `docs/en` and `docs/zh` contain the same relative paths, and runs every command in the [quickstart](../quickstart.md). On a push to `main` it uploads the site as a GitHub Pages artifact and deploys it.

The [CLI reference](../reference/cli.md) lists `report` formats and the gate flags.
