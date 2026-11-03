# Guard Control Experiment and Recommended Preset Selection (Guards A/B)

This document specifies the methodology, execution protocol, and evaluation criteria for Skeptic task **G53** ("Guards Control Experiment and `recommended` Preset").

The purpose of this study is to empirically evaluate the effectiveness of Skeptic's eight defensive guards (G01–G08) under controlled synthetic faults, identifying which guards provide significant reliability gains and determining the definitive composition of the `recommended` preset.

---

## 1. Experimental Design & Methodology

### 1.1 Scenario Corpus
To balance evaluation power against monetary budget ($\le \$60$), the experiment samples **60 scenarios** from the 200-scenario `core-v1` suite using Python's pseudo-random number generator initialized with **seed 0**:
```python
import random
from skeptic_agent.scenario.suites import load_suite

suite = load_suite("core-v1")
rng = random.Random(0)
sampled_scenarios = rng.sample(suite.scenarios, 60)
```
The sampled suite is persisted as `bench/suites/guards-ab.yaml` (aliased as `bench/suites/core-v1-guards-ab.yaml`). It spans all 10 MCP sandboxes (`sb_calendar`, `sb_crm`, `sb_docs`, `sb_files`, `sb_fx`, `sb_mail`, `sb_orders`, `sb_sqlshop`, `sb_stocks`, `sb_weather`) across diverse read, write, multi-hop, and edge cases.

### 1.2 Fault Profiles
Each scenario is evaluated under three standard fault profiles defined in S7.2, operating under deterministic `per_fault` expansion:
1. **`silent-core`**: 9 silent data corruption faults (S01 empty response, S02 truncation, S03 stale date, S04 numeric corruption, S05 wrong entity, S06 key redaction, S07 malformed payload, S08 unit swap, and S10 phantom write).
2. **`loud-core`**: 6 explicit transport and runtime faults (L01 timeout hold, L02 JSON-RPC -32603 internal error, L03 tool execution error, L05 429 rate limit, L06 tool missing, L07 schema drift).
3. **`adversarial-core`**: 3 prompt injection and tool description poisoning faults (A01 tool output injection, A02 tool description poisoning, A03 rug-pull delayed injection).

Across the 60 scenarios, static applicability filters yield:
- `silent-core`: 481 episodes (per seed)
- `loud-core`: 300 episodes (per seed)
- `adversarial-core`: 180 episodes (per seed)
- **Total per configuration/seed**: 961 episodes.

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

### 1.4 Evaluated Models
Per card G53, the matrix evaluates two models via the reference ReAct agent (`reference:${model}`):
- **Dev Tier**: `compat/deepseek-v4-pro` (fast, cost-effective base)
- **Mid Tier**: `compat/gpt-5.6-terra` (representative production model)

With 2 models $\times$ 10 guard configurations $\times$ 961 episodes/run, the full matrix defines **19,220 total episodes**.

---

## 2. Decision Criteria for `recommended` Preset

A guard is included in the production `recommended` preset if removing it in the ablation experiment reveals a measurable degradation:
1. **SKS Drop**: $\Delta\text{SKS} \le -1.0$ (SKS falls by 1.0 point or more when the guard is removed).
2. **FSR Increase**: $\Delta\text{FSR} \ge +2.0\%$ (Failure Silence Rate rises by 2.0 percentage points or more when the guard is removed).

### Acceptance Gate
- The final `recommended` preset must produce a statistically significant reduction in Failure Silence Rate (FSR) relative to `none`, confirmed by non-overlapping 95% bootstrap confidence intervals ($B = 1000$ paired cluster resamples).
- If the confidence intervals overlap or no guard meets the threshold, the report must document the findings and retain the tentative default:
  `[schema_guard, staleness_guard, emptiness_guard, retry_guard, loop_breaker, injection_shield, drift_lock]` (G02–G08, excluding G01).

---

## 3. How to Run

The entire study is captured in `bench/matrix/guards-ab.yaml` conforming to the `skeptic.matrix/v1` schema.

### 3.1 Pre-run Inspection (Dry-run / Episode Count)
Verify matrix configuration validity and inspect the planned episode count without making network or model calls:
```bash
# Print configuration summary and total episode count (19,220 episodes)
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --dry-run

# Or print only the episode count integer
uv run skeptic bench run --matrix bench/matrix/guards-ab.yaml --count
```

### 3.2 Executing the Benchmark Matrix
Run the matrix evaluation against the OpenAI-compatible endpoint with concurrency and ledger tracking:
```bash
uv run skeptic bench run \
  --matrix bench/matrix/guards-ab.yaml \
  --concurrency 4 \
  --ledger bench/ledger.csv \
  --out runs/guards-ab
```

### 3.3 Resuming an Interrupted Run
If a run is stopped or encounters network throttling, resume seamlessly using `--resume`:
```bash
uv run skeptic bench run \
  --matrix bench/matrix/guards-ab.yaml \
  --resume \
  --ledger bench/ledger.csv \
  --out runs/guards-ab
```

### 3.4 Comparing Configurations
Compare the baseline (`none`) against the full pipeline (`all`) or individual ablations using paired bootstrap CI:
```bash
uv run skeptic compare runs/guards-ab/<none_run_id> runs/guards-ab/<all_run_id>
```

---

## 4. Results (TBD)

> *Results below will be populated after executing the matrix in task G53.*

### 4.1 Summary Metrics by Configuration

| Config | Model | SKS (95% CI) | FSR (95% CI) | RR | ICR | Cost (USD) | Run ID |
|---|---|---|---|---|---|---|---|
| `none` (Baseline) | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| `none` (Baseline) | `compat/gpt-5.6-terra` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| `all` (Full) | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| `all` (Full) | `compat/gpt-5.6-terra` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G01 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G02 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G03 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G04 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G05 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G06 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G07 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |
| Minus G08 | `compat/deepseek-v4-pro` | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* | *TBD* |

### 4.2 Ablation Impact Analysis

| Guard Omitted | Name | $\Delta\text{SKS}$ | $\Delta\text{FSR}$ | Meets Inclusion Criteria ($\Delta\text{SKS} \le -1.0$ or $\Delta\text{FSR} \ge +2.0\%$) |
|---|---|---|---|---|
| G01 | `evidence_contract` | *TBD* | *TBD* | *TBD* |
| G02 | `schema_guard` | *TBD* | *TBD* | *TBD* |
| G03 | `staleness_guard` | *TBD* | *TBD* | *TBD* |
| G04 | `emptiness_guard` | *TBD* | *TBD* | *TBD* |
| G05 | `retry_guard` | *TBD* | *TBD* | *TBD* |
| G06 | `loop_breaker` | *TBD* | *TBD* | *TBD* |
| G07 | `injection_shield` | *TBD* | *TBD* | *TBD* |
| G08 | `drift_lock` | *TBD* | *TBD* | *TBD* |

### 4.3 Final `recommended` Composition
- **Status**: Pending empirical run.
- **Current Tentative Preset**: `[G02, G03, G04, G05, G06, G07, G08]` (in `src/skeptic_agent/guards/presets.py`).
