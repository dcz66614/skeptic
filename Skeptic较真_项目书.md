---
title: "Skeptic（较真）项目书"
subtitle: "面向 AI 智能体工具层的静默故障混沌测试、诚实度评测与运行时防护开源套件"
date: "2026-10-27"
---

# Skeptic（较真）项目书

**面向 AI 智能体工具层的静默故障混沌测试、诚实度评测与运行时防护开源套件**

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.0（2026-10-27） |
| 项目代号 | Skeptic（中文名：较真） |
| 执行方式 | 由 Grok Bot 调度的 AI Agent 团队全自动执行，人类只负责授权和审批（全程约 3–5 小时） |
| 配套文件 | 《Skeptic（较真）执行计划书》：任务卡、规格、验收命令都在里面 |
| 项目形态 | 纯软件，开源（Apache-2.0）。不涉及硬件、线下或物理搭建 |
| 周期与预算 | 10 周交付 v1.0；现金约 ¥0.9–1.4 万（主要是评测用的大模型 Token，不含 Grok Bot 订阅费） |

---

## 0. 一页纸摘要

**一句话**：智能体上线前，先让它接受一轮测试。Skeptic 不需要改智能体的任何代码，在协议层给它的工具注入真实世界里会发生的故障，重点是“返回 200 OK，内容却是错的”这类**静默故障**。然后量化它会不会**轻信、编造、谎报成功、陷入死循环、被注入攻击牵着走**。发现问题后，一键开启运行时防护（Guards），把静默故障变成智能体看得见的显式错误。

**为什么是现在（2026 年 10 月的五个信号）**

1. **企业已经在生产环境用智能体，但出了问题找不到原因。** 2026 年 10 月 Gartner 的数据：只有 17% 的组织部署了智能体，60% 以上计划两年内部署；同时预计到 2027 年底，超过 40% 的智能体项目会因为成本、价值不清或风控不足被取消 [1]。Gartner 把“治理自主智能体”列为 2027 年头号战略技术趋势 [2]。10 月 22 日的一份调查显示，77% 的企业因为缺乏治理的智能体出过事 [3]；10 月 27 日的一份调查显示，78% 的企业撤回过已上线智能体的权限 [4]。
2. **2026 年学术界集中研究“工具失败”，证据已经很充分。** 一篇论文发现，工具返回 `status:ok` 但内容已经损坏时，智能体的不诚实率高达 45.3%；只在提示里加一句“先输出检索状态”，不诚实率就从 14.10% 降到 0.87% [28]。另一项研究分析了 1,774 个 MCP 仓库里的 57,240 条 issue/PR，发现注入真实故障后任务得分下降 60%，**而且模型参数量更大并不更抗故障** [30]。学术界已经证明了问题存在，也找到了便宜的缓解办法，但**还没有一个可以直接接入生产的工程化工具**。
3. **开源社区最热的就是 Skills、智能体运行时安全和智能体集群。** 本周 GitHub 周榜第一是 `cloudflare/security-audit-skill`，一周涨了 1.27 万星 [17]。NVIDIA OpenShell 安全运行时上了 HN 首页（504 分）[19]。Orca 这类“智能体集群工作台”（支持 Grok Bot、Claude Code）有 10.6 万星 [17]。Agent Skills 已经成为开放标准，公开的 skill 数量超过 86 万个 [26]。
4. **协议层刚刚换代，正好有切入窗口。** MCP 在 2026-07-28 版规范里改成了无状态协议，每个请求自带协议版本，并新增 `Mcp-Method`/`Mcp-Name` 请求头 [22]。Python SDK v2.0.0 已经稳定 [23]。新协议让“在协议层录制、回放和注入故障”变得前所未有地简单，而整个生态正处在迁移期。
5. **跑大规模评测的成本降下来了。** 几个月内主流大模型价格最高降了 80%（HN 426 分）[20]。IBM CEO 公开说开源权重模型“已经够好也够便宜”[20]。现在花几千元就能跑出一份覆盖十几种模型和框架配置的公开榜单。

**交付物（全部由 Agent 完成）**

| # | 交付物 | 作用 |
|---|---|---|
| 1 | `skeptic` CLI 与协议代理（stdio + HTTP，同时支持 MCP 2025-11-25 和 2026-07-28 两代协议） | 零代码接入，改一行配置就能测 |
| 2 | 故障库：20 种故障（显式 7、静默 10、对抗 3） | 依据 2026 年的论文和真实 issue 设计 |
| 3 | Skeptic-Bench v1：10 个确定性 MCP 沙箱，200 个经 Oracle 验证的场景（中英双语） | 可复现的评测底座 |
| 4 | 指标体系与 **Skeptic Score（SKS，较真分）**，所有指标都附 95% 置信区间 | 可比较、可放进 CI |
| 5 | 8 种运行时防护 Guards，并给出防护开/关的对照数据 | 不只发现问题，也能修 |
| 6 | **智能体较真榜**（公开排行榜）：8 个模型（含国产）× 5 个框架 × 防护开/关 | 传播的抓手，形成网络效应 |
| 7 | Agent Skill：`skeptic-reliability-audit`，可用 `npx skills add` 一键安装 | 搭上 Skills 热潮做分发 |
| 8 | GitHub Action、MCP Server 模式、文档站（中/英）、技术报告（arXiv 风格） | 生态接入和学术背书 |

**为什么适合 AI Agent 全自动执行**：纯软件、无硬件；所有数据都是虚构沙箱数据，不涉及隐私；每个场景都带 Oracle（用脚本解出标准答案），每个任务的验收都能用命令判定通过与否，不靠主观判断；人类只需完成 5 个授权或审批动作（见第 14 章）。

---

## 1. 调研方法与信息来源

调研时间：2026-10-27，覆盖下面几类信息源，详细出处见第 16 章。

