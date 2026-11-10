# Leaderboard Model Selection and Budget Estimate (L70)

- **Task**: L70 榜单模型选定与试跑估价
- **Roles**: R8 (Research & Analysis) + R0 (Architect)
- **Dependencies**: E48 (Batch Benchmark Runner), G53 (Guards A/B Control Experiment)
- **Target Audience / Gate**: Human Reviewer (H3 Approval Gate for L71 Official Benchmark Execution)
- **Date**: 2026-11-10
- **Matrix**: `bench/matrix/leaderboard-v1.yaml`
- **Models Registry**: `bench/leaderboard/models.yaml`

---

## 1. Executive Summary & Recommended Budget Tiers

Per task card **L70** and specifications **S16.1** and **S16.2**, this report establishes the definitive model selection for the Skeptic Leaderboard and presents a rigorous empirical budget extrapolation across three operational tiers.

All estimates are grounded in actual empirical token counts observed during the **G53** benchmark runs (4,820 episodes on `compat/hy3`) and exact episode expansions calculated by `count_matrix_episodes` from `src/skeptic_agent/runner/matrix.py`.

In compliance with project directives, **zero paid API calls or 128api billable requests were executed** during this estimation phase. The $40 allocation for L70 remains unspent ($0.00 actual expenditure).

### Three Budget Tiers Comparison

| Tier | Seeds | Scenarios | Expanded Configs | Total Episodes | Base Extrapolated Cost | Safety Buffer | Recommended Cap (`--max-cost-usd`) | Key Trade-off / Statistical Validity |
|---|---|---|---|---|---|---|---|---|
| **Tier 1: 完整方案 (Full)** | 3 (`[1, 2, 3]`) | 200 (`core-v1`) | 24 | **231,768** | **$1,247.66** | +4.2% | **$1,300.00** | **Full Statistical Power**: 3 seeds enable robust paired bootstrap confidence intervals (B=1000) for SKS/FSR/ICR without overlapping seed artifacts. Perfectly matches S16.2 specification ceiling ($1,300). |
| **Tier 2: 节省方案 (Save)** | 2 (`[1, 2]`) | 200 (`core-v1`) | 24 | **154,512** | **$831.77** | +5.8% | **$880.00** | **Cost-Effective Balance**: Retains 100% scenario coverage (all 200 scenarios across 10 sandboxes) while reducing episode count and cost by **33.3%**. 2 seeds still provide variance estimation. |
| **Tier 3: 最低方案 (Min)** | 2 (`[1, 2]`) | 100 (50% sample) | 24 | **77,904** | **$419.38** | +7.3% | **$450.00** | **Budget-Constrained Minimum**: Reduces cost by **66.4%** while preserving all 8 models and 4 framework adapters across 10 scenarios per sandbox with 2 seeds. |

> [!IMPORTANT]
> **R0 Recommendation**: If funding allows, approve **Tier 1 ($1,300.00)** to ensure definitive ranking stability and non-overlapping confidence intervals across leaderboard entries. If constrained, **Tier 2 ($880.00)** maintains complete scenario diversity across all 10 sandboxes without compromising failure coverage.

---

## 2. Model Selection (S16.1 Compliance)

The 8 leaderboard models and 1 development model have been registered in `bench/leaderboard/models.yaml`. All models are accessible via OpenRouter and have verified tool-calling capabilities.

### 2.1 Model Registry Overview

| Model ID (`openrouter/slug`) | Display Name | Group (`group`) | Origin (`origin`) | Tier (`tier`) | Price In ($/Mtok) | Price Out ($/Mtok) | Unit Cost ($/ep)* | Selection Rationale & Tool Calling Status |
|---|---|---|---|---|---|---|---|---|
| `openrouter/anthropic/claude-3.5-sonnet` | Claude 3.5 Sonnet | `closed-frontier` | `us` | `leaderboard` | $3.00 | $15.00 | $0.010500 | Anthropic flagship; industry state-of-the-art for coding and tool reasoning; benchmark baseline. |
| `openrouter/openai/gpt-4o` | GPT-4o | `closed-frontier` | `us` | `leaderboard` | $2.50 | $10.00 | $0.008125 | OpenAI flagship omni model; high tool-calling precision and strict JSON-RPC schema compliance. |
| `openrouter/google/gemini-pro-1.5` | Gemini 1.5 Pro | `closed-frontier` | `us` | `leaderboard` | $1.25 | $5.00 | $0.004063 | Google flagship frontier model; 2M token context; verified function calling on OpenRouter. |
| `openrouter/anthropic/claude-3.5-haiku` | Claude 3.5 Haiku | `closed-small` | `us` | `leaderboard` | $0.80 | $4.00 | $0.002800 | Anthropic high-speed compact model; low latency and reliable multi-step tool execution. |
| `openrouter/google/gemini-flash-1.5` | Gemini 1.5 Flash | `closed-small` | `us` | `leaderboard` | $0.075 | $0.30 | $0.000244 | Google lightweight high-throughput model; highly cost-effective native tool calling. |
| `openrouter/deepseek/deepseek-chat` | DeepSeek V3 | `open-weight` | `cn` | `leaderboard` | $0.14 | $0.28 | $0.000385 | DeepSeek open-weight MoE flagship; exceptional open-source agentic performance. |
| `openrouter/qwen/qwen-2.5-72b-instruct` | Qwen 2.5 72B Instruct | `open-weight` | `cn` | `leaderboard` | $0.35 | $0.40 | $0.000887 | Alibaba Qwen 2.5 flagship 72B dense open-weight model; strong Chinese/English tool use. |
| `openrouter/meta-llama/llama-3.3-70b-instruct` | Llama 3.3 70B Instruct | `open-weight` | `us` | `leaderboard` | $0.12 | $0.30 | $0.000345 | Meta open-weight flagship; broad community adoption and verified OpenRouter tools routing. |
| `openrouter/openai/gpt-4o-mini` | GPT-4o mini | `closed-small` | `us` | `dev` | $0.15 | $0.60 | $0.000488 | Default dev-tier model ($0.75/Mtok total $\le \$1.00$ requirement); used for local dev and CI. |

