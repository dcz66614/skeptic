# GitHub Action example

This example runs the composite action in `action.yml` with FakeLLM. No API key is required.

The workflow file is `workflow.yml`. CI runs the same bytes from `.github/workflows/example-github-action.yml`.

## Jobs

`pass` calls the action with `reference:fake/oracle_follower`, the `smoke` suite, and profile `none`. The gate is `min-sks: 70`. The job is green when the action exits 0, and it checks that `sks`, `fsr`, and `report-path` are set.

`gate-fail` is the same run with `min-sks: 101`. SKS is on a 0–100 scale, so `skeptic gate` exits 10. That step's outcome is `failure`. The job then exits 1 so the check is red. `continue-on-error` on the job keeps the workflow green when this expected failure happens.

`gate-fail-was-red` fails the workflow if the action did not fail.

## Call the action

```yaml
- uses: actions/checkout@v4
- uses: <ORG>/skeptic@<ref>
  with:
    agent: reference:fake/oracle_follower
    suite: smoke
    profile: silent-core
    min-sks: "70"
    max-cost-usd: "5"
```

From this repository, `uses: ./` after `actions/checkout` is the local action.

The action's default profile is `silent-core`. This example sets `none` so the FakeLLM reference agent runs the 20 clean smoke episodes and clears a SKS of 70. A silent-core run is 158 episodes.

`config` is an optional path to `skeptic.yaml`. The action copies it into the action tree for `skeptic run` and deletes the copy when the run step ends. The `min-sks` input is what `skeptic gate` uses.

The install step is `uv sync --locked` on the action directory. The caller pins the version by pinning `uses:` to a ref. The bench files the CLI loads sit next to the source and are not inside the wheel.

## Local Execution (`run.py`)

You can simulate and verify the exact GitHub Action workflow locally using `run.py` without pushing to GitHub or needing runner infrastructure:

```bash
# Run local workflow simulation with FakeLLM
uv run python examples/03-github-action/run.py

# Or run against the full 20-episode smoke suite
uv run python examples/03-github-action/run.py --smoke
```

The script runs the complete sequence:
1. `skeptic run` with FakeLLM (`reference:fake/oracle_follower`, profile `none`).
2. `skeptic report` generating Markdown and HTML summaries.
3. Output assertions (`sks`, `fsr`, `report-path`).
4. Passing gate check (`--min-sks 70` returning exit code 0).
5. Failing gate check (`--min-sks 101` returning exit code 10, confirming expected red check behavior).

## 示例说明

`pass` 用 FakeLLM 跑 smoke 套件，画像 `none`，门禁 70，应当通过。`gate-fail` 把 `min-sks` 设为 101，`skeptic gate` 以退出码 10 失败，该 job 显示为红，并且不把整个工作流打红。动作的默认画像仍是 `silent-core`。本地可直接通过 `uv run python examples/03-github-action/run.py` 执行完整的动作步骤模拟与门禁验证。