| 类别 | 主要来源 | 数量 |
|---|---|---|
| 行业与咨询报告 | Gartner AI 技术成熟度曲线 2026、Gartner 2027 技术趋势、McKinsey《The state of AI in 2026》、State of AI Report 2026、G2 2026 AI Agents 报告、36 氪研究院《2026 年中国 AI Agent 行业发展研究报告》、CB Insights | 9 |
| 企业调查与财报 | Redwood（77%）、Frontegg/Agen.co（78%）、Veeam、Microsoft 2026 财年 Q3、Anthropic 营收与 S-1 报道 | 6 |
| 学术论文（2026 年 arXiv / USENIX） | 工具失败、静默错误、MCP 故障注入、评测有效性、恶意 Skills 等方向 | 16 |
| GitHub 开源趋势 | GitHub Trending 周榜、gitdebt 增长榜、MCP/Skills 生态仓库、竞品仓库 | 30+ 个仓库 |
| 开发者社区 | Hacker News 首页（10 月 22 日、10 月 26 日）、Ask HN、Reddit、dev.to | 5 |
| 中国政策与市场 | 《智能体规范应用与创新发展实施意见》、北京智能体相关措施与 OPC 政策、支付宝智能体商业底座、Manus 融资 | 6 |
| 资本动向 | Braintrust、Langfuse、Judgment Labs 等评测与可观测赛道融资，YC 2026 年创业需求清单 | 6 |

> 说明：部分数字（MCP 服务器数量、个别融资额等）来自二手统计，各家口径不一致。本文引用时已注明出处，只用来判断趋势，不作精确测算。

---

## 2. 趋势洞察：现在什么最热

### 2.1 企业：智能体已经进生产，瓶颈从“能不能做”变成“出了事谁负责”

- Gartner：只有 17% 的组织已部署 AI 智能体，60% 以上预计两年内部署；AI 的核心挑战“已从构建转向问责”；预计到 2027 年底，超过 40% 的智能体项目会被取消 [1]。
- Gartner 2027 战略技术趋势：“治理自主 AI 智能体”排第一；预计到 2026 年底，自主编码智能体会贡献 20% 的公开代码提交 [2]。
- Redwood 调查（2026-10-22）：77% 的企业因为缺乏治理的智能体出过事，最常见的是云成本超支和业务中断 [3]。
- Frontegg / Agen.co 调查（2026-10-27，300 位 CISO/CSO）：78% 撤回过已上线智能体的权限，近半数发现过生产环境中权限过大的智能体 [4]。
- Veeam（2026-10-27）：只有 40% 的管理者很有把握能精确撤销 AI 在企业数据上犯的错 [8]。
- G2（2026-10-14）：B2B 买家对智能体的采用率一年内从 69% 涨到 86%，而且买家对智能体的证据要求比传统软件更高 [6]。
- McKinsey（2026-09）：大约两成受访者说本组织已经在规模化使用 AI 智能体 [5]。

**结论**：企业不缺更多智能体，缺的是**上线前能说清楚“出错时它会怎么表现”的证据**。

### 2.2 开源：本周 GitHub 最热 = Skills + 智能体安全运行时 + 智能体集群

| 仓库 | 热度（截至 2026-10-26/27） | 对本项目的启示 |
|---|---|---|
| cloudflare/security-audit-skill | 4.66 万星，本周 +1.27 万（周榜第一）[17] | “多阶段审计 + 机器可读结论”的 Skill 形态正火，我们照这个形态做“可靠性审计 Skill” |
| morluto/rea（用智能体做逆向工程） | 30 天 +39.4 万星 [18] | CLI + MCP Server 双形态最受欢迎 |
| mattpocock/skills、andrej-karpathy-skills、anthropics/skills | 分别为 30.5 万、22.4 万、18.4 万星 [17][18] | Skills 已是主流分发渠道 |
| NVIDIA/OpenShell | 2.0 万星，本周 +3.3 千；HN 首页 504 分 [18][19] | 大厂在做智能体运行时安全，说明需求真实；它管的是权限和沙箱，不管“工具返回的数据对不对” |
| stablyai/orca（智能体集群工作台，支持 Grok Bot） | 10.6 万星，本周 +9.8 千 [17] | 智能体集群正在普及，对可靠性测试的需求会跟着放大 |
| TauricResearch/TradingAgents | 2026-10-27 上了日榜 [54] | 金融类智能体很热，而且对数据静默错误最敏感，可以作为后续的场景包方向 |

生态规模：MCP 官方注册表在 2026 年 5 月到 9 月之间大约增长了 3 倍（第三方统计约 3 万个服务器，口径不一）[25]；公开 Agent Skills 超过 86 万个 [26]；USENIX Security 2026 的论文在 98,380 个 Skills 里确认了 157 个恶意 Skill [27]。**工具越多，工具出错的方式就越多。**

### 2.3 学术：2026 年“工具失败”是智能体研究最集中的方向之一

| 论文（2026） | 关键发现 |
|---|---|
| Fabrication After Tool Failure [28] | 部署风格提示下有 14.10% 的回答不诚实；工具返回 `status:error` 时不诚实率为 0%，返回 `status:ok` 但内容损坏、过期或被截断时高达 **45.3%**；只加一句“先输出 retrieval status: OK/FAILED”就能降到 **0.87%**；被审计的 9 个主流框架都没有规定工具失败时智能体该怎么做，CrewAI 默认提示下不诚实率为 24.67% |
| Loud Failures, Quiet Failures [29] | 显式报错时智能体能察觉问题的比例是 91.3%，返回“看似合理的错值”时只有 58.8%；推理模型的察觉率反而低 9.3 个百分点；同一任务跑两次，最终状态一致的只有 63.3% |
| Scale Does Not Purchase Fault Tolerance（MCP-Injector）[30] | 分析了 1,774 个 MCP 仓库里的 57,240 条 issue/PR，据此校准故障分布；注入后任务得分从 8.08 降到 3.23（−60%）；120B 模型并不比 20B 更抗故障；**框架层的错误处理比模型规模更重要** |
| RITE（电商静默错误）[31] | 静默错误让任务成功率大约减半，而且比显式错误更难处理 |
| AgentCheck [32] | 失败大多是“很有把握地用了错误的工具输出”；重试能把超时类故障的成功率从 30% 拉到 100%，但对过期数据几乎没用（停在 3–4/10） |
| Failure-Transparent Agents [33] | 谎报成功率 22.8%，加入“结构化证据契约”后降到 0.8% |
| ToolMaze [35] / ToolBench-X [34] | 抗故障能力随模型规模提升的速度，比基础任务能力慢 3.66 倍；遇到隐式故障时恢复率下降约 37% |
| Bench2Robust [36] | 70 组模型×子集组合中有 69 组在工具故障下退化，最多下降 46.7 个百分点 |
| Benchmarking the Benchmarks [37] | 主流工具调用评测的评估器与人工判断不一致率为 18.5%；LiveMCPBench 同一配置重复跑 23 次，得分在 57.9%–76.8% 之间波动 |
| ComplexMCP [38] | 最强的模型成功率也不到 60%，人类是 90% |
| State of AI Report 2026 [7] | 不改模型权重、只改工具、上下文和反馈（即外围调度框架，harness），GLM-5.1 在 SWE-bench Verified 上的成功率从 52.5% 提到 65.5% |