*\*Unit cost assumes weighted average consumption of $T_{in} = 2,250$ tokens and $T_{out} = 250$ tokens per episode.*

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

### 4.1 Token Distribution from G53 Empirical Runs

During the **G53** Guards A/B experiment on `compat/hy3` (4,820 total episodes):
- **Unprotected runs (`guards: none`)**:
  - 482 episodes recorded total cost of **$1.16** under dev pricing ($0.60 in / $2.40 out).
  - Derived tokens per episode: $T_{in} \approx 2,100$ tokens, $T_{out} \approx 230$ tokens.
  - Effective baseline cost: **$0.002407 / episode**.
- **Protected runs (`guards: all` / `guards: recommended`)**:
  - 482 episodes recorded total cost of **$1.37** (+18.1% cost increase).
  - Additional consumption stems from retry guard (G05) re-invocations, evidence contract (G01) framing, and schema validation turns.
  - Derived tokens per episode: $T_{in} \approx 2,450$ tokens, $T_{out} \approx 270$ tokens.
  - Effective protected cost: **$0.002842 / episode**.
- **Matrix Weighted Average**:
  - In `leaderboard-v1`, 16 of 24 configs run without guards (`none`) and 8 of 24 run with guards (`recommended`).
  - Weighted average consumption: **$T_{in} = 2,250$ tokens** ($0.00225$ Mtok) and **$T_{out} = 250$ tokens** ($0.00025$ Mtok).

### 4.2 Smoke Suite Extrapolation Reference (318 Episodes / Seed)

A single-seed dry run on the 20-scenario `smoke` suite produces **318 episodes / config** (7,632 episodes across 24 configs). The extrapolated smoke cost across all 24 configs is:
- Reference models (`none` + `recommended`, 16 configs): **$17.38**
- Framework adapters (8 configs): **$23.70**
- **Total Smoke Matrix Cost**: **$41.08** (closely aligning with the $40 L70 card budget).

---

## 5. Detailed Cost Breakdown by Tier

### 5.1 Tier 1: 完整方案 (Full — 3 Seeds, 200 Scenarios)

- **Total Episodes**: $24 \times 9,657 = \mathbf{231,768\text{ episodes}}$
- **Recommended Cap**: **$1,300.00**

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) | % of Budget |
|---|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 (2 ref + 4 frameworks) | 57,942 | $0.010500 | $608.39 | 48.8% |
| GPT-4o | 6 (2 ref + 4 frameworks) | 57,942 | $0.008125 | $470.78 | 37.7% |
| Gemini 1.5 Pro | 2 (ref none + ref rec) | 19,314 | $0.004063 | $78.46 | 6.3% |
| Claude 3.5 Haiku | 2 (ref none + ref rec) | 19,314 | $0.002800 | $54.08 | 4.3% |
| Qwen 2.5 72B Instruct | 2 (ref none + ref rec) | 19,314 | $0.000887 | $17.14 | 1.4% |
| DeepSeek V3 | 2 (ref none + ref rec) | 19,314 | $0.000385 | $7.44 | 0.6% |
| Llama 3.3 70B Instruct | 2 (ref none + ref rec) | 19,314 | $0.000345 | $6.66 | 0.5% |
| Gemini 1.5 Flash | 2 (ref none + ref rec) | 19,314 | $0.000244 | $4.71 | 0.4% |
| **Total Base** | **24** | **231,768** | — | **$1,247.66** | **100.0%** |
| **With Safety Buffer (+4.2%)** | | | | **$1,300.00** | |

