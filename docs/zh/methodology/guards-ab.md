# 防护对照实验与 `recommended` 预设（Guards A/B）

本文记录 Skeptic 任务 **G53**（防护对照实验与 `recommended` 预设）的方法、执行过程和实测结果。

目的是在受控的合成故障下评估八个防护（G01–G08），看哪些防护带来可靠的提升，并确定 `recommended` 预设的组成。

## 1. 实验设计

### 1.1 场景集

为了在预算（不超过 60 美元）内保留区分度，计划用 Python 的伪随机数生成器、种子 **0**，从 200 个场景的 `core-v1` 套件里抽 **60** 个场景：

```python
import random
from skeptic_agent.scenario.suites import load_suite

suite = load_suite("core-v1")
rng = random.Random(0)
sampled_scenarios = rng.sample(suite.scenarios, 60)
```

完整的 60 场景套件在 `bench/suites/guards-ab.yaml`（别名 `bench/suites/core-v1-guards-ab.yaml`）。它覆盖 10 个 MCP 沙箱（`sb_calendar`、`sb_crm`、`sb_docs`、`sb_files`、`sb_fx`、`sb_mail`、`sb_orders`、`sb_sqlshop`、`sb_stocks`、`sb_weather`），包含读、写、多跳和边界场景。

#### 已执行的免费模型缩减集

零费用约束下，按确定顺序取 `guards-ab` 的前 30 个场景，得到缩减套件：

- 套件：`bench/suites/guards-ab-free.yaml`（`id: guards-ab-free`）
- 矩阵：`bench/matrix/guards-ab-free.yaml`（`id: guards-ab-free`）

### 1.2 故障画像

每个场景在 S7.2 的三个标准画像下、按 `per_fault` 展开：

1. **`silent-core`**：9 种静默数据故障（S01 空响应、S02 截断、S03 过期日期、S04 数值污染、S05 错误实体、S06 字段遮蔽、S07 格式损坏、S08 单位对调、S10 幻影写入）。
2. **`loud-core`**：6 种显式故障（L01 超时、L02 JSON-RPC -32603、L03 工具错误、L05 429 限流、L06 工具缺失、L07 schema 漂移）。
3. **`adversarial-core`**：3 种对抗故障（A01 工具输出注入、A02 工具描述投毒、A03 延迟 rug pull）。

静态适用性过滤之后，每个配置的回合数：

- **完整 60 场景**（`bench/matrix/guards-ab.yaml`）：
  - `silent-core`：每个种子 481 回合
  - `loud-core`：每个种子 300 回合
  - `adversarial-core`：每个种子 180 回合
  - 每个配置、每个种子合计 961 回合
- **缩减的 30 场景**（`bench/matrix/guards-ab-free.yaml`）：
  - `silent-core`：每个种子 241 回合
  - `loud-core`：每个种子 151 回合
  - `adversarial-core`：每个种子 90 回合
  - 每个配置、每个种子合计 **482 回合**

### 1.3 防护配置与消融

为了分开看每个防护的贡献，评测 **10** 组配置：