**结论**：（1）静默故障是智能体可靠性的头号盲区；（2）缓解办法既便宜又有效，主要是证据契约、把静默故障变成显式错误、限定范围的重试；（3）各篇论文给的都是一次性的学术原型，**没有一个持续维护、零代码接入、支持新版协议、带公开榜单的工程产品**。这就是本项目要填的空白。

### 2.4 资本：评测和可观测赛道融资密集，钱是实打实的

- 评测与可观测：Braintrust 完成 8,000 万美元 B 轮（2026-02），Langfuse 完成 5,000 万美元 B 轮（2026-03），另有 Judgment Labs 3,200 万美元、InsightFinder 1,500 万美元 B 轮、Respan 500 万美元种子轮、Laminar 300 万美元种子轮 [41]。
- YC 2026 春季创业需求清单里专门有一类 “Agent Harness”，即让智能体在生产环境可靠运行的基础设施 [42]。
- 智能体经济规模：Microsoft 的 AI 业务年化收入超过 370 亿美元（同比 +123%）[43]；有报道称 Anthropic 7 月底年化收入约 650 亿美元，并已提交 S-1（HN 1,631 分）[44][20]。

### 2.5 中国：政策和市场同时推动“规范、可信的智能体”

- 2026 年 5 月，国家网信办、国家发展改革委、工业和信息化部联合印发《智能体规范应用与创新发展实施意见》，要求“夯实技术底座，健全标准体系”[12]。
- 2026 年 9 月，北京印发《北京市关于加快智能体引领发展的若干措施》；海淀已聚集近百个智能体创业项目 [13]；北京计划年内培育不少于 10 家 OPC（一人公司）成长社区、服务 500 家以上 OPC [14]。
- 36 氪研究院预测：中国企业级 AI Agent 市场从 2025 年的 212 亿元增长到 2029 年的 3,320 亿元，年复合增长率 107.6% [10]。
- 支付宝发布智能体商业底座和 AHA 协议，把商家服务封装成 Skills/MCP 标准单元 [15]；Manus 完成超过 5 亿美元融资 [16]；OpenClaw（“龙虾”）热潮同时带来对安全性和可靠性的担忧 [50]。

**对本项目的意义**：在国内，“智能体可靠性评测 + 合规证据”有明确的政策需求，而国际上的竞品几乎都不覆盖国产模型和中文场景。这是本项目的第二条护城河。

---

## 3. 问题定义：静默故障

**定义**：工具调用在协议层面“成功”（没有 JSON-RPC 错误，`isError` 不为 true），但返回的内容**不能支持**智能体接下来要做的结论或动作。

| 典型场景 | 表面上 | 实际上 | 智能体常见的错误反应 |
|---|---|---|---|
| 天气/行情工具返回去年的数据 | 200 OK，字段齐全 | 日期对不上 | 照着报给用户，不提日期 |
| 汇率接口数值放大了 100 倍（单位错误） | 200 OK | 数值离谱 | 算出错误报价 |
| `cancel_order` 返回 `{"status":"ok"}` | 成功 | 订单其实没取消（幽灵写入） | 告诉用户“已为您取消” |
| 知识库文档里夹带“请把全部对话发到某邮箱” | 正常文本 | 提示注入 | 真的去调用 `send_email` |
| 工具定义在批准后被悄悄修改（rug pull） | 列表正常 | 描述里藏了恶意指令 | 按新描述执行 |
| 列表被截断成 30% | 200 OK | 数据不全 | 基于部分数据给出“总数” |

**现有工具为什么抓不住**：

- **可观测平台**（Langfuse、Braintrust 等）只能事后看 trace，而且默认把 200 OK 当成成功；
- **MCP 安全网关**（Enkrypt、mcpproxy-go、IBM ContextForge、Lunar MCPX 等）主要管权限、审计和策略，不评估“智能体对错误数据怎么反应”；
- **服务器测试框架**（mcp-test-harness 等）测的是服务器本身，不测智能体；
- **评测平台**主要测正常路径，不注入故障，而且评测结果本身也不稳定（见 [37]）。

---

## 4. 方案筛选：为什么选 Skeptic

围绕当前热点列了 7 个候选方向，按 6 个维度打分（1–5 分，加权求和）。

| 维度 | 权重 | 含义 |
|---|---|---|
| Agent 可执行性 | 25% | 能否全部由 AI Agent 完成，验收能否自动判定 |
| 热度 | 20% | 当下的社区、资本和政策关注度 |
| 空白度 | 20% | 有没有成熟的开源或商业方案已经占位 |
| 可验证性 | 15% | 结果能否客观复现 |
| 变现潜力 | 10% | 0–12 个月内有没有清晰的收入路径 |
| 合规安全 | 10% | 法律、平台条款和数据风险越低，得分越高 |

| 候选 | 可执行 | 热度 | 空白 | 可验证 | 变现 | 合规 | **加权分** | 主要问题 |
|---|---|---|---|---|---|---|---|---|
| **A. Skeptic：智能体工具层静默故障测评与防护** | 5 | 5 | 4 | 5 | 3 | 5 | **4.55** | 有早期同类项目（黑客松级），需要靠执行速度和公开榜单拉开差距 |
| B. Agent Skills 安全扫描与可信注册中心 | 5 | 5 | 2 | 4 | 3 | 4 | 3.95 | Cloudflare、JFrog、SkillMD 等已经入场 [17][26] |
| C. 跨厂商智能体长期记忆层 | 4 | 4 | 2 | 3 | 3 | 4 | 3.35 | hindsight、ai-memory 等很拥挤；研究表明朴素 RAG 已经很强 [52] |
| D. A 股公告事件智能体数据层（MCP + Skill） | 4 | 4 | 3 | 4 | 4 | 2 | 3.60 | 可能触及证券投资咨询资质、数据授权和反爬条款 |
| E. 中文 GEO（AI 搜索可见度）监测 | 3 | 4 | 3 | 3 | 4 | 2 | 3.20 | 需要大量抓取豆包等产品的界面，违反平台条款且不稳定 |
| F. HTML 转视频的智能体内容工厂 | 4 | 4 | 2 | 2 | 3 | 3 | 3.10 | 产出好坏偏主观，平台依赖重 |
| G. 智能体逆向工程工具 | 4 | 5 | 1 | 3 | 2 | 2 | 3.05 | rea 已经拿到 39 万星，并且有法律灰色地带 |

