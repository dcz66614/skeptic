# Skeptic Leaderboard L71 Reduced-Scope Free Run Methodology

**Document Version**: 1.0.0  
**Date**: 2026-11-10  
**Status**: APPROVED INTERIM EXPERIMENT (H3 approval timestamp: 2026-11-10 21:16 Europe/London)  
**Governance Scope**: Skeptic Task L71 (Reduced-Scope Contrast Run)  

---

> [!IMPORTANT]
> **NOT THE OFFICIAL S16.2 LEADERBOARD**  
> This is a reduced-scope, $0 contrast run approved by H3 on 2026-11-10 21:16 Europe/London; it is NOT the official S16.2 leaderboard and must not be reported as one. The official S16.2 leaderboard matrix (`bench/matrix/leaderboard-v1.yaml`, 8 official models, 4 profiles, 3 seeds, 231,768 episodes, $1,300 ceiling) remains frozen and unfulfilled pending future formal H3 budget approval.

---

## 1. Executive Summary & Purpose

Following the empirical budget audit in `docs/reports/leaderboard-budget.md` demonstrating that the original S16.2 $1,300 ceiling is insufficient for a full 3-seed run at empirical token rates ($2,250 recommended cap), H3 approved an interim, zero-cost reduced experiment (L71) on 2026-11-10 21:16 Europe/London.

The goal of this L71 reduced run is to validate the execution pipeline, evaluate guards effectiveness (`guards: none` vs `guards: recommended`) on reference agents under `silent-core`, and gather empirical execution artifacts using zero-cost OpenAI-compatible experimental endpoints, without consuming project budget.

---

## 2. Experimental Scope & Boundary Isolation

### 2.1 Included Configurations

| Parameter | Specification | Notes |
|---|---|---|
| **Primary Matrix** | `bench/matrix/leaderboard-v1-reduced-free.yaml` | ID: `leaderboard-v1-reduced-free` |
| **Contrast Matrix** | `bench/matrix/leaderboard-v1-reduced-free-hy3.yaml` | ID: `leaderboard-v1-reduced-free-hy3` |
| **Suites** | `core-v1-l71-reduced` (56 scenarios), `core-v1-l71-hy3` (10 scenarios) | Deterministic subsets of `core-v1` |
| **Profiles** | `[silent-core]` | Single profile only |
| **Seeds** | `[1]` | Seed 1 only |
| **Agent Adapter** | `reference:${model}` | Reference agent only |
| **Prompt Variant** | `plain` | Plain instructions |
| **Guards Conditions** | `none`, `recommended` | 2 configurations per matrix |
| **Workhorse Model** | `compat/our-free-model/deepseek-ai/deepseek-v4.1-flash` | WorkBuddy relay endpoint (`http://127.0.0.1:5390/v1`) |
| **Contrast Model** | `compat/hy3` | Hunyuan 3 free experiment endpoint |
| **Safety Cap** | `max_cost_usd: 5.0` | Circuit breaker cap only; expected cost $0.00 |

### 2.2 Explicit Exclusions & Negative Scope

To maintain absolute budget isolation and prevent inadvertent API charges or scope leakage, the following components are strictly excluded from L71:

- **No OpenRouter Models**: None of the 8 official S16.1 leaderboard models or the S16.1 dev model are run in L71.
- **No Framework Adapters**: No evaluations of `openai-agents`, `langgraph`, `crewai`, or `pydantic-ai`.
- **No Other Profiles**: No execution under `loud-core`, `adversarial-core`, or `cross-source`.
- **No 128api Endpoints**: No calls to 128api commercial proxies.
- **No Paid WorkBuddy Models**: No calls to paid WorkBuddy slugs (`deepseek-v4.1-flash`, `deepseek-v4.1-flash-sg`, etc.).
- **No OpenCode Models**: No calls to any `opencode/*` models.
- **No Paid Fallback**: If an endpoint fails or rejects requests, fallback to a paid route is strictly forbidden.

---

## 3. Deterministic Suite Selection Rule

The scenarios for both suites are drawn exclusively from `bench/suites/core-v1.yaml` (200 total scenarios across 10 sandboxes). No scenarios are invented.

### 3.1 Selection Algorithm

1. **Sandbox Ordering**: Group scenarios by sandbox directory, preserving the exact order they first appear in `core-v1.yaml`:
   1. `calendar`
   2. `crm`
   3. `docs`
   4. `files`
   5. `fx`
   6. `mail`
   7. `orders`
   8. `sqlshop`
   9. `stocks`
   10. `weather`
2. **Within-Sandbox Ordering**: Preserve the scenario ordering within each sandbox as defined in `core-v1.yaml`.
3. **`core-v1-l71-reduced` (56 scenarios)**:
   - Take the first 5 scenarios from every sandbox: $10 \times 5 = 50$ scenarios.
   - Take the 6th scenario from the first 6 sandboxes (`calendar`, `crm`, `docs`, `files`, `fx`, `mail`): $6 \times 1 = 6$ scenarios.
   - Total: $50 + 6 = 56$ scenarios.
4. **`core-v1-l71-hy3` (10 scenarios)**:
   - Take the 1st scenario from each of the 10 sandboxes: $10 \times 1 = 10$ scenarios.
   - By definition, these 10 scenarios are a strict subset of the 56 scenarios in `core-v1-l71-reduced`.

