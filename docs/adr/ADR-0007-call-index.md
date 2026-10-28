# ADR-0007: call_index 在故障前置钩子之前计数

- 状态：采纳
- 日期：2026-10-28
- 提出者：F20　裁决者：R1

## 背景

S4.3 把 `call_index` 定义为：在同一个 episode 内，某个工具名被转发到上游的第 n 次尝试（从 1 开始），Guard 发起的重试也计入；故障调度（S7）以它为准。S6 的 `when.call_index` 表示“第几次尝试时触发”。

P12 的实现只在 `tools/call` 走完故障前置阶段、确定要 `Forward` 之后才自增 `call_index`（`Pipeline.on_c2s`）。由此产生三个问题：

1. S4.4 中 c2s 第 ④ 步的故障前置钩子（L04、L06、L07、S05、S10）运行时看不到本次尝试的 `call_index`，S7 的 `when.call_index` 对它们没有意义。
2. S10 从不转发写请求，永远走不到自增的那一行，因此同一个工具的写请求 `call_index` 永远是 0，`when.call_index: 2` 之类永远不触发。
3. 前置故障直接回复了客户端时，这次尝试既不在 `call_counts` 里，也无法在后置钩子或 cassette 记录里找到一致编号。

## 选项

### A. 维持现状（转发后才计数）

优点：不改 P12 代码；`call_index` 严格等于“转发到上游的次数”。
缺点：前置故障看不到 `call_index`，S10 永不推进，S7.4 展开出的 `when.call_index` 在 L04/L06/L07/S05/S10 上失效；与 S6 “第几次尝试时触发”的语义冲突。

### B. 到达故障前置阶段时计数（采用）

优点：一次 `tools/call` 尝试在进入第 ④ 步时就有编号；前置钩子、后置钩子、cassette 记录读到同一个值；S10 这类从不转发的故障也能按次数调度。被 G06/G07 拦截的尝试不进第 ④ 步，因此不计；G05 重试回到第 ④ 步，自然计入，与 S4.3“Guard 发起的重试也计入”一致。
缺点：`call_index` 不再字面等于“被转发到上游的次数”，而是“进入故障前置阶段的尝试次数”；需要改 P12 的 `Pipeline` 和 `EpisodeContext`，并同步更新对应测试。

## 决定

采纳 B。

- `tools/call` 尝试在到达故障前置阶段时计数，也就是在 G06/G07 放行之后、前置钩子运行之前；具体位置是管线按 S4.4 顺序调用故障阶段之前。
- 编号存放两份、值相同：`EpisodeContext.current_call_index[tool]`（故障阶段在钩子里读取）与对应 `PendingCall.attempt`（后置钩子通过待处理请求读取）。
- s2c 响应进入故障后置阶段时，匹配的 `PendingCall` 仍留在 `ctx.pending`；后置钩子把它的 `attempt` 写回 `current_call_index[tool]`，因此和前置钩子读到同一个编号。整条 s2c 链返回前再删除该 pending。
- 被 G06/G07 拦截的尝试不计入；Guard（G05）发起的重试从第 ④ 步重新进入，照常计数。
- 故障阶段的默认行为由管线负责计数；需要自行决定计数时机的阶段可以覆盖 `FaultStage.counts_attempts()` 返回 `True`，由该阶段自行调用 `next_call_index`。

## 影响

- 代码：`src/skeptic_agent/proxy/pipeline.py`（`FaultStage.counts_attempts`、`_run` 的 `before_fault` 回调、`Pipeline.on_c2s`）；`src/skeptic_agent/proxy/context.py`（新增 `current_call_index`）。
- 测试：`tests/unit/test_pipeline.py` 中 `call_index` 仍为 1、2、3；新增“故障阶段直接回复也算一次尝试”和“故障阶段能看到本次编号”两条用例。
- 规格：S4.3 的“转发到上游的第 n 次尝试”按本 ADR 解释为“进入故障前置阶段的第 n 次尝试”；S6 的 `when.call_index` 对全部 20 种故障生效。计划书正文不改，以此 ADR 为准。
- 文档：cassette 中 `fault.call_index` 取 `PendingCall.attempt`，与钩子看到的值一致。