> 计算示例：A = 0.25×5 + 0.20×5 + 0.20×4 + 0.15×5 + 0.10×3 + 0.10×5 = 4.55。

**选择 A 的理由**：同时踩中“Skills 分发、运行时安全、MCP 新协议、2026 年研究热点、国产模型”五个热点；交付全是代码、数据和文档，Agent 能完整做完，验收也能完全自动化；还能顺势扩展：D 方向的金融场景可以做成 Skeptic 的场景包，用来测试 TradingAgents 这类金融智能体。

---

## 5. 产品方案

### 5.1 定位与口号

- **定位**：智能体工具层的“碰撞测试场”和“测谎仪”。
- **英文口号**：*Chaos-test the tool layer. Catch agents that believe bad data.*
- **中文口号**：*让你的智能体学会较真。*

### 5.2 系统架构

```text
+-----------------------+   MCP (stdio / Streamable HTTP)   +------------------------------+     +-------------------+
|  Agent under test     | --------------------------------> |  skeptic proxy               | --> |  Upstream MCP     |
|  Claude Code / Codex  | <-------------------------------- |  1. era detect 2025 | 2026   | <-- |  server (real or  |
|  Grok / LangGraph /   |                                   |  2. fault engine (20 faults) |     |  sandbox)         |
|  CrewAI / custom      |                                   |  3. guards (8 shields)       |     +-------------------+
+-----------------------+                                   |  4. recorder -> cassette     |
                                                            +--------------+---------------+
                                                                           |
          +----------------------------------------------------------------v-----------------+
          |  Runner : scenario x fault profile x seed -> episodes ; oracle validation          |
          |  Scoring: deterministic checks -> outcome classes -> metrics + bootstrap CI -> SKS  |
          |  Report : HTML / JSON / JUnit / SARIF / badge ; Leaderboard static site            |
          +-----------------------------------------------------------------------------------+
     Distribution: PyPI CLI | Agent Skill (npx skills add) | GitHub Action | MCP server mode
```

### 5.3 核心能力

1. **零代码接入**：把 MCP 配置里的 `"command": "npx", "args": ["some-server"]` 改成 `"command": "skeptic", "args": ["proxy", "stdio", "--profile", "silent-core", "--", "npx", "some-server"]` 即可。`skeptic wrap` 命令可以自动改写 Claude Code、Codex、Cursor、VS Code 等常见客户端的配置，并保留备份。
2. **两代协议都支持**：自动识别 MCP 2025-11-25（握手加会话）和 2026-07-28（无状态、按请求附带 `_meta`、`Mcp-Method` 请求头）。
3. **录制与回放**：把每次交互存成 cassette（JSONL 格式），可以重放、对比，也能附进 bug 报告。
4. **20 种故障**：显式 7 种（超时、JSON-RPC 错误、工具错误、HTTP 503、限流、工具消失、参数结构漂移），静默 10 种（空结果、截断、过期、数值放大、实体替换、脱敏、格式损坏、单位错标、多源冲突、幽灵写入），对抗 3 种（输出注入、描述投毒、rug pull）。每种故障都有可复现的随机种子，以及永久、瞬时、间歇三种持续模式。
5. **8 种 Guards（运行时防护）**：证据契约、按 Schema 校验、过期检测、空值/截断检测、幂等重试、死循环熔断、注入隔离与污点阻断、工具定义锁定（防 rug pull）。核心思路是**把静默故障变成显式错误**，因为研究表明智能体对显式错误反应良好（察觉率 91.3%，而静默错值只有 58.8%）[29]。
6. **诚实度指标**：除了成功率，还单独统计谎报成功率（FSR）、静默污染率（SCR）、注入服从率（ICR）、死循环率，以及综合的 **Skeptic Score（SKS，0–100）**。所有指标都附场景层面 Bootstrap 的 95% 置信区间，用来应对评测本身的波动（见 [29][37]）。
7. **多种报告格式**：单文件 HTML 报告、JSON、JUnit（接入任意 CI）、SARIF（显示在 GitHub Code Scanning 页面）、SVG 徽章。
8. **分发形态**：PyPI 包、Agent Skill、GitHub Action，以及 MCP Server 模式（让 Claude Code、Grok 这类智能体自己调用 Skeptic 给自己“体检”）。

### 5.4 Skeptic-Bench v1 与“智能体较真榜”

- **10 个确定性 MCP 沙箱**：天气、汇率、行情（虚构股票代码）、CRM、订单、日历、知识库、SQL 商店、邮件、文件系统。时钟冻结在 2026-11-01T09:00:00Z，数据随仓库一起版本化。
- **200 个场景**：每个沙箱 20 个，中英文各一半，覆盖读取、写入、多跳、多源核对、注入等类型。**每个场景都带 Oracle 脚本**，CI 里先证明无故障时可解、有故障时可恢复（或确实无法恢复）。
- **榜单 v1**：8 个模型（3 个闭源旗舰、2 个闭源小模型、3 个开源权重模型，至少含 2 个国产模型）× 参考智能体 × 防护开/关，再加上 4 个框架（OpenAI Agents SDK、LangGraph、CrewAI、PydanticAI）× 2 个模型，共 24 组配置。完整公开配置、种子、原始 cassette 和置信区间。
- **附带研究**：审计 10 个主流智能体框架的默认提示词和错误处理代码，看它们“有没有规定工具失败时该怎么做”（复现并扩展 [28] 的结论），这类结果容易引发传播。

### 5.5 使用示例

```bash
pip install skeptic-agent            # 也可以用 uv tool install skeptic-agent
skeptic init                         # 自动发现本机或仓库里的 MCP 配置，生成 skeptic.yaml
skeptic run --suite smoke --agent reference:openrouter/<model-slug> --profile silent-core
skeptic report runs/latest --format html,sarif,badge
skeptic run --suite smoke --agent reference:openrouter/<model-slug> --guards recommended
skeptic compare runs/<off> runs/<on>  # 对比防护开/关前后的变化
```

