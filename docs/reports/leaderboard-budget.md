# Leaderboard Model Selection and Budget Estimate (L70 / L70fix2)

- **Task**: L70 榜单模型选定与试跑估价 (L70fix2 Reconciled)
- **Roles**: R8 (Research & Analysis) + R0 (Architect)
- **Dependencies**: E48 (Batch Benchmark Runner), G53 (Guards A/B Control Experiment)
- **Target Audience / Gate**: Human Reviewer (H3 Approval Gate for L71 Official Benchmark Execution)
- **Date**: 2026-11-10
- **Matrix**: `bench/matrix/leaderboard-v1.yaml`
- **Models Registry**: `bench/leaderboard/models.yaml`

---

## 1. Executive Summary & Recommended Budget Tiers

Per task card **L70** and specifications **S16.1** and **S16.2**, this report establishes the definitive model selection for the Skeptic Leaderboard and presents a reconciled empirical budget extrapolation across three operational tiers following the L70fix2 empirical audit.

All estimates are grounded in actual empirical token counts observed during the **G53** benchmark runs (482 episodes under `guards: none` and 482 episodes under `guards: all`, proxied for `recommended`, on `compat/hy3` in `C:\Users\Du200\Projects\skeptic_runs\g53_free\ledger.csv`) and exact episode expansions calculated by `count_matrix_episodes` from `src/skeptic_agent/runner/matrix.py`.

In compliance with project directives, **zero paid API calls or 128api billable requests were executed** during this estimation phase. The $40 allocation for L70 remains unspent ($0.00 actual expenditure).

### Three Budget Tiers Comparison

| Tier | Seeds | Scenarios | Expanded Configs | Total Episodes | Base Extrapolated Cost | Safety Buffer | Recommended Cap (`--max-cost-usd`) | Key Trade-off / Statistical Validity |
|---|---|---|---|---|---|---|---|---|
| **Tier 1: 完整方案 (Full)** | 3 (`[1, 2, 3]`) | 200 (`core-v1`) | 24 | **231,768** | **$2,135.10** | +5.4% | **$2,250.00** | **Full Statistical Power**: 3 seeds enable robust paired bootstrap confidence intervals (B=1000) for SKS/FSR/ICR without overlapping seed artifacts. **Exceeds original S16.2 ceiling ($1,300)**; requires H3 approval to raise ceiling to $2,250. |
| **Tier 2: 节省方案 (Save)** | 2 (`[1, 2]`) | 200 (`core-v1`) | 24 | **154,512** | **$1,423.40** | +6.8% | **$1,520.00** | **Cost-Effective Balance**: Retains 100% scenario coverage (all 200 scenarios across 10 sandboxes) while reducing episode count and cost by **33.3%**. 2 seeds still provide variance estimation. **Exceeds original S16.2 ceiling ($1,300)**; requires H3 approval to raise ceiling to $1,520. |
| **Tier 3: 最低方案 (Min)** | 2 (`[1, 2]`) | 100 (50% sample) | 24 | **77,904** | **$717.67** | +8.7% | **$780.00** | **Budget-Constrained Minimum**: Reduces cost by **66.4%** while preserving all 8 models and 4 framework adapters across 10 scenarios per sandbox with 2 seeds. **Fits within original S16.2 ceiling ($1,300)** without requiring additional budget. |

> [!IMPORTANT]
> **Honest H3 Budget Implication & Decision Gate**:
> Empirical token counts from G53 reveal that single-episode token consumption is significantly higher than the earlier speculative assumption ($T_{in} \approx 2,250, T_{out} \approx 250$). Under empirical consumption ($T_{in} \approx 3,736.21, T_{out} \approx 453.57$), the previous estimates ($1,247.66 / $831.77 / $419.38) severely understated the true cost.
> **Critical Reality**: S16.2's original **$1,300.00** ceiling cannot cover Tier 1 ($2,135.10 base, $2,250.00 cap) or even Tier 2 ($1,423.40 base, $1,520.00 cap) at empirical token rates.
> H3 must make an explicit choice:
> 1. **Option A (Raise Ceiling — Recommended for Research Quality)**: Approve **Tier 1 ($2,250.00)** or **Tier 2 ($1,520.00)**, formally raising the budget ceiling beyond the original $1,300.
> 2. **Option B (Strict Budget Limit)**: If the $1,300 budget ceiling is non-negotiable, H3 must approve **Tier 3 ($780.00 cap)** or accept a further-reduced evaluation matrix.
> 
> *Governance Note*: In accordance with change-control discipline, `bench/matrix/leaderboard-v1.yaml` leaves `max_cost_usd: 1300` unchanged until H3 formally issues written approval for a revised ceiling.