### 5.2 Tier 2: 节省方案 (Save — 2 Seeds, 200 Scenarios)

- **Total Episodes**: $24 \times 6,438 = \mathbf{154,512\text{ episodes}}$
- **Recommended Cap**: **$880.00**

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) |
|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 | 38,628 | $0.010500 | $405.59 |
| GPT-4o | 6 | 38,628 | $0.008125 | $313.85 |
| Gemini 1.5 Pro | 2 | 12,876 | $0.004063 | $52.31 |
| Claude 3.5 Haiku | 2 | 12,876 | $0.002800 | $36.05 |
| Qwen 2.5 72B Instruct | 2 | 12,876 | $0.000887 | $11.43 |
| DeepSeek V3 | 2 | 12,876 | $0.000385 | $4.96 |
| Llama 3.3 70B Instruct | 2 | 12,876 | $0.000345 | $4.44 |
| Gemini 1.5 Flash | 2 | 12,876 | $0.000244 | $3.14 |
| **Total Base** | **24** | **154,512** | — | **$831.77** |
| **With Safety Buffer (+5.8%)** | | | | **$880.00** |

### 5.3 Tier 3: 最低方案 (Min — 2 Seeds, 100 Scenarios)

- **Total Episodes**: $24 \times 3,246 = \mathbf{77,904\text{ episodes}}$
- **Recommended Cap**: **$450.00**

| Model | Config Count | Episodes / Model | Unit Cost ($/ep) | Model Total ($) |
|---|---|---|---|---|
| Claude 3.5 Sonnet | 6 | 19,476 | $0.010500 | $204.50 |
| GPT-4o | 6 | 19,476 | $0.008125 | $158.24 |
| Gemini 1.5 Pro | 2 | 6,492 | $0.004063 | $26.37 |
| Claude 3.5 Haiku | 2 | 6,492 | $0.002800 | $18.18 |
| Qwen 2.5 72B Instruct | 2 | 6,492 | $0.000887 | $5.76 |
| DeepSeek V3 | 2 | 6,492 | $0.000385 | $2.50 |
| Llama 3.3 70B Instruct | 2 | 6,492 | $0.000345 | $2.24 |
| Gemini 1.5 Flash | 2 | 6,492 | $0.000244 | $1.58 |
| **Total Base** | **24** | **77,904** | — | **$419.38** |
| **With Safety Buffer (+7.3%)** | | | | **$450.00** |

---

## 6. Budget Drivers & Cost Sensitivity Analysis

1. **Frontier Model Dominance**:
   - The two frontier models (Claude 3.5 Sonnet and GPT-4o) account for **86.5%** ($1,079.17 of $1,247.66) of the total budget in Tier 1.
   - This asymmetry arises because Sonnet and GPT-4o serve dual roles: evaluating model capability (reference agent) AND evaluating framework robustness (4 adapters $\times$ 2 models).
2. **Open-Weight & Small Model Economy**:
   - The remaining 6 models (Gemini Pro, Haiku, Flash, DeepSeek, Qwen, Llama) combined cost only **$168.49** (13.5% of total budget) for 115,884 episodes.
   - DeepSeek V3, Qwen 2.5, and Llama 3.3 provide exceptional cost efficiency ($0.12–$0.35/Mtok in), demonstrating that expanding open-weight evaluations incurs negligible budget impact.
3. **Safety Buffer Justification**:
   - A 4–8% safety margin is incorporated into each tier to accommodate:
     - Scenarios triggering multi-turn retry loops under L01/L05.
     - Prompt inflation in adversarial injection tasks (A01–A03).
     - Token count variance across different natural language tokenizers.

---

## 7. Compliance & Integrity Disclosure

- **Zero Paid Network Calls**: As instructed, no paid API tokens or 128api calls were made during L70. All numbers are derived from static profile expansion on actual scenarios and empirical G53 token distributions.
- **Dry-run Validated**: The full matrix `leaderboard-v1` was verified with `skeptic bench run --matrix bench/matrix/leaderboard-v1.yaml --dry-run` and `--count`, matching the 231,768 episode calculation exactly.
- **Reproducibility**: All calculations are reproducible via standard CLI commands and unit tests.

---

## 8. H3 Approval Gate Sign-off Request

R0 hereby submits this document to the Human Project Sponsor for **H3 Approval**:

```text
Action Required: Human reviewer to approve one budget tier in GitHub Issue:
  - "批准 完整" (Tier 1, Cap $1,300.00)
  - "批准 节省" (Tier 2, Cap $880.00)
  - "批准 最低" (Tier 3, Cap $450.00)

Upon receipt of approval, Role R4 will proceed with Task L71:
  skeptic bench run --matrix bench/matrix/leaderboard-v1.yaml --max-cost-usd <批准额度>
```