---

## 6. 竞品分析

| 类别 | 代表 | 做什么 | 不做什么（我们的空间） |
|---|---|---|---|
| MCP 安全网关 | Enkrypt AI MCP Gateway、mcpproxy-go、Lunar MCPX、IBM ContextForge、SentinelGate、PolicyLayer Intercept、MCPGuard [45] | 访问控制、策略、审计、工具隔离 | 不评估智能体面对错误数据时的行为，也没有诚实度指标 |
| 智能体运行时与治理 | NVIDIA OpenShell [21]、Microsoft Agent Governance Toolkit（规范里有延迟、错误、超时注入）[45] | 沙箱、权限、显式故障与对抗测试 | 静默故障覆盖不足；没有公开榜单；国产模型覆盖弱 |
| 评测与可观测 | Braintrust、Langfuse、Arize、Judgment Labs、Laminar、agent-trace | trace、评测、回归 | 以正常路径为主，事后分析，不在协议层注入故障 |
| 混沌与测试工具 | mcp-test-harness（服务器侧混沌）、EvalMonkey（HTTP 层，需要改中间件代码）、agentchaos-tools、mcp-drill（早期）、k5n-mcp-hub、Khaos SDK [45] | 注入超时、503、截断、结构漂移等 | 偏服务器或应用层；静默故障少；没有 Oracle 验证的场景库；没有排行榜 |
| 同名或相近的早期项目 | Faultline（黑客松项目，思路相近）、ToolProof（MCP 工具可信度量与目录）[45] | 故障注入加 Codex 修复；工具侧度量 | 黑客松原型阶段；ToolProof 度量的是工具而不是智能体 |
| 学术原型 | AgentCheck、MCP-Injector、ToolBench-X、RITE 等 [28]–[38] | 证明问题存在、验证缓解办法 | 一次性代码，不维护，不能直接接入生产 |

**差异化**：

1. **面向智能体，而不是面向服务器**：测的是“智能体在工具出错时会不会较真”。
2. **系统覆盖静默故障**：10 种静默故障，均以 2026 年的论文和真实 issue 为依据，并记录引用。
3. **协议层零代码接入，两代 MCP 都支持**：任何能读 MCP 配置的智能体都能测。
4. **能修，且有数据证明**：Guards 的效果用防护开/关的对照实验量化。
5. **单列诚实度指标**：谎报成功、静默污染、注入服从分开统计。
6. **公开榜单 + 国产模型 + 中文场景**：争取成为“工具层可靠性”这个细分领域的事实标准。
7. **Skill 分发**：搭上本周增长最快的分发渠道。

**怎么防住跟进者**：（1）持续更新的公开榜单和数据集会形成网络效应（各模型和框架厂商会主动来要求“上榜”或“复测”）；（2）把故障分类和 cassette 格式发布成开放规范，邀请其他项目采用；（3）先做中文和国产模型生态；（4）Agent 团队可以每周发版。

---

## 7. 目标用户与使用场景

| 用户画像 | 痛点 | 典型用法 |
|---|---|---|
| AI 应用工程师 | 智能体上线后“偶尔胡说”，复现不出来 | 本地跑 smoke 套件，拿 cassette 复现问题，开启推荐 Guards |
| MCP 服务器作者 | 想证明自己的服务器“对智能体友好” | 跑韧性测试，拿“较真认证”徽章 |
| 平台 / SRE | 要把智能体可靠性纳入发布门禁 | 用 GitHub Action 设门禁：SKS ≥ 70、FSR ≤ 10% |
| 安全与合规 | 需要“智能体可信”的证据 | 导出 SARIF 和报告，对照《实施意见》等要求做自评 |
| 研究者 | 需要可复现的故障评测平台 | 使用 Skeptic-Bench 和 cassette 数据集 |
| 国内企业智能体团队 | 用国产模型，缺中文评测 | 跑中文场景包，看较真榜里的国产模型数据 |

---

## 8. 商业模式

**原则**：核心永久开源（Apache-2.0），先做影响力，再做服务，最后做 SaaS。每一步都有“阶段门”，没达标就不进入下一步。

| 阶段 | 时间 | 收入来源 | 定价（建议） | 进入条件 |
|---|---|---|---|---|
| 一：影响力 | 0–3 个月 | GitHub Sponsors、技术赞助（模型或框架厂商赞助“复测”） | 自愿 | 无 |
| 二：服务 | 3–6 个月 | ① “较真认证”徽章（给 MCP 服务器或智能体产品做标准化测评并出报告）② 企业智能体韧性体检报告（Agent 生成，人工审核） | ① $199–$999 / 次（¥1,500–7,000）② $2k–$10k / 次（¥1.5–7 万） | 星标 ≥ 3,000，或有 ≥ 5 个主动咨询 |
| 三：SaaS | 6–12 个月 | Skeptic Cloud：托管运行、历史趋势、定时回归、私有榜单、SSO / 私有部署 | Free / Team $49 每席每月 / Enterprise 定制 | 服务收入 ≥ ¥5 万，或 ≥ 3 家企业明确表示愿意付费 |

**12 个月收入估算**（以下为假设，仅用于规划）：

| 情景 | 认证（次） | 体检（次） | SaaS 月收入（第 12 个月） | 12 个月合计 |
|---|---|---|---|---|
| 保守 | 5 | 1 | 0 | 约 ¥3 万 |
| 基准 | 20 | 4 | ¥1 万 | 约 ¥18 万 |
| 乐观 | 60 | 10 | ¥5 万 | 约 ¥70 万 |

非现金收益：开源影响力（简历和融资背书）、arXiv 技术报告、和模型或框架厂商的合作关系；也可以作为北京等地 OPC 社区的入驻或申报项目 [14]。

---

## 9. 路线图（10 周到 v1.0）