---

## 2. Model Selection (S16.1 Compliance)

The 8 leaderboard models and 1 development model have been registered in `bench/leaderboard/models.yaml`. All models are accessible via OpenRouter and have verified tool-calling capabilities.

### 2.1 Model Registry Overview

| Model ID (`openrouter/slug`) | Display Name | Group (`group`) | Origin (`origin`) | Tier (`tier`) | Price In ($/Mtok) | Price Out ($/Mtok) | Unit Cost ($/ep)* | Selection Rationale & Tool Calling Status |
|---|---|---|---|---|---|---|---|---|
| `openrouter/anthropic/claude-3.5-sonnet` | Claude 3.5 Sonnet | `closed-frontier` | `us` | `leaderboard` | $3.00 | $15.00 | $0.018012 | Anthropic flagship; industry state-of-the-art for coding and tool reasoning; benchmark baseline. |
| `openrouter/openai/gpt-4o` | GPT-4o | `closed-frontier` | `us` | `leaderboard` | $2.50 | $10.00 | $0.013876 | OpenAI flagship omni model; high tool-calling precision and strict JSON-RPC schema compliance. |
| `openrouter/google/gemini-pro-1.5` | Gemini 1.5 Pro | `closed-frontier` | `us` | `leaderboard` | $1.25 | $5.00 | $0.006938 | Google flagship frontier model; 2M token context; verified function calling on OpenRouter. |
| `openrouter/anthropic/claude-3.5-haiku` | Claude 3.5 Haiku | `closed-small` | `us` | `leaderboard` | $0.80 | $4.00 | $0.004803 | Anthropic high-speed compact model; low latency and reliable multi-step tool execution. |
| `openrouter/google/gemini-flash-1.5` | Gemini 1.5 Flash | `closed-small` | `us` | `leaderboard` | $0.075 | $0.30 | $0.000416 | Google lightweight high-throughput model; highly cost-effective native tool calling. |
| `openrouter/deepseek/deepseek-chat` | DeepSeek V3 | `open-weight` | `cn` | `leaderboard` | $0.14 | $0.28 | $0.000650 | DeepSeek open-weight MoE flagship; exceptional open-source agentic performance. |
| `openrouter/qwen/qwen-2.5-72b-instruct` | Qwen 2.5 72B Instruct | `open-weight` | `cn` | `leaderboard` | $0.35 | $0.40 | $0.001489 | Alibaba Qwen 2.5 flagship 72B dense open-weight model; strong Chinese/English tool use. |
| `openrouter/meta-llama/llama-3.3-70b-instruct` | Llama 3.3 70B Instruct | `open-weight` | `us` | `leaderboard` | $0.12 | $0.30 | $0.000584 | Meta open-weight flagship; broad community adoption and verified OpenRouter tools routing. |
| `openrouter/openai/gpt-4o-mini` | GPT-4o mini | `closed-small` | `us` | `dev` | $0.15 | $0.60 | $0.000833 | Default dev-tier model ($0.75/Mtok total $\le \$1.00$ requirement); used for local dev and CI. |

*\*Unit cost assumes weighted average empirical consumption of $T_{in} = 3,736.2123$ tokens and $T_{out} = 453.5733$ tokens per episode, based on the 16-none + 8-recommended configuration mix from the G53 empirical ledger (with recommended proxied by G53 'all'). $\text{unit} = T_{in}/10^6 \times \text{price\_in} + T_{out}/10^6 \times \text{price\_out}$.*

> [!NOTE]
> **Non-Leaderboard Experiment Tier Split**: Existing compatibility models (`compat/deepseek-v4-pro`, `compat/gpt-5.6-terra`, `compat/hy3`) from G53 experiments are retained in `bench/leaderboard/models.yaml` under `tier: experiment`. They represent 128api / WorkBuddy endpoints rather than OpenRouter slugs and are completely isolated from the official S16.1 leaderboard and dev tiers.

### 2.2 Verification Against S16.1 Rules

