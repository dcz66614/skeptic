# GitHub Action

`action.yml` at the repository root is a composite action (K57, S1).

## Inputs

| Input | Default | Passed to |
|---|---|---|
| `config` | empty | copied to the action tree as `skeptic.yaml` for the duration of `skeptic run` |
| `suite` | `smoke` | `skeptic run --suite` |
| `agent` | required | `skeptic run --agent` |
| `profile` | `silent-core` | `skeptic run --profile` |
| `guards` | empty (CLI default `none`) | `skeptic run --guards` when non-empty |
| `min-sks` | `70` | `skeptic gate --min-sks` |
| `max-cost-usd` | `5` | `skeptic run --max-cost-usd` |
| `upload-report` | `true` | upload `${{ runner.temp }}/skeptic-run` as artifact `skeptic-report` |

## Outputs

`sks` and `fsr` are the first agent's estimates in `summary.json`. `report-path` is the run directory. The same directory's `report.md` is appended to `$GITHUB_STEP_SUMMARY`.

## Steps

setup-uv (`astral-sh/setup-uv@v6`, Python 3.12) → `uv sync --locked` on the action tree → `skeptic run` → `skeptic report` → upload the artifact when `upload-report` is `true` → write `report.md` to the job summary → `skeptic gate`.

`skeptic gate` exits 10 when the threshold is missed (S2). The action does not catch that exit, so the step fails.

The install is the tree selected by `uses: <org>/skeptic@<ref>`, locked by `uv.lock`. It is not `pip install skeptic-agent` without a pin. Suite files live in `bench/` next to the source (ADR-0001) and are not shipped in the wheel, so the action runs the checkout it was pinned to.

FakeLLM (`reference:fake/oracle_follower`) does not need `OPENROUTER_API_KEY`. The CI example is `examples/03-github-action/`.

## 中文

仓库根目录的 `action.yml` 是 composite 动作。输入、默认值和输出与上表一致。步骤依次是安装固定的 `uv.lock` 树、`skeptic run`、`skeptic report`、按需上传 artifact、把 `report.md` 写入作业摘要、`skeptic gate`。门禁不通过时退出码为 10，该步骤失败。`config` 没有对应的 CLI 参数，动作在 run 期间把文件复制到动作目录的 `skeptic.yaml`，结束时删掉副本。`min-sks` 输入优先于配置文件里的门禁，因为动作总是把它传给 `skeptic gate`。