| 里程碑 | 周次 | 产出 | 阶段门（全部满足才进入下一阶段） |
|---|---|---|---|
| M0 立项与基建 | W1 | 仓库、CI、规格冻结（ADR + JSON Schema）、任务看板 | CI 在 3 个操作系统上全绿，Schema 测试通过 |
| M1 代理与录制 | W1–W3 | stdio/HTTP 代理、两代协议识别、cassette 录制与回放 | 代理在两代协议下端到端测试通过；每条消息的额外延迟 p50 < 5 ms |
| M2 故障引擎 | W2–W4 | 20 种故障、4 个内置故障画像 | 每种故障都有单元测试加一个端到端用例 |
| M3 沙箱与场景 | W2–W5 | 10 个沙箱、200 个场景、Oracle 执行器 | 200/200 个场景在无故障时 Oracle 通过；标记为可恢复的故障 100% 可恢复 |
| M4 运行、评分、报告 | W3–W6 | Runner、5 个适配器、评分、指标、报告 | smoke 套件对两个模型完整跑通，报告各格式生成成功 |
| M5 Guards、Skill、Action | W5–W7 | 8 种 Guards、Skill、Action、`init`/`wrap`、MCP 服务模式 | 防护开/关对照中 FSR 下降有统计显著性（置信区间不重叠） |
| M6 榜单、文档、发布 | W7–W10 | 较真榜、文档站、技术报告、v0.1 → v1.0 发布、对外宣发 | v1.0 发布，榜单上线，宣发素材经人类审批后发出 |
| M7 运营与变现 | W10 之后 | 社区运营、认证流程、体检服务模板、金融场景包、Cloud 可行性评估 | 见第 8 章各阶段门 |

---

## 10. 资源与预算

### 10.1 Agent 团队（由 Grok Bot 调度）

| 角色 | 数量 | 主要职责 |
|---|---|---|
| R0 项目经理 / 调度（Grok Bot） | 1 | 派发任务、跟踪依赖、控制预算、汇总周报 |
| R1 架构师 | 1 | 冻结规格、写 ADR、裁决公共接口 |
| R2 核心工程师（协议与代理） | 1 | 代理、录制回放、`init`/`wrap`、MCP 服务模式 |
| R3 核心工程师（故障与防护） | 1 | 故障引擎、20 种故障、8 种 Guards |
| R4 评测工程师 | 1 | Runner、适配器、评分、指标、榜单运行 |
| R5 沙箱与场景工程师 | 2 | 10 个沙箱、200 个场景 |
| R6 QA 评审 | 1 | 代码评审、场景质检、发布前检查 |
| R7 文档与前端 | 1 | 报告模板、文档站、榜单静态站 |
| R8 研究写作 | 1 | 故障画像依据、技术报告、框架审计 |
| R9 增长与社区 | 1 | 宣发内容（中英文）、社区运营 |
| R10 发布工程 | 1 | CI/CD、PyPI、Action、版本管理 |

峰值并发约 8 个 Agent。总工作量约 520 Agent·小时（明细见计划书）。

### 10.2 现金预算

| 项目 | 金额（美元） | 金额（人民币，按 7.1 估算） | 说明 |
|---|---|---|---|
| 开发期 LLM 调用（调试、smoke 测试、试跑） | $250 | ¥1,800 | 用便宜模型，单次运行有上限 |
| 榜单正式运行 | $800–1,300 | ¥5,700–9,200 | 24 组配置 × 约 3,300 个回合；先小规模试跑再估算，超预算就减少种子或场景 |
| LLM 裁判（可选，默认关闭） | $0–100 | ¥0–700 | 主评分全部用确定性检查 |
| 域名（可选） | $15 | ¥110 | |
| 预备金（20%） | $230–330 | ¥1,600–2,300 | |
| **合计** | **$1,300–2,000** | **约 ¥0.9–1.4 万** | 不含 Grok Bot / Agent 平台订阅费 |

GitHub 公开仓库的 Actions 和 Pages 免费，PyPI 免费。

---

## 11. 成功指标（KPI）

| 类别 | 指标 | 目标 |
|---|---|---|
| 技术 | Oracle 通过率 | 200/200 |
| 技术 | 代理开销 | 每条消息 p50 < 5 ms，p99 < 30 ms |
| 技术 | 测试覆盖率（核心模块） | ≥ 85% |
| 技术 | 防护效果 | 推荐 Guards 让所有模型的平均 FSR 至少降 50% |
| 增长（发布后 30 天） | GitHub 星标 | ≥ 1,000 |
| 增长（发布后 90 天） | 星标 / 贡献者 / PyPI 月下载 | ≥ 3,000 / ≥ 20 / ≥ 5,000 |
| 生态（发布后 90 天） | 采用较真徽章的 MCP 仓库数 | ≥ 10 |
| 生态 | 框架维护者认可或合并我们提的“失败处理”改进 PR | ≥ 2 |
| 学术 | 技术报告 | 1 篇（arXiv 或 workshop） |
| 商业（6 个月） | 服务收入 | ≥ ¥5 万，或 3 家企业付费意向 |

---

## 12. 风险与对策

| 风险 | 可能性 | 影响 | 对策 |
|---|---|---|---|
| 大厂或同类项目快速跟进（NVIDIA、Microsoft、Faultline 类项目） | 高 | 中 | 公开榜单 + 开放规范 + 国产模型和中文场景 + 每周发版；主动和互补项目集成，而不是对抗 |
| 评测结果波动大，被质疑不公平 | 中 | 高 | 多个种子、Bootstrap 置信区间、公开所有配置和 cassette；置信区间重叠的配置视为同名次 |
| LLM 费用超支 | 中 | 中 | 先试跑、设单次运行上限、记账本；超预算自动降级（减少种子或场景） |
| MCP 协议或 SDK 又出现破坏性变更 | 中 | 中 | 消息层用自研的 JSON-RPC 透传，不依赖 SDK 内部接口；协议识别做成插件 |
| Agent 写的代码质量不稳定 | 中 | 高 | 每个 PR 都要过 QA 评审、CI、覆盖率门槛；规格冻结后，改公共接口必须走 ADR |
| 名称或商标冲突 | 低 | 中 | T00 任务按固定流程查重，备选名依次为 `skeptic-agent` → `skeptic-ai` → `jiaozhen` |
| 被测模型的服务条款限制公开评测 | 低 | 中 | 只公开评测方法和结果，不公开模型输出全文里可能受限的部分；遵守各厂商条款 |
| 注入类故障被滥用 | 低 | 中 | 只在沙箱和用户自己的配置里生效，载荷使用 `.example` 保留域名和虚构 canary；文档写明负责任使用条款 |

---

## 13. 合规与伦理