1. **3 Closed-Frontier Models**: Anthropic (`claude-3.5-sonnet`), OpenAI (`gpt-4o`), and Google (`gemini-pro-1.5`) — each vendor's leading flagship model.
2. **2 Closed-Small Models**: Anthropic (`claude-3.5-haiku`) and Google (`gemini-flash-1.5`) — the latest fast/compact tier models with native tool calling.
3. **3 Open-Weight Models (at least 2 domestic/CN)**:
   - DeepSeek (`deepseek-chat`, origin: `cn`)
   - Alibaba Qwen (`qwen-2.5-72b-instruct`, origin: `cn`)
   - Meta Llama (`llama-3.3-70b-instruct`, origin: `us`)
   - **Result**: Exactly 2 of 3 open-weight models originate from China (`origin: cn`), satisfying the S16.1 rule.
4. **Tool Call Verification**: All 8 models confirmed to support function calling / tools on OpenRouter (`supports_tools: true`).
5. **1 Dev-Tier Model**: Exactly one official S16.1 dev-tier model `openrouter/openai/gpt-4o-mini` is retained as `tier: dev` with total price $0.75/Mtok ($\le \$1.00$/Mtok).
6. **Experiment-Tier Split (Backward Compatibility)**: Existing compatibility endpoints (`compat/deepseek-v4-pro`, `compat/gpt-5.6-terra`, `compat/hy3`) are preserved and isolated into `tier: experiment` (128api / WorkBuddy endpoints, distinct from OpenRouter slugs), preventing interference with the S16.1 leaderboard and dev tiers.

---

## 3. Matrix Configuration & Episode Expansion (S16.2)

The benchmark matrix file `bench/matrix/leaderboard-v1.yaml` adheres to `skeptic.matrix/v1` and expands into 24 distinct configurations.

### 3.1 Matrix Architecture

```yaml
schema: skeptic.matrix/v1
id: leaderboard-v1
suite: core-v1
profiles: [loud-core, silent-core, adversarial-core, cross-source]
seeds: [1, 2, 3]
max_cost_usd: 1300
configs:
  - {agent: "reference:${model}", prompt_variant: plain, guards: none, models: leaderboard}
  - {agent: "reference:${model}", prompt_variant: plain, guards: recommended, models: leaderboard}
  - {agent: "openai-agents:${model}", prompt_variant: plain, guards: none, models: [openrouter/openai/gpt-4o, openrouter/anthropic/claude-3.5-sonnet]}
  - {agent: "langgraph:${model}", prompt_variant: plain, guards: none, models: [openrouter/openai/gpt-4o, openrouter/anthropic/claude-3.5-sonnet]}
  - {agent: "crewai:${model}", prompt_variant: plain, guards: none, models: [openrouter/openai/gpt-4o, openrouter/anthropic/claude-3.5-sonnet]}
  - {agent: "pydantic-ai:${model}", prompt_variant: plain, guards: none, models: [openrouter/openai/gpt-4o, openrouter/anthropic/claude-3.5-sonnet]}
```

### 3.2 Expanded Configurations Breakdown

The 24 expanded configurations consist of:
- **Reference Agent Baseline** (`guards: none`): 8 models $\times$ 1 = 8 configs.
- **Reference Agent Protected** (`guards: recommended`): 8 models $\times$ 1 = 8 configs.
- **Agent Framework Comparisons** (`guards: none`):
  - OpenAI Agents SDK on GPT-4o and Claude 3.5 Sonnet: 2 configs.
  - LangGraph on GPT-4o and Claude 3.5 Sonnet: 2 configs.
  - CrewAI on GPT-4o and Claude 3.5 Sonnet: 2 configs.
  - PydanticAI on GPT-4o and Claude 3.5 Sonnet: 2 configs.
- **Total Configurations**: $8 + 8 + 8 = 24$ configs.

### 3.3 Episode Count per Profile (`core-v1` Suite)

The 200 scenarios in `core-v1` evaluated against the 4 fault profiles yield the following episode counts per seed (verified by `expand()` in `src/skeptic_agent/faults/profiles.py`):

| Profile | Expansion Type | Faults Covered | Applicable Scenarios | Episodes / Seed |
|---|---|---|---|---|
| `loud-core` | `per_fault` | L01, L02, L03, L05, L06, L07 | All 200 (stdio applicable) | 1,000 |
| `silent-core` | `per_fault` | S01–S08, S10 | All 200 (S10 filtered to write tools) | 1,599 |
| `adversarial-core` | `per_fault` | A01, A02, A03 | All 200 (mail sandbox attached) | 600 |
| `cross-source` | `per_fault` | S09 | 20 scenarios with `conflict_pair` | 20 |
| **Total per Seed** | | | | **3,219 episodes** |

