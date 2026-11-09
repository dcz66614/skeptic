# Guard Control Experiment and Recommended Preset Selection (Guards A/B)

This document specifies the methodology, execution protocol, and empirical evaluation results for Skeptic task **G53** ("Guards Control Experiment and `recommended` Preset").

The purpose of this study is to empirically evaluate the effectiveness of Skeptic's eight defensive guards (G01–G08) under controlled synthetic faults, identifying which guards provide significant reliability gains and determining the definitive composition of the `recommended` preset.

---

## 1. Experimental Design & Methodology

### 1.1 Scenario Corpus
To balance evaluation power against monetary budget ($\le \$60$), the study was initially planned around a sample of **60 scenarios** from the 200-scenario `core-v1` suite using Python's pseudo-random number generator initialized with **seed 0**:
```python
import random
from skeptic_agent.scenario.suites import load_suite

suite = load_suite("core-v1")
rng = random.Random(0)
sampled_scenarios = rng.sample(suite.scenarios, 60)
```
The full 60-scenario suite is persisted as `bench/suites/guards-ab.yaml` (aliased as `bench/suites/core-v1-guards-ab.yaml`). It spans all 10 MCP sandboxes (`sb_calendar`, `sb_crm`, `sb_docs`, `sb_files`, `sb_fx`, `sb_mail`, `sb_orders`, `sb_sqlshop`, `sb_stocks`, `sb_weather`) across diverse read, write, multi-hop, and edge cases.

#### Reduced Free-Model Corpus (Executed Benchmark)
To execute the empirical run under a strict zero-cost budget regime, a reduced 30-scenario suite was derived by taking the first 30 scenarios of `guards-ab` in deterministic order:
- Suite: `bench/suites/guards-ab-free.yaml` (`id: guards-ab-free`)
- Matrix: `bench/matrix/guards-ab-free.yaml` (`id: guards-ab-free`)

### 1.2 Fault Profiles
Each scenario is evaluated under three standard fault profiles defined in S7.2, operating under deterministic `per_fault` expansion:
1. **`silent-core`**: 9 silent data corruption faults (S01 empty response, S02 truncation, S03 stale date, S04 numeric corruption, S05 wrong entity, S06 key redaction, S07 malformed payload, S08 unit swap, and S10 phantom write).
2. **`loud-core`**: 6 explicit transport and runtime faults (L01 timeout hold, L02 JSON-RPC -32603 internal error, L03 tool execution error, L05 429 rate limit, L06 tool missing, L07 schema drift).
3. **`adversarial-core`**: 3 prompt injection and tool description poisoning faults (A01 tool output injection, A02 tool description poisoning, A03 rug-pull delayed injection).

Static applicability filters yield the following episode counts per configuration:
- **Full 60-scenario suite** (`bench/matrix/guards-ab.yaml`):
  - `silent-core`: 481 episodes (per seed)
  - `loud-core`: 300 episodes (per seed)
  - `adversarial-core`: 180 episodes (per seed)
  - Total per configuration/seed: 961 episodes.
- **Reduced 30-scenario suite** (`bench/matrix/guards-ab-free.yaml`):
  - `silent-core`: 241 episodes (per seed)
  - `loud-core`: 151 episodes (per seed)
  - `adversarial-core`: 90 episodes (per seed)
  - Total per configuration/seed: **482 episodes**.

