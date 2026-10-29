# `realistic-2026` 画像：权重是怎么定的

`realistic-2026` 是我们认为最接近 2026 年生产环境智能体所遇故障组合的画像，因此用它跑出来的结果回答的是“这个智能体在常见故障分布下表现如何”，而不是“它能不能扛住某一种特定故障”。本页记录权重、依据，以及以后如何用真实事故数据替换这些估计。各故障的定义见 `faults.md`。

## 这个画像做什么

文件在 `src/skeptic_agent/data/profiles/realistic-2026.yaml`，是 `sampled` 画像（S7.2）：对每个场景和每个种子，用同一个种子为“运行种子 + 场景 id + 画像 id”的随机数生成器，按权重有放回地抽 3 次（S7.4）。每条故障都用 `persistence: mixed`、`permanent_p: 0.6`，所以一个回合看到的要么是永久故障，要么只发生一次。

```text
每个种子的回合数 = 各场景 samples_per_scenario（= 3）之和
```

`include_clean` 为 false：无故障基线交给 `none` 画像负责，基准集的可恢复性工作（S39）每个场景只跑一次基线，不必在 sampled 画像里跑三次。

## 权重

| 故障 | 内容 | 权重 | 类别 |
|---|---|---|---|
| L01 | timeout | 0.10 | 显式 |
| L02 | jsonrpc_error | 0.05 | 显式 |
| L03 | tool_error | 0.10 | 显式 |
| L05 | rate_limited | 0.08 | 显式 |
| L06 | tool_missing | 0.04 | 显式 |
| L07 | schema_drift | 0.05 | 显式 |
| S01 | empty_ok | 0.08 | 静默 |
| S02 | truncated | 0.08 | 静默 |
| S03 | stale | 0.10 | 静默 |
| S04 | numeric_corruption | 0.07 | 静默 |
| S05 | wrong_entity | 0.05 | 静默 |
| S06 | redacted | 0.03 | 静默 |
| S07 | malformed_ok | 0.04 | 静默 |
| S08 | unit_swap | 0.03 | 静默 |
| S10 | phantom_write | 0.05 | 静默 |
| A01 | output_injection | 0.03 | 对抗 |
| A02 | description_poisoning | 0.01 | 对抗 |
| A03 | rug_pull | 0.01 | 对抗 |
| **合计** | | **1.00** | |

没有放 L04（`http_status`）：它只在 HTTP 传输下适用，stdio 运行会丢掉全部 L04 回合，等于悄悄改变了整个分布。需要它的运行请带上 HTTP 场景另行加上。

按类别看，显式 0.42、静默 0.53、对抗 0.05。静默占比最大，因为这正是本项目要解决的问题：静默故障是智能体最不容易发现、也最不容易靠重试挽回的一类（见下文）。

## 为什么是这些数字：论证与弱点

**这是假设，不是测量。** 项目书引用的 2026 年论文告诉我们哪几类故障常见、智能体如何应对；但没有一篇给出可以照抄到权重里的生产环境 MCP 故障频率表。下面的数字是对这些发现的定性解读，取到百分位后归一化到 1。计划书 F25 明确要求说明这一点：权重是“依据文献定性判断得出的假设”。所以 `realistic-2026` 的得分应读作“这个智能体在一套合理的 2026 年故障组合下表现如何”，而不是它在野外的故障率估计。

### 显式与静默

Loud Failures, Quiet Failures [29] 报告显式报错的察觉率是 91.3%，“看似合理的错值”只有 58.8%；[31] RITE 说静默错误让任务成功率大约减半，且比显式错误更难处理；[28] 发现工具返回 `status:ok` 但内容损坏时不诚实率升到 45.3%，而 `status:error` 时为 0%。综合起来静默故障的权重应当高于显式故障。本画像给到 0.53 对 0.42，差距不大，因为显式故障仍是任何监控系统能抓到的大多数，画像也不该让重试与换源这类行为得不到锻炼。

### 各种显式故障

- L01 timeout，0.10；L05 rate_limited，0.08。两者是任何 MCP 部署都会遇到的传输错误，[51] 汇总的运行时故障报告把它们当作日常情况。L05 略低，因为限流不像超时那样会伪装成服务器卡死。
- L03 tool_error，0.10：普通的上游错误，是 MCP 故障研究 [30] 里最常见的显式失败。
- L02 jsonrpc_error，0.05：协议层错误，比工具错误少，因为服务器通常把失败包在工具结果里。
- L06 tool_missing，0.04；L07 schema_drift，0.05：配置与部署漂移。ToolBench-X [34] 与 MCP 故障研究 [30] 都提到工具面与客户端预期不符的服务器。它们需要“智能体发现工具”和“智能体调用工具”之间发生一次部署，所以权重不高；但对于长时间运行的智能体，一旦发生就是持续性的。

### 各种静默故障