Across seeds and scenarios:
- **1 Seed, 200 Scenarios**: 3,219 episodes / config.
- **2 Seeds, 200 Scenarios**: 6,438 episodes / config.
- **3 Seeds, 200 Scenarios**: 9,657 episodes / config.
- **2 Seeds, 100 Scenarios**: 3,246 episodes / config (1,623 episodes / seed).

---

## 4. Empirical Cost Estimation Basis

### 4.1 Token Distribution from G53 Empirical Runs & Reconciliation

The empirical token baseline is established directly from the real G53 free run ledger (`C:\Users\Du200\Projects\skeptic_runs\g53_free\ledger.csv`, on `compat/hy3`):

1. **Unprotected Runs (`guards: none`, run_id `20261103-155316-3e96a4`)**:
   - 482 episodes recorded `tokens_in = 1,685,280`, `tokens_out = 211,034`, with recorded ledger cost of **$1.159186**.
   - Per episode consumption: $T_{in} = 1,685,280 / 482 \approx 3,496.4315$ tokens, $T_{out} = 211,034 / 482 \approx 437.8299$ tokens.
   - Per episode ledger cost: **$0.002405 / episode**.

2. **Protected Runs (`guards: all`, run_id `20261103-162358-6c18bb`)**:
   - 482 episodes recorded `tokens_in = 2,032,003`, `tokens_out = 233,799`, with recorded ledger cost of **$1.366695**.
   - Per episode consumption: $T_{in} = 2,032,003 / 482 \approx 4,215.7739$ tokens, $T_{out} = 233,799 / 482 \approx 485.0602$ tokens.
   - Per episode ledger cost: **$0.002835 / episode**.

3. **Ledger Pricing Fallback & Prior Review FAIL Root Cause**:
   - The ledger USD totals were priced at the runner fallback defaults `DEFAULT_PRICE_IN_PER_MTOK = $0.50` and `DEFAULT_PRICE_OUT_PER_MTOK = $1.50` from `src/skeptic_agent/runner/llm.py`, because `compat/hy3` was not yet registered in `models.yaml` at the time of the G53 run (it is now registered as `tier: experiment` at $0.00).
   - Verification:
     $$1,685,280 \times \frac{\$0.50}{10^6} + 211,034 \times \frac{\$1.50}{10^6} = \$0.842640 + \$0.316551 = \$1.159191 \approx \$1.159186$$
   - The ledger totals were **NOT** priced at $\$0.60\text{ in} / \$2.40\text{ out}$. The earlier draft reported speculative figures of $T_{in} \approx 2,100 / T_{out} \approx 230$ and claimed $\$0.002407$ came from $2,100 / 230$ at $\$0.60 / \$2.40$; in reality, $2,100 \times 0.60/10^6 + 230 \times 2.40/10^6 = \$0.001812$, which was mathematically inconsistent and caused the Copilot review FAIL. Those understated token counts drastically understated the entire benchmark budget.

4. **Matrix Weighted Average (16-none + 8-recommended)**:
   - In `leaderboard-v1`, 16 of the 24 configurations run without guards (`guards: none`) and 8 run with guards (`guards: recommended`).
   - Guard token overhead for `recommended` is proxied by G53 `guards: all`.
   - Weighted average token consumption per episode:
     $$T_{in} = \frac{16 \times 3,496.431535 + 8 \times 4,215.773859}{24} = 3,736.212310\text{ tokens}$$
     $$T_{out} = \frac{16 \times 437.829876 + 8 \times 485.060166}{24} = 453.573306\text{ tokens}$$
   - Unit cost formula for each model:
     $$\text{unit} = \frac{T_{in}}{10^6} \times \text{price\_in} + \frac{T_{out}}{10^6} \times \text{price\_out}$$

### 4.2 Smoke Suite Extrapolation Reference (318 Episodes / Seed)

A single-seed dry run on the 20-scenario `smoke` suite produces **318 episodes / config** (7,632 episodes across 24 configs). The extrapolated smoke cost across all 24 configs is:
- Reference models (`none` + `recommended`, 16 configs; $2 \times 318 = 636$ eps per model): **$29.75**
- Framework adapters (8 configs; $4 \times 318 = 1,272$ eps each for Sonnet and GPT-4o): **$40.56**
- **Total Smoke Matrix Cost**: **$70.31**

> [!NOTE]
> **Budget Disclosure**: The extrapolated smoke cost of **$70.31** exceeds the original $40 L70 card budget. A live paid smoke across all 24 configurations of the smoke suite cannot fit within $40. However, L70 itself spent **$0.00** and made zero paid calls, preserving 100% of the project funds.