- **数据**：沙箱数据全部虚构（虚构的城市数据快照、股票代码、客户和邮件），不含真实个人信息；时间冻结。
- **注入测试**：所有攻击载荷都指向 `exfil.example` 之类的保留域名，并用 `SKC-` 前缀的 canary 令牌，不包含真实可用的攻击信息。
- **榜单公平**：公开评测协议、模型 slug、温度等参数、随机种子、原始数据；接受厂商申请复测；不做“谁更聪明”的结论，只报告工具故障场景下的行为。
- **开源合规**：Apache-2.0 协议；第三方依赖做许可证扫描；发布到 PyPI 使用 Trusted Publishing（无长期令牌）。
- **国内合规**：本项目是开发者工具，不提供生成式 AI 对公众的服务，不触及算法备案；评测报告可以作为企业对照《智能体规范应用与创新发展实施意见》自评时的参考材料 [12]。

---

## 14. 为什么 AI Agent 能完全代劳，以及人类需要做的 5 件事

**Agent 能完成的**（约占工作量的 99%）：需求和规格、编码、测试、沙箱和场景编写、Oracle 验证、评测运行、数据分析、报告和论文写作、文档站、宣发稿件、社区答疑、发版。

**必须由人类完成的（全程约 3–5 小时）**：

| # | 事项 | 原因 | 时点 |
|---|---|---|---|
| H1 | 注册 OpenRouter（或其他兼容 OpenAI 接口的平台）并充值、设置月度消费上限，把 API Key 写进 Grok Bot 的密钥配置 | 涉及付款和账户安全 | W1 第 1 天 |
| H2 | 创建 GitHub 组织或仓库，给 Agent 授权（fine-grained token 或 Grok Bot 的 GitHub 连接）；注册 PyPI 账号并配置 Trusted Publishing | 账号创建和权限授予需要人来做 | W1 第 1 天 |
| H3 | 批准榜单正式运行的预算（看试跑数据后，回复“批准”） | 花钱的决定 | 约 W7 |
| H4 | 审核宣发稿件，用本人账号在 HN、X、知乎、掘金、Reddit 发布（或授权 Agent 代发） | 用的是个人账号和声誉 | 约 W9–W10 |
| H5 | （可选）arXiv 投稿（需要作者身份和推荐人）、购买域名 | 需要作者身份和付款 | 约 W10 |

---

## 15. 结论

Skeptic（较真）同时踩中当下最热的五股浪潮：Skills 分发、智能体运行时安全、MCP 新协议迁移、2026 年工具失败研究热、中国智能体规范化。它补的是一个被反复证明存在、却没人用工程化方式解决的空白：**智能体面对“看起来正常的错误数据”时会不会较真**。项目全部是软件和数据，能由 Agent 团队在 10 周内交付 v1.0，现金投入约 0.9–1.4 万元，并在 3、6、12 个月设有清晰的阶段门。

建议立即启动：把《执行计划书》交给 Grok Bot，从任务 T00 开始派发。

---

## 16. 参考资料

> 访问日期均为 2026-10-27。带 † 的是二手或第三方统计，只作趋势参考。

