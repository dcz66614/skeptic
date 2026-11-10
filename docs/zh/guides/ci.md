# 持续集成

在 GitHub Actions 里用 FakeLLM 跑 Skeptic，作业就不需要模型密钥。`profile: none` 是干净基线。`smoke` 是 20 个场景的套件（每个沙箱一英一中）。

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

分数低于门槛时，`skeptic gate` 的退出码是 10。希望检查变红时，让作业采用这个退出码。

本仓库的文档工作流（`.github/workflows/docs.yml`）用 `mkdocs build --strict` 构建 MkDocs 站点，检查 `docs/en` 和 `docs/zh` 的相对路径一致，并执行[快速开始](../quickstart.md)里的每一条命令。推送到 `main` 时，它把站点作为 GitHub Pages 产物上传并发布。

报告格式和门禁参数见[命令行参考](../reference/cli.md)。
