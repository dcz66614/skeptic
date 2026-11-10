# Skeptic（较真）

对工具层做混沌测试，抓住相信坏数据的智能体。

![演示：版本号、静默故障列表、回合计数](docs/launch/demo.gif)

Skeptic 是一个 MCP 代理。它给工具调用注入故障，并记录智能体是否把坏结果当成成功。

| 数字 | 取值 | run_id |
| --- | --- | --- |
| 无防护时的谎报成功率 FSR | 8.54%（95% 区间 3.14% 到 15.58%） | `20261103-155316-3e96a4` |
| 八个防护全开时的 FSR | 7.29%（95% 区间 1.88% 到 14.53%） | `20261103-162358-6c18bb` |
| 无防护时的较真分 SKS | 93.19（95% 区间 89.71 到 96.00），partial | `20261103-155316-3e96a4` |

模型是 `compat/hy3`，上面两行各 482 个回合。两个 FSR 区间重叠。矩阵用的故障画像把 `include_clean` 设为 false，这批回合里没有无故障回合，两份 SKS 都是 partial。整张表在 [guards-ab.md](docs/en/methodology/guards-ab.md)。

## 安装

这个仓库的版本是 0.0.0。在检出目录里：

```bash
uv sync
uv run skeptic --version
```

本仓库是 `skeptic-agent` 包（导入名 `skeptic_agent`）。
给人类审的宣发稿在 `docs/launch/`。
项目计划见 `docs/plan/`。

Composite GitHub Action 在仓库根目录的 `action.yml`。FakeLLM 示例工作流在 `examples/03-github-action/`。