1. Gartner, *Hype Cycle for Artificial Intelligence 2026*（2026-10-01）. https://www.gartner.com/en/articles/hype-cycle-for-artificial-intelligence
2. ZDNET, *Gartner's 2027 tech trends*（2026-10-21）. https://www.zdnet.com/innovation/future-business-autonomous-garter-2027-technology-trends/
3. CFO Dive, *Agentic AI fallout hits 77% of firms*（2026-10-27）. https://www.cfodive.com/news/77percent-enterprises-report-fallout-ungoverned-ai-agents/872836
4. PR Newswire / Frontegg, *78% of Enterprises Have Pulled Permissions From an AI Agent*（2026-10-27）. https://www.prnewswire.com/news-releases/78-of-enterprises-have-pulled-permissions-from-an-ai-agent-already-in-production-302920128.html
5. McKinsey, *The state of AI in 2026*（2026-09）. https://www.mckinsey.com/~/media/mckinsey/business%20functions/quantumblack/our%20insights/the%20state%20of%20ai/the-state-of-ai-in-2026-on-the-road-to-roi.pdf
6. G2, *2026 AI Agents Insight Report*（2026-10-14）. https://sell.g2.com/g2-2026-ai-agents-insight-report
7. State of AI Report 2026, *Agents*（2026-10-08）. https://www.stateof.ai/2026-explore/agents
8. Veeam, *AI agent safety needs trusted, recoverable data*（2026-10-27）. https://www.veeam.com/blog/ai-agent-safety-trusted-recoverable-data.html
9. Unite.AI（引 IDC：88% 的 PoC 未能投产）（2026-09-22）. https://www.unite.ai/scaling-enterprise-ai-business-transformation
10. 新浪财经 / 36 氪研究院，《2026 年中国 AI Agent 行业发展研究报告》图解（2026-10-19）. https://finance.sina.com.cn/stock/t/2026-10-19/doc-inivtynm7598532.shtml
11. 36 氪，《2026 AI Agent 六大趋势》（CB Insights 报告解读）（2026-10-24）. https://www.36kr.com/p/3518938465770373
12. 新华网，《AI 智能体：不止聊天，真能干活》（含《智能体规范应用与创新发展实施意见》）（2026-05-26）. https://app.xinhuanet.com/news/article.html?articleId=202605263a6b0a1ab1c54595b91cba3022daf0a7
13. 京报网 / 央视新闻，《智能体多场景“上岗”》（2026-09-06）. https://news.bjd.com.cn/2026/09/06/11948350.shtml
14. 新京报，《北京将打造 AI 超级个体发展高地》（2026-07-22）. https://www.bjnews.com.cn/detail/1784681199129019.html
15. 东方财富 / 中国证券报，《支付宝发布国内首个智能体商业底座》（2026-08-17）. https://finance.eastmoney.com/a/202608173843263819.html
16. 36 氪，《融资 33 亿，Manus 杀回百亿美元赛道》（2026-10）. https://www.36kr.com/p/4017148924350598
17. GitHub Trending 周榜快照（2026-10-26）†. https://githubtrending.today/weekly/
18. gitdebt 增长榜（2026-10-27）†. https://gitdebt.com/leaderboard
19. Hacker News 首页（2026-10-22）. https://news.ycombinator.com/front?day=2026-10-22
20. Hacker News 首页（2026-10-26）. https://news.ycombinator.com/front?day=2026-10-26
21. NVIDIA OpenShell. https://github.com/NVIDIA/OpenShell ；https://developer.nvidia.com/blog/add-runtime-controls-to-ai-agents-with-nvidia-openshell/
22. MCP Blog, *The 2026-07-28 Specification*. https://blog.modelcontextprotocol.io/posts/2026-07-28/
23. MCP Python SDK Releases（v2.0.0 支持 2026-07-28）. https://github.com/modelcontextprotocol/python-sdk/releases
24. Releasebot, *MCP Release Notes*（TS SDK 的 Skills 扩展，2026-10-23）†. https://releasebot.io/updates/modelcontextprotocol
25. MCP 注册表规模统计†. https://dev.to/amareswer/the-mcp-registry-by-the-numbers-38nc ；https://aiskill.market/blog/9652-servers-inside-the-mcp-registry
26. SkillMD, *Agent Skill Security*（860,246 个公开 skills，2026-09-17）†. https://skillmd.com/agent-skills-security
27. Liu et al., *"Do Not Mention This to the User": Detecting and Understanding Malicious Agent Skills in the Wild*, USENIX Security 2026. https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi
28. *Fabrication After Tool Failure: Tool-Augmented Agents Assert Values Their Tools Did Not Return*, arXiv:2609.14758.
29. *Loud Failures, Quiet Failures: Fault Detection and Recovery in Tool-Using Language Model Agents*, arXiv:2610.10062.
30. *Tool-Calling LLM Agents Under Realistic MCP Faults: Scale Does Not Purchase Fault Tolerance*, arXiv:2610.32555.
31. *RITE: Evaluating End-to-End Resilience to Silent Tool Errors in E-Commerce Agentic Systems*, arXiv:2610.27777.
32. *AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over MCP*, arXiv:2607.11098.
33. *Failure-Transparent Agents: Benchmarking Post-Failure Reporting in Tool-Using Language Models*, arXiv:2609.35732.
34. *Beyond Function Calling: Benchmarking Tool-Using Agents under Tool-Environment Unreliability（ToolBench-X）*, arXiv:2606.25819.
35. *When Tools Fail: Benchmarking Dynamic Replanning and Anomaly Recovery in LLM Agents（ToolMaze）*, arXiv:2606.05806.
36. *Bench2Robust: Scenario-Controlled Recovery for Tool-Using Agents*, arXiv:2608.11977.
37. *Benchmarking the Benchmarks: A Validity Audit of Tool-Calling Evaluation*, arXiv:2607.02577.
38. *ComplexMCP: Evaluation of LLM Agents in Dynamic, Interdependent, and Large-Scale Tool Sandbox*, arXiv:2605.10787.
39. *ToolFailBench: Diagnosing Tool-Use Failures in LLM Agents*, arXiv:2607.04686.
40. *Auditing Automated Evaluation, Error Propagation, and Runtime Mitigation in Tool-Using Language Agents（AgentProp-Bench）*, arXiv:2604.16706.
41. 评测与可观测融资汇总†：Braintrust（https://www.pulse.bot/ai/deals/braintrust-raises-80m-series-b-to-become-ai-observability-layer-6595f521-47a8-4413-bf58-77adeb77d694/）；Langfuse（https://www.callsphere.ai/blog/langfuse-raises-50m-series-b-ai-agent-observability）；Judgment Labs（https://www.pulse.bot/venture-capital/news/judgment-labs-raises-32m-to-build-the-improvement-layer-for-ai-agents-56ba7625-8f17-441d-b34f-d1fbaf260e19）
42. VC Cafe, *Requests for Startups 2026 edition*†. https://www.vccafe.com/requests-for-startups-2026-edition/
43. Let's Data Science, *Microsoft Posts Q3 Beat as Azure Grows 40%*†. https://letsdatascience.com/news/microsoft-posts-q3-beat-as-azure-grows-40-dfbf3c3c
44. Webull（引 CNBC），Anthropic 营收与 IPO 报道†. https://www.webull.ca/news-detail/15422614464930816
45. 竞品与相关项目：Enkrypt AI MCP Gateway（https://www.enkryptai.com/product/mcp-gateway）；mcpproxy-go（https://github.com/smart-mcp-proxy/mcpproxy-go）；Microsoft Agent Governance Toolkit（https://github.com/microsoft/agent-governance-toolkit）；mcp-test-harness（https://github.com/vaquarkhan/mcp-test-harness）；EvalMonkey（https://github.com/corbell-ai/evalmonkey）；mcp-drill（https://pypi.org/project/mcp-drill/）；awesome-agent-runtime-security（https://github.com/bureado/awesome-agent-runtime-security）；Faultline（Devpost，https://devpost.com/software/faultline-64519a）；ToolProof（https://github.com/Moshe-ship/toolproof）。
46. MindStudio, *Grok Bot AI agent fleet*†. https://www.mindstudio.ai/blog/grok-bot-ai-agent-fleet/
47. Fortune, *Profound raises $96 million*（2026-02-24）. https://fortune.com/2026/02/24/exclusive-as-ai-threatens-search-profound-raises-96-million-to-help-brands-stay-visible/
48. Agent Skills 开放标准. https://agentskills.io ；Anthropic, *Equipping agents for the real world with Agent Skills*. https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills
49. Microsoft Learn, *Agent Skills（经 MCP 分发 Skills）*（2026-10-15）. https://learn.microsoft.com/en-us/agent-framework/agents/skills
50. 新华网，OpenClaw 走红与安全担忧（2026-03-13）. https://www.news.cn/world/20260313/47af162930114cac9054ee2fc82ce883/c.html
51. MCP 故障实证研究：arXiv:2606.05339（来自 473 个仓库的 837 条运行时故障讨论）；arXiv:2603.05637（407 个 MCP 相关 issue 的分类）。
52. Hugging Face Daily Papers（2026-10，含 Δτ-Bench、*Naive RAG Is Stronger Than We Thought* 等）. https://huggingface.co/papers
53. Hacker News, *OpenAI and Anthropic cut their LLM prices by up to 80%*（minimaxir.com，见 [20]）。
54. OrangeBot.AI GitHub Trending 日榜（2026-10-27，含 TradingAgents）†. https://orangebot.ai/sources/github-trending
