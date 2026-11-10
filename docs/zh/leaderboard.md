# 榜单

智能体较真榜（Agent Skepticism Leaderboard）按 Skeptic Score 给智能体配置排名。SKS 置信区间重叠的配置记成同一个名次组。

页面发布在 <https://skeptic-agent.github.io/skeptic/leaderboard/>。

一次榜单运行是一份 `skeptic.matrix/v1` 文件，按画像和种子展开。这次运行使用的模型清单在 `bench/leaderboard/models.yaml`（`skeptic.models/v1`）。SKS 的算法在[指标](concepts/metrics.md)页。