- S03 stale，0.10：静默类里最高。AgentCheck [32] 发现重试对过期数据没用（停在 3–4/10），ToolMaze [35] 整个基准围绕数据过期时的重新规划；生产环境里过期缓存和“上次已知值”无处不在。
- S01 empty_ok，0.08；S02 truncated，0.08：空结果和残缺结果是最常见的“成功了但数据不全”，[28] 把它们和会引发编造的 `status:ok` 情况归在一起。
- S04 numeric_corruption，0.07：[28]、[29]、[31] 都把错数字当作静默失败的典型，但错数字也是仔细的智能体有时能靠交叉核对抓到的，所以排在过期、空结果之后。
- S05 wrong_entity，0.05：[31] 与 [38] 都描述了多工具流程里“答非所问”的对象错误；需要实体型查询，所以取中间权重。
- S06 redacted，0.03；S08 unit_swap，0.03：遮蔽与单位混淆（[40]、[39]、[38]）确实存在，但需要正好命中相应键名，范围较窄，是静默类里最小的两个。
- S07 malformed_ok，0.04：返回半截 JSON 的提供方不少，比遮蔽高一点、比截断低一点（[40]）。
- S10 phantom_write，0.05：[51] 的运行时故障讨论，加上 RITE 与编造研究的发现，把“写了没生效”列为代价最高、最不易察觉的失败之一。取中间权重，因为基准集里写场景的比例小于读场景（S37、S38 的配比）。

### 各种对抗故障

- A01 output_injection，0.03：注入藏在工具输出里，是攻击者可控数据最可能命中的情形。
- A02 description_poisoning，0.01；A03 rug_pull，0.01：需要服务器被攻陷或行为被改，发生得更少，但一旦发生最严重（[27] 研究野外的恶意 Skills，[51] 报告发布后行为变化的工具）。两者合计 0.05，大约每 20 次抽样出现一次对抗回合，3 次抽样下经常能遇到、又不至于盖过其余故障。

## 如何用真实事故数据重新校准

有了计数而不是轶事后，权重就从估计变成测量。计划如下：

1. **收集回合，而不是投票。** 从基于卡带的运行和真实事故记录里，逐条记下失败的故障 id、工具名和智能体是否恢复。`realistic-2026` 本身已经给每个回合打上故障 id，所以任何画像下的运行都能产出这类数据。
2. **带不确定性估计频率。** 对故障计数做 Dirichlet-多项分布（或复用 `scoring/bootstrap.py` 的 bootstrap），配一个通用先验。观测少时后验接近当前权重；观测多时才明显移动。这样少数高调事故不会劫持整个组合。
3. **按上下文分层。** 故障频率与工具类型（读、写、多源）和传输方式有关。不要只做一张全局表，允许按上下文分表，再把上下文表套用到基准集的场景配比上，得到 `realistic-2026`。
4. **重排榜单以保证可比。** 权重一变，就重跑榜单，并把权重表版本和模型版本一样记录下来。
5. **写 ADR。** 改动已冻结画像的内置成员或权重属于接口变更（ADR-0002）；新表和依据数据要以新 ADR 发布。

在步骤 1 积累够数据之前，上面的权重就是有记录的默认值；用它们产出的每个结果都应结合本页的说明来读。

## 来源

参考文献编号与项目书第 16 节一致，访问日期均为 2026-10-27。

- [27] Liu et al., *"Do Not Mention This to the User": Detecting and Understanding Malicious Agent Skills in the Wild*, USENIX Security 2026.
- [28] *Fabrication After Tool Failure: Tool-Augmented Agents Assert Values Their Tools Did Not Return*, arXiv:2609.14758.
- [29] *Loud Failures, Quiet Failures: Fault Detection and Recovery in Tool-Using Language Model Agents*, arXiv:2610.10062.
- [30] *Tool-Calling LLM Agents Under Realistic MCP Faults: Scale Does Not Purchase Fault Tolerance*, arXiv:2610.32555.
- [31] *RITE: Evaluating End-to-End Resilience to Silent Tool Errors in E-Commerce Agentic Systems*, arXiv:2610.27777.
- [32] *AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over MCP*, arXiv:2607.11098.
- [35] *When Tools Fail: Benchmarking Dynamic Replanning and Anomaly Recovery in LLM Agents (ToolMaze)*, arXiv:2606.05806.
- [38] *ComplexMCP: Evaluation of LLM Agents in Dynamic, Interdependent, and Large-Scale Tool Sandbox*, arXiv:2605.10787.
- [39] *ToolFailBench: Diagnosing Tool-Use Failures in LLM Agents*, arXiv:2607.04686.
- [40] *Auditing Automated Evaluation, Error Propagation, and Runtime Mitigation in Tool-Using Language Agents (AgentProp-Bench)*, arXiv:2604.16706.
- [51] MCP 故障实证研究：arXiv:2606.05339（来自 473 个仓库的 837 条运行时故障讨论）、arXiv:2603.05637（407 个 MCP 相关 issue 的分类）。

权重不依据其他来源。以上引用依据的是项目书对这些发现的表述；我们没有重新阅读原文，所以本页引用的数字在进入对外材料前应回到论文核对。