1. **基线（`none`）**：不启用防护（`guards: none`）。
2. **全开（`all`）**：八个防护都开（`guards: all`）。
3. **去掉 G01（`evidence_contract`）**：`[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
4. **去掉 G02（`schema_guard`）**：`[evidence_contract, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
5. **去掉 G03（`staleness_guard`）**：`[evidence_contract, schema_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
6. **去掉 G04（`emptiness_guard`）**：`[evidence_contract, schema_guard, staleness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
7. **去掉 G05（`retry_guard`）**：`[evidence_contract, schema_guard, staleness_guard, emptiness_guard, loop_breaker, injection_shield, drift_lock]`
8. **去掉 G06（`loop_breaker`）**：`[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, injection_shield, drift_lock]`
9. **去掉 G07（`injection_shield`）**：`[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, drift_lock]`
10. **去掉 G08（`drift_lock`）**：`[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield]`

### 1.4 模型与执行范围

原计划用参考 ReAct 智能体（`reference:${model}`）跑两个模型：

- **Dev 档**：`compat/deepseek-v4-pro`
- **Mid 档**：`compat/gpt-5.6-terra`

2 个模型 × 10 组防护 × 961 回合 = **19,220 回合**。

#### 实际执行范围与单模型缺口

上游 API 的额度限制下，实测改用免费端点：

- **模型**：`compat/hy3`（价格 0 美元，dev 档）
- **矩阵**：`bench/matrix/guards-ab-free.yaml`（1 个模型 × 10 组配置 × 482 回合）
- **实际回合数**：**4,820**（从 19,220 缩到 4,820）
- **单模型缺口**：下面的结果只来自 `compat/hy3`。前沿模型和中档模型的评测留待以后有预算时再跑。

## 2. `recommended` 的入选规则

消融里去掉某个防护之后，若出现可测量的变差，该防护可以进入生产用的 `recommended`：

1. **SKS 下降**：去掉它之后 SKS 下降不少于 1.0 分。
2. **FSR 上升**：去掉它之后谎报成功率上升不少于 2.0 个百分点。

### 验收门

最终的 `recommended` 相对 `none` 应当降低谎报成功率（FSR），并由互不重叠的 95% bootstrap 置信区间确认（B = 1000，按场景整群重抽样）。

若置信区间重叠，或没有防护达到门槛，报告必须写下这个结果，并保留暂定默认值：

`[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`（G02–G08，不含 G01）。

## 3. 怎么跑

### 3.1 跑之前看规模（dry-run / 计数）

不发起网络或模型调用，只检查矩阵并打印回合数：

```bash
# Full matrix (19,220 episodes)
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --dry-run
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --count

# Free-model reduced matrix (4,820 episodes)
uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --dry-run
uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --count
```

### 3.2 执行矩阵

```bash
uv run skeptic bench run \
  --matrix bench/matrix/guards-ab-free.yaml \
  --concurrency 4 \
  --ledger bench/ledger.csv \
  --out runs/guards-ab-free
```

### 3.3 比较两组配置

用成对 bootstrap 置信区间比较任意两次运行：

```bash
uv run skeptic compare runs/guards-ab-free/<none_run_id> runs/guards-ab-free/<all_run_id>
```

## 4. 实测结果（`compat/hy3`）

10 组配置在 `compat/hy3` 上共 4,820 回合。下面是点估计和 bootstrap 95% 置信区间（B = 1000）。

### 4.1 各配置的汇总

| 配置 | 模型 | SKS（95% CI） | FSR（95% CI） | RR | ICR | 费用（美元） | Run ID |
|---|---|---|---|---|---|---|---|
| `none`（基线） | `compat/hy3` | 93.19（89.71–96.00） | 8.54%（3.14%–15.58%） | 0.0000 | 0.0000 | $1.16 | `20261103-155316-3e96a4` |
| `all`（全开） | `compat/hy3` | 92.68（88.87–95.88） | 7.29%（1.88%–14.53%） | 0.0000 | 0.0000 | $1.37 | `20261103-162358-6c18bb` |
| 去掉 G01（`evidence_contract`） | `compat/hy3` | 92.19（88.23–95.62） | 8.56%（3.09%–15.87%） | 0.0000 | 0.0000 | $1.38 | `20261103-165643-d4399c` |
| 去掉 G02（`schema_guard`） | `compat/hy3` | 92.64（88.57–96.10） | 7.31%（1.45%–15.16%） | 0.0000 | 0.0000 | $1.34 | `20261103-172835-b3135c` |
| 去掉 G03（`staleness_guard`） | `compat/hy3` | 93.17（89.27–96.43） | 6.89%（1.46%–14.05%） | 0.0000 | 0.0000 | $1.34 | `20261103-180108-b1c518` |
| 去掉 G04（`emptiness_guard`） | `compat/hy3` | 93.43（89.78–96.48） | 6.88%（1.67%–13.60%） | 0.0000 | 0.0000 | $1.27 | `20261103-183234-5606cf` |
| 去掉 G05（`retry_guard`） | `compat/hy3` | 93.20（89.04–96.52） | 7.52%（1.66%–15.52%） | 0.0000 | 0.0000 | $1.41 | `20261103-190521-3a13ec` |
| 去掉 G06（`loop_breaker`） | `compat/hy3` | 93.78（90.35–96.56） | 6.67%（2.06%–12.90%） | 0.0000 | 0.0000 | $1.29 | `20261103-195059-0efa70` |
| 去掉 G07（`injection_shield`） | `compat/hy3` | 92.92（88.92–96.34） | 6.88%（1.04%–14.43%） | 0.0000 | 0.0000 | $1.36 | `20261103-204210-c5587d` |
| 去掉 G08（`drift_lock`） | `compat/hy3` | 93.22（89.19–96.48） | 6.88%（1.24%–14.14%） | 0.0000 | 0.0000 | $1.36 | `20261103-211533-97d29f` |

### 4.2 消融差

差值相对 `all`（全开：SKS = 92.68，FSR = 7.29%）：去掉该防护后的 SKS 减去全开 SKS，去掉该防护后的 FSR 减去全开 FSR。

| 去掉的防护 | 名称 | SKS | SKS 差 | FSR | FSR 差 | 达到入选规则（SKS 差 ≤ −1.0，或 FSR 差 ≥ +2.0 个百分点） |
|---|---|---|---|---|---|---|
| G01 | `evidence_contract` | 92.19 | −0.49 | 8.56% | +1.27 个百分点 | 否（最接近；FSR 差 +1.27 个百分点，未到 +2.0） |
| G02 | `schema_guard` | 92.64 | −0.04 | 7.31% | +0.02 个百分点 | 否 |
| G03 | `staleness_guard` | 93.17 | +0.49 | 6.89% | −0.40 个百分点 | 否 |
| G04 | `emptiness_guard` | 93.43 | +0.75 | 6.88% | −0.41 个百分点 | 否 |
| G05 | `retry_guard` | 93.20 | +0.52 | 7.52% | +0.23 个百分点 | 否 |
| G06 | `loop_breaker` | 93.78 | +1.10 | 6.67% | −0.62 个百分点 | 否 |
| G07 | `injection_shield` | 92.92 | +0.24 | 6.88% | −0.41 个百分点 | 否 |
| G08 | `drift_lock` | 93.22 | +0.54 | 6.88% | −0.41 个百分点 | 否 |

### 4.3 主要结果

1. **置信区间大范围重叠**：
   - 基线 `none` 的 SKS = 93.19（CI 89.71–96.00），FSR = 8.54%（CI 3.14%–15.58%）。
   - 全开 `all` 的 SKS = 92.68（CI 88.87–95.88），FSR = 7.29%（CI 1.88%–14.53%）。
   - 全部消融的 SKS 落在 92.19 到 93.78，FSR 落在 6.67% 到 8.56%。
   - 每一条 95% bootstrap 置信区间都与其他条重叠。SKS 的重叠几乎盖住 [88, 96]，FSR 的重叠几乎盖住 [1%, 16%]。各配置之间没有统计上分开的差距。

2. **门槛规则**：
   - **没有防护达到入选门槛**（SKS 下降不少于 1.0，或 FSR 上升不少于 2.0 个百分点）。
   - 最接近的是 **G01（`evidence_contract`）**。去掉它之后 FSR 从 7.29% 升到 8.56%（+1.27 个百分点），SKS 从 92.68 降到 92.19（−0.49）。这低于 +2.0 个百分点的门槛，置信区间也大幅重叠（8.56% [3.09%, 15.87%] 对 7.29% [1.88%, 14.53%]）。G01 还会改写工具输出的文本，这是它起初被排除在暂定预设之外的原因。
   - 其余防护（G02–G08）的消融差落在 FSR ±0.5 个百分点和 SKS ±1.1 以内，处在样本波动范围内。

3. **局限（规模缩小，且只有一个模型）**：
   - **语料缩小**：实际是 30 个场景、4,820 回合。计划是 60 个场景 × 961 回合 × 2 个模型 = 19,220 回合。
   - **单模型**：只评了 `compat/hy3`。不同的模型结构、指令遵循或推理深度，可能和防护的相互作用不一样。

### 4.4 `recommended` 的最终组成

按本节第 2 部分的规则：置信区间重叠，或没有防护达到门槛时，保留暂定默认值 `[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`（G02–G08，不含 G01）。

没有防护满足数量门槛，置信区间又大范围重叠，因此 `recommended` **仍是暂定预设**：

```python
# src/skeptic_agent/guards/presets.py
PRESETS["recommended"] = [
    "schema_guard",  # G02
    "staleness_guard",  # G03
    "emptiness_guard",  # G04
    "retry_guard",  # G05
    "loop_breaker",  # G06
    "injection_shield",  # G07
    "drift_lock",  # G08
]
```

`src/skeptic_agent/guards/presets.py` 没有因为这次实验而改动。要对 `recommended` 做最终标定，需要在多个前沿模型上跑完计划中的 19,220 回合。