---

## 5. Detailed Cost Breakdown by Tier

### 5.1 Tier 1: 完整方案 (Full — 3 Seeds, 200 Scenarios)

- **Total Episodes**: $24 \times 9,657 = \mathbf{231,768\text{ episodes}}$
- **Recommended Cap**: **$2,250.00** (Buffer +5.4% over base $2,135.10; original S16.2 ceiling $1,300 is insufficient)

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) | % of Budget |
|---|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 (2 ref + 4 frameworks) | 57,942 | $0.018012 | $1043.67 | 48.9% |
| GPT-4o | 6 (2 ref + 4 frameworks) | 57,942 | $0.013876 | $804.02 | 37.7% |
| Gemini 1.5 Pro | 2 (ref none + ref rec) | 19,314 | $0.006938 | $134.00 | 6.3% |
| Claude 3.5 Haiku | 2 (ref none + ref rec) | 19,314 | $0.004803 | $92.77 | 4.3% |
| Qwen 2.5 72B Instruct | 2 (ref none + ref rec) | 19,314 | $0.001489 | $28.76 | 1.3% |
| DeepSeek V3 | 2 (ref none + ref rec) | 19,314 | $0.000650 | $12.56 | 0.6% |
| Llama 3.3 70B Instruct | 2 (ref none + ref rec) | 19,314 | $0.000584 | $11.29 | 0.5% |
| Gemini 1.5 Flash | 2 (ref none + ref rec) | 19,314 | $0.000416 | $8.04 | 0.4% |
| **Total Base** | **24** | **231,768** | — | **$2135.10** | **100.0%** |
| **With Safety Buffer (+5.4%)** | | | | **$2,250.00** | |

### 5.2 Tier 2: 节省方案 (Save — 2 Seeds, 200 Scenarios)

- **Total Episodes**: $24 \times 6,438 = \mathbf{154,512\text{ episodes}}$
- **Recommended Cap**: **$1,520.00** (Buffer +6.8% over base $1,423.40; exceeds original S16.2 ceiling $1,300)

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) |
|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 | 38,628 | $0.018012 | $695.78 |
| GPT-4o | 6 | 38,628 | $0.013876 | $536.01 |
| Gemini 1.5 Pro | 2 | 12,876 | $0.006938 | $89.34 |
| Claude 3.5 Haiku | 2 | 12,876 | $0.004803 | $61.85 |
| Qwen 2.5 72B Instruct | 2 | 12,876 | $0.001489 | $19.17 |
| DeepSeek V3 | 2 | 12,876 | $0.000650 | $8.37 |
| Llama 3.3 70B Instruct | 2 | 12,876 | $0.000584 | $7.52 |
| Gemini 1.5 Flash | 2 | 12,876 | $0.000416 | $5.36 |
| **Total Base** | **24** | **154,512** | — | **$1423.40** |
| **With Safety Buffer (+6.8%)** | | | | **$1,520.00** |

### 5.3 Tier 3: 最低方案 (Min — 2 Seeds, 100 Scenarios)

- **Total Episodes**: $24 \times 3,246 = \mathbf{77,904\text{ episodes}}$
- **Recommended Cap**: **$780.00** (Buffer +8.7% over base $717.67; fits within original S16.2 ceiling $1,300)

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) |
|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 | 19,476 | $0.018012 | $350.81 |
| GPT-4o | 6 | 19,476 | $0.013876 | $270.25 |
| Gemini 1.5 Pro | 2 | 6,492 | $0.006938 | $45.04 |
| Claude 3.5 Haiku | 2 | 6,492 | $0.004803 | $31.18 |
| Qwen 2.5 72B Instruct | 2 | 6,492 | $0.001489 | $9.67 |
| DeepSeek V3 | 2 | 6,492 | $0.000650 | $4.22 |
| Llama 3.3 70B Instruct | 2 | 6,492 | $0.000584 | $3.79 |
| Gemini 1.5 Flash | 2 | 6,492 | $0.000416 | $2.70 |
| **Total Base** | **24** | **77,904** | — | **$717.67** |
| **With Safety Buffer (+8.7%)** | | | | **$780.00** |

---

## 6. Budget Drivers & Cost Sensitivity Analysis

1. **Frontier Model Dominance**:
   - The two frontier models (Claude 3.5 Sonnet and GPT-4o) account for **86.5%** ($1,847.69 of $2,135.10) of the total budget in Tier 1.
   - This asymmetry arises because Sonnet and GPT-4o serve dual roles: evaluating model capability (reference agent) AND evaluating framework robustness (4 adapters $\times$ 2 models).