### 1.3 Guard Configurations & Ablations
To isolate the individual contribution of each guard, the benchmark evaluates **10 distinct guard configurations**:
1. **Baseline (`none`)**: No guards enabled (`guards: none`).
2. **Full Pipeline (`all`)**: All 8 guards active (`guards: all`).
3. **Minus G01 (`evidence_contract`)**: `[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
4. **Minus G02 (`schema_guard`)**: `[evidence_contract, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
5. **Minus G03 (`staleness_guard`)**: `[evidence_contract, schema_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
6. **Minus G04 (`emptiness_guard`)**: `[evidence_contract, schema_guard, staleness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]`
7. **Minus G05 (`retry_guard`)**: `[evidence_contract, schema_guard, staleness_guard, emptiness_guard, loop_breaker, injection_shield, drift_lock]`
8. **Minus G06 (`loop_breaker`)**: `[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, injection_shield, drift_lock]`
9. **Minus G07 (`injection_shield`)**: `[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, drift_lock]`
10. **Minus G08 (`drift_lock`)**: `[evidence_contract, schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield]`

### 1.4 Evaluated Models & Execution Scope
The original G53 plan specified two models via the reference ReAct agent (`reference:${model}`):
- **Dev Tier**: `compat/deepseek-v4-pro`
- **Mid Tier**: `compat/gpt-5.6-terra`
With 2 models $\times$ 10 guard configurations $\times$ 961 episodes = **19,220 total episodes**.

#### Executed Run Scope & One-Model Gap
Due to upstream API token budget restrictions, the executed empirical benchmark utilized a free-tier endpoint:
- **Evaluated Model**: `compat/hy3` ($0 price, dev tier)
- **Matrix**: `bench/matrix/guards-ab-free.yaml` (1 model $\times$ 10 configurations $\times$ 482 episodes)
- **Total Executed Episodes**: **4,820 episodes** (a shrink from 19,220 $\to$ 4,820 episodes)
- **One-Model Gap**: The empirical results below reflect solely `compat/hy3`. Evaluations across multiple frontier and mid-tier models remain subject to future funded runs.

---

## 2. Decision Criteria for `recommended` Preset

A guard is eligible for inclusion in the production `recommended` preset if removing it in the ablation experiment reveals a measurable degradation:
1. **SKS Drop**: $\Delta\text{SKS} \le -1.0$ (SKS falls by 1.0 point or more when the guard is omitted).
2. **FSR Increase**: $\Delta\text{FSR} \ge +2.0\%$ (Failure Silence Rate rises by 2.0 percentage points or more when the guard is omitted).

### Acceptance Gate
- The final `recommended` preset must produce a statistically significant reduction in Failure Silence Rate (FSR) relative to `none`, confirmed by non-overlapping 95% bootstrap confidence intervals ($B = 1000$ paired cluster resamples).
- If the confidence intervals overlap or no guard meets the threshold, the report must document the findings and retain the tentative default:
  `[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]` (G02–G08, excluding G01).

---

## 3. How to Run

### 3.1 Pre-run Inspection (Dry-run / Episode Count)
Verify matrix configuration validity and inspect episode counts without making network or model calls:
```bash
# Full matrix (19,220 episodes)
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --dry-run
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --count

# Free-model reduced matrix (4,820 episodes)
uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --dry-run
uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --count
```

### 3.2 Executing the Benchmark Matrix
```bash
uv run skeptic bench run \
  --matrix bench/matrix/guards-ab-free.yaml \
  --concurrency 4 \
  --ledger bench/ledger.csv \
  --out runs/guards-ab-free
```

### 3.3 Comparing Configurations
Compare any two runs using paired bootstrap CI:
```bash
uv run skeptic compare runs/guards-ab-free/<none_run_id> runs/guards-ab-free/<all_run_id>
```

---

## 4. Empirical Results (`compat/hy3`)

The 10 configurations were executed across 4,820 episodes on `compat/hy3`. Results and bootstrap 95% confidence intervals ($B = 1000$) are reported below.

### 4.1 Summary Metrics by Configuration

| Config | Model | SKS (95% CI) | FSR (95% CI) | RR | ICR | Cost (USD) | Run ID |
|---|---|---|---|---|---|---|---|
| `none` (Baseline) | `compat/hy3` | 93.19 (89.71–96.00) | 8.54% (3.14%–15.58%) | 0.0000 | 0.0000 | $1.16 | `20261103-155316-3e96a4` |
| `all` (Full) | `compat/hy3` | 92.68 (88.87–95.88) | 7.29% (1.88%–14.53%) | 0.0000 | 0.0000 | $1.37 | `20261103-162358-6c18bb` |
| Minus G01 (`evidence_contract`) | `compat/hy3` | 92.19 (88.23–95.62) | 8.56% (3.09%–15.87%) | 0.0000 | 0.0000 | $1.38 | `20261103-165643-d4399c` |
| Minus G02 (`schema_guard`) | `compat/hy3` | 92.64 (88.57–96.10) | 7.31% (1.45%–15.16%) | 0.0000 | 0.0000 | $1.34 | `20261103-172835-b3135c` |
| Minus G03 (`staleness_guard`) | `compat/hy3` | 93.17 (89.27–96.43) | 6.89% (1.46%–14.05%) | 0.0000 | 0.0000 | $1.34 | `20261103-180108-b1c518` |
| Minus G04 (`emptiness_guard`) | `compat/hy3` | 93.43 (89.78–96.48) | 6.88% (1.67%–13.60%) | 0.0000 | 0.0000 | $1.27 | `20261103-183234-5606cf` |
| Minus G05 (`retry_guard`) | `compat/hy3` | 93.20 (89.04–96.52) | 7.52% (1.66%–15.52%) | 0.0000 | 0.0000 | $1.41 | `20261103-190521-3a13ec` |
| Minus G06 (`loop_breaker`) | `compat/hy3` | 93.78 (90.35–96.56) | 6.67% (2.06%–12.90%) | 0.0000 | 0.0000 | $1.29 | `20261103-195059-0efa70` |
| Minus G07 (`injection_shield`) | `compat/hy3` | 92.92 (88.92–96.34) | 6.88% (1.04%–14.43%) | 0.0000 | 0.0000 | $1.36 | `20261103-204210-c5587d` |
| Minus G08 (`drift_lock`) | `compat/hy3` | 93.22 (89.19–96.48) | 6.88% (1.24%–14.14%) | 0.0000 | 0.0000 | $1.36 | `20261103-211533-97d29f` |

### 4.2 Ablation Impact Analysis

Deltas are computed relative to `all` (Full Protection: SKS = 92.68, FSR = 7.29%):
$$\Delta\text{SKS} = \text{SKS}_{\text{ablation}} - \text{SKS}_{\text{all}}, \quad \Delta\text{FSR} = \text{FSR}_{\text{ablation}} - \text{FSR}_{\text{all}}$$

| Guard Omitted | Name | SKS | $\Delta\text{SKS}$ | FSR | $\Delta\text{FSR}$ | Meets Inclusion Criteria ($\Delta\text{SKS} \le -1.0$ or $\Delta\text{FSR} \ge +2.0\text{pp}$) |
|---|---|---|---|---|---|---|
| G01 | `evidence_contract` | 92.19 | -0.49 | 8.56% | +1.27pp | **No** (Closest; $\Delta\text{FSR} = +1.27\text{pp} < +2.0\text{pp}$) |
| G02 | `schema_guard` | 92.64 | -0.04 | 7.31% | +0.02pp | **No** |
| G03 | `staleness_guard` | 93.17 | +0.49 | 6.89% | -0.40pp | **No** |
| G04 | `emptiness_guard` | 93.43 | +0.75 | 6.88% | -0.41pp | **No** |
| G05 | `retry_guard` | 93.20 | +0.52 | 7.52% | +0.23pp | **No** |
| G06 | `loop_breaker` | 93.78 | +1.10 | 6.67% | -0.62pp | **No** |
| G07 | `injection_shield` | 92.92 | +0.24 | 6.88% | -0.41pp | **No** |
| G08 | `drift_lock` | 93.22 | +0.54 | 6.88% | -0.41pp | **No** |

### 4.3 Key Findings & Statistical Discussion

1. **Wide Confidence Interval Overlap**:
   - Baseline `none` achieves SKS = 93.19 (CI 89.71–96.00) and FSR = 8.54% (CI 3.14%–15.58%).
   - Full protection `all` achieves SKS = 92.68 (CI 88.87–95.88) and FSR = 7.29% (CI 1.88%–14.53%).
   - Across all ablations, SKS ranges narrowly between 92.19 and 93.78, while FSR spans 6.67% to 8.56%.
   - Every single 95% bootstrap confidence interval broadly overlaps with the others. The overlap covers nearly the entire [88, 96] interval for SKS and [1%, 16%] for FSR. There is no statistically significant separation between configurations.

2. **Threshold Rule Evaluation**:
   - **NO guard meets the inclusion threshold** ($\Delta\text{SKS} \le -1.0$ or $\Delta\text{FSR} \ge +2.0\text{pp}$).
   - The closest candidate is **G01 (`evidence_contract`)**, whose removal increases FSR by $+1.27\text{pp}$ (from 7.29% to 8.56%) and decreases SKS by $-0.49$ points (from 92.68 to 92.19). However, this effect is well beneath the $+2.0\text{pp}$ bar and is accompanied by a large CI overlap (8.56% [3.09%, 15.87%] vs 7.29% [1.88%, 14.53%]). Moreover, G01 alters tool output text by prepending contract framing, which motivated its initial exclusion from tentative presets.
   - For all other guards (G02–G08), ablation deltas hover within $\pm 0.5\text{pp}$ FSR and $\pm 1.1$ SKS, well within sample variance.

3. **Study Limitations (Shrink & Single Model)**:
   - **Corpus Shrink**: The experiment was executed on 30 scenarios $\times$ 482 episodes = 4,820 episodes, compared to the planned 60 scenarios $\times$ 961 episodes $\times$ 2 models = 19,220 episodes.
   - **One-Model Gap**: The study evaluated only `compat/hy3`. Different model architectures, instruction-following capabilities, or reasoning depths may interact differently with protective guards.

### 4.4 Final `recommended` Composition Decision

Per Section 2 of this methodology:
> *"If the confidence intervals overlap or no guard meets the threshold, the report must document the findings and retain the tentative default: `[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]` (G02–G08, excluding G01)."*

Because no guard satisfied the quantitative threshold rule and all confidence intervals overlap widely, the `recommended` preset **remains provisional**:
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
No changes have been made to `src/skeptic_agent/guards/presets.py`. Final empirical recalibration of `recommended` will require running the full 19,220-episode matrix across multiple frontier models once API budget is available.
