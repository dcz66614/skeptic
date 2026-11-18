# 榜单

智能体较真榜（Agent Skepticism Leaderboard）按 Skeptic Score 给智能体配置排名。SKS 置信区间重叠的配置记成同一个名次组。

榜单页面尚未发布。官方 S16.2 榜单评测尚未进行，因此这个预览版不宣称任何官方榜单结果。生成器是 `site/build.py`。

一次榜单运行是一份 `skeptic.matrix/v1` 文件，按画像和种子展开。这次运行使用的模型清单在 `bench/leaderboard/models.yaml`（`skeptic.models/v1`）。SKS 的算法在[指标](concepts/metrics.md)页。