---

## 4. Episode Expansion & Deterministic Counts

Episode counts are verified statically using `count_matrix_episodes` and CLI dry counting (`uv run skeptic bench run --matrix <file> --count`):

### 4.1 Primary Reduced Matrix (`leaderboard-v1-reduced-free`)

- **Suite**: `core-v1-l71-reduced` (56 scenarios)
- **Profile**: `silent-core` (generates 446 episodes for 56 scenarios under seed 1)
- **Seeds**: `[1]` (1 seed)
- **Configs**: 2 (`reference:${model}` with `guards: none`, and `reference:${model}` with `guards: recommended`)
- **Model**: `compat/our-free-model/deepseek-ai/deepseek-v4.1-flash`
- **Total Episodes**: $446 \times 2 = 892$ episodes.
- **CLI Verification**:
  ```bash
  uv run skeptic bench run --matrix bench/matrix/leaderboard-v1-reduced-free.yaml --count
  # Output: Total episodes: 892
  ```

### 4.2 Contrast Matrix (`leaderboard-v1-reduced-free-hy3`)

- **Suite**: `core-v1-l71-hy3` (10 scenarios)
- **Profile**: `silent-core` (generates 84 episodes for 10 scenarios under seed 1)
- **Seeds**: `[1]` (1 seed)
- **Configs**: 2 (`reference:${model}` with `guards: none`, and `reference:${model}` with `guards: recommended`)
- **Model**: `compat/hy3`
- **Total Episodes**: $84 \times 2 = 168$ episodes.
- **CLI Verification**:
  ```bash
  uv run skeptic bench run --matrix bench/matrix/leaderboard-v1-reduced-free-hy3.yaml --count
  # Output: Total episodes: 168
  ```

### 4.3 Combined Evaluation Volume

- **Combined Episodes**: $892 + 168 = 1,060$ episodes.
- In contrast, the full S16.2 leaderboard matrix spans 231,768 episodes (L71 reduced run is ~0.46% of the full official matrix volume).

### 4.4 Execution Latency & Episode Timeout Override

Empirical smoke testing demonstrated that the free DSH workhorse (`compat/our-free-model/deepseek-ai/deepseek-v4.1-flash`) via the WorkBuddy relay is slower than 180s/episode (taking ~90s per LLM generation request, averaging ~3.8 requests/episode). Under the scenario default 180s limit (`limits.timeout_s: 180`), episodes would fail with `flags.timed_out=true` and `outcome: ERROR`.

Therefore, the reduced run must pass an episode timeout override:
- Via CLI: `--episode-timeout-s` (recommend 900) on `skeptic bench run` or `skeptic run`
- Or via environment variable: `export SKEPTIC_EPISODE_TIMEOUT_S=900`

> [!NOTE]
> The official S16.2 run is **NOT** changed; its scenario definitions and specifications retain the default 180s timeout. The episode timeout override is an operational parameter allowing slow free models to be evaluated without modifying scenario files.

---

## 5. Cost Accounting & Safeguards

### 5.1 Pricing Registration

Both models are explicitly declared with zero rates in `bench/leaderboard/models.yaml`:
- `compat/our-free-model/deepseek-ai/deepseek-v4.1-flash`: `price_in_per_mtok: 0.0`, `price_out_per_mtok: 0.0`.
- `compat/hy3`: `price_in_per_mtok: 0.0`, `price_out_per_mtok: 0.0`.

### 5.2 Cash Spend & Safety Cap

- **Expected Cash Spend**: **$0.00 USD**.
- **Matrix Safety Cap (`max_cost_usd`)**: **$5.00 USD** in each matrix.
  - This cap is an emergency guardrail against accidental billing anomalies; it is not a spending target or an authorization for paid usage.
  - It is completely distinct from the S16.2 official $1,300 ceiling.

### 5.3 Fail-Closed Provider Cost Policy

> [!CAUTION]
> If any execution monitoring or provider accounting indicates WorkBuddy balance deductions, credit consumption, or non-zero billing, the run **MUST BE IMMEDIATELY HALTED**. Under no circumstances may an agent switch to paid endpoints.

---

## 6. Statistical Limitations & Interpretability

Because this is a reduced-scope verification experiment, its statistical power is inherently constrained:

1. **No Confidence Intervals Across Seeds**: With a single seed (`[1]`), seed-to-seed variance cannot be computed. Paired bootstrap confidence intervals ($B=1000$) across seeds are not possible.
2. **Single Profile Bias**: Only `silent-core` is evaluated. Fault detection under `loud-core` (noisy tool exceptions), `adversarial-core` (prompt injection), and `cross-source` (contradictory tools) is unmeasured.
3. **Partial Scenario Sample**: 56 of 200 scenarios (~28% coverage) means specific domain tasks and multihop scenarios from `orders`, `sqlshop`, `stocks`, and `weather` are omitted.
4. **Experimental Models Only**: Results reflect local relay and experimental endpoints, not public commercial frontier models.

**Conclusion**: Data from L71 cannot be merged into or cited as official Skeptic Leaderboard standings.