2. **Open-Weight & Small Model Economy**:
   - The remaining 6 models (Gemini Pro, Haiku, Flash, DeepSeek, Qwen, Llama) combined cost only **$287.41** (13.5% of total budget) for 115,884 episodes in Tier 1.
   - DeepSeek V3, Qwen 2.5, and Llama 3.3 provide exceptional cost efficiency ($0.12–$0.35/Mtok in), demonstrating that expanding open-weight evaluations incurs minimal budget impact.
3. **S16.2 Ceiling Inadequacy & Honest Dilemma**:
   - The original S16.2 specification postulated a ceiling of `max_cost_usd: 1300`. This assumed speculative token averages of $T_{in} \approx 2,250, T_{out} \approx 250$ (yielding earlier figures of $1,247.66 / $831.77 / $419.38).
   - Under real empirical token rates ($T_{in} \approx 3,736.21, T_{out} \approx 453.57$), the true base cost of Tier 1 is $2,135.10 and Tier 2 is $1,423.40.
   - Consequently, the S16.2 $1,300 ceiling is **insufficient** to cover Tier 1 or even Tier 2. H3 must either formally raise the ceiling ($2,250 for Tier 1, $1,520 for Tier 2) or choose Tier 3 ($780) / a further-reduced matrix to stay within $1,300.
4. **Safety Buffer Justification**:
   - A modest 5–8% safety margin is incorporated into each tier (Tier 1: $2,250 / +5.4%; Tier 2: $1,520 / +6.8%; Tier 3: $780 / +8.7%) to accommodate:
     - Scenarios triggering multi-turn retry loops under L01/L05.
     - Prompt inflation in adversarial injection tasks (A01–A03).
     - Token count variance across different natural language tokenizers.

---

## 7. Compliance & Integrity Disclosure

- **Zero Paid Network Calls**: As instructed, no paid API tokens or 128api calls were made during L70 / L70fix2. All numbers are derived from static profile expansion on actual scenarios and empirical G53 token distributions.
- **Dry-run Validated**: The full matrix `leaderboard-v1` was verified with `skeptic bench run --matrix bench/matrix/leaderboard-v1.yaml --dry-run` and `--count`, matching the 231,768 episode calculation exactly.
- **Reproducibility**: All calculations are reproducible via standard CLI commands and unit tests.

---

## 8. H3 Approval Gate Sign-off Request

R0 hereby submits this document to the Human Project Sponsor for **H3 Approval**:

```text
Action Required: Human reviewer to approve budget decision in GitHub Issue:
  - "批准 完整" (Tier 1, Cap $2,250.00 — requires raising S16.2 $1,300 ceiling)
  - "批准 节省" (Tier 2, Cap $1,520.00 — requires raising S16.2 $1,300 ceiling)
  - "批准 最低" (Tier 3, Cap $780.00 — fits within original S16.2 $1,300 ceiling)

Note: S16.2's original $1,300 ceiling is insufficient to cover Tier 1 or even Tier 2 at empirical token rates. If H3 cannot raise the ceiling beyond $1,300, H3 should approve Tier 3 ($780.00 cap) or request a further-reduced matrix.
bench/matrix/leaderboard-v1.yaml retains max_cost_usd: 1300 until H3 formally approves the new cap.

Upon receipt of approval, Role R4 will proceed with Task L71:
  skeptic bench run --matrix bench/matrix/leaderboard-v1.yaml --max-cost-usd <批准额度>
```

---

## 9. Interim Update: Reduced-Scope Free Run (L71)

On 2026-11-10 21:16 Europe/London, Human Sponsor (H3) approved a reduced-scope, $0 contrast experiment (L71) rather than the official S16.2 leaderboard execution. This interim experiment evaluates free-tier endpoints (`compat/our-free-model/deepseek-ai/deepseek-v4.1-flash` and `compat/hy3`) on a subset of scenarios (`core-v1-l71-reduced` with 56 scenarios and `core-v1-l71-hy3` with 10 scenarios) under `silent-core` and seed 1 with safety cap `max_cost_usd: 5.0`.

This interim run does **not** fulfill or replace the official S16.2 leaderboard execution (Tier 1/2/3). See [leaderboard-l71-reduced.md](leaderboard-l71-reduced.md) for full methodology, suite selection rules, and episode counts.
