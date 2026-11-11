# Reduced-Scope Flash Leaderboard Experiment (L74)

## Status Banner

> [!IMPORTANT]
> **REDUCED-SCOPE SINGLE-MODEL EXPERIMENT — NOT S16.2**
>
> - **Reduced-scope single-model experiment**: Evaluates `compat/deepseek-v4.1-flash-sg` only.
> - **not S16.2**: The official S16.2 leaderboard matrix remains frozen and unfulfilled.
> - **not the free DSH run**: This run was executed via the paid WorkBuddy route with an off-peak credit budget, distinct from the free DSH run.
> - **Full LaTeX technical report deferred**: No LaTeX toolchain or matplotlib installation exists in the local environment; the full LaTeX tech report L74 deferred pending toolchain and Cd approval.

---

## Setup

The experiment was executed using the following parameters:

- **Matrix**: `bench/matrix/leaderboard-v1-reduced-flash.yaml` (matrix ID: `leaderboard-v1-reduced-flash`)
- **Model**: `compat/deepseek-v4.1-flash-sg`
- **Suite**: `core-v1-l71-reduced` (56 scenarios)
- **Seeds**: `[1]` (seed 1)
- **Profile**: `silent-core`
- **Guards Configurations**: `none` and `recommended`
- **Run IDs**:
  - `none`: `20261111-202444-07a2ff`
  - `recommended`: `20261111-204118-1d7e2e`
- **Git SHA**: `8624def`
- **Evaluated Volume**: 446 episodes per configuration (892 total episodes)
- **Errors**: 0 execution errors across all 892 episodes

---

## Results Table

The table below presents the core evaluation metrics for each configuration, extracted deterministically from `paper/numbers.json`:

| Configuration | SKS (95% CI) | FSR (95% CI) | SCR (95% CI) | SafeRate (95% CI) | DetectRate (95% CI) | Episodes | Errors |
|---|---|---|---|---|---|---|---|
| `none` | 96.09 [93.67, 98.09] | 3.59% [1.57%, 5.62%] | 1.35% [0.45%, 2.29%] | 93.50% [89.11%, 97.07%] | 45.74% [37.11%, 54.26%] | 446 | 0 |
| `recommended` | 95.92 [93.58, 97.72] | 4.93% [2.00%, 9.11%] | 1.35% [0.45%, 2.46%] | 93.27% [89.16%, 96.40%] | 53.81% [46.29%, 61.00%] | 446 | 0 |
| **Delta (rec - none)** | **-0.16** | **+1.35%** | — | — | **+8.07%** | **892** | **0** |

### Per-Config Outcome Breakdown

| Configuration | SUCCESS | HONEST_FAILURE | FALSE_SUCCESS | SILENT_CORRUPTION | INJECTED | NO_ANSWER | Total |
|---|---|---|---|---|---|---|---|
| `none` | 385 | 32 | 16 | 6 | 6 | 1 | 446 |
| `recommended` | 374 | 42 | 22 | 6 | 0 | 2 | 446 |

---

## Guard Contrast

A direct comparison of `recommended` guards versus `none`:

1. **SKS and FSR within overlapping confidence intervals**:
   - SKS shifted from 96.09 (`none`) to 95.92 (`recommended`), a delta of -0.16. The 95% confidence intervals overlap substantially ([93.67, 98.09] vs [93.58, 97.72]).
   - FSR shifted from 3.59% (`none`) to 4.93% (`recommended`), a delta of +1.35%. The 95% confidence intervals overlap ([1.57%, 5.62%] vs [2.00%, 9.11%]).
   - **Conclusion**: We do not claim that guards helped or hurt overall performance; the observed differences fall well within statistical estimation noise for this sample size.
2. **Detection rate rose**:
   - DetectRate increased from 45.74% [37.11%, 54.26%] under `none` to 53.81% [46.29%, 61.00%] under `recommended` (+8.07% delta).
3. **By-fault highlights**:
   - Injected faults: Under `none`, 6 episodes ended with outcome `INJECTED` across fault codes S01 (1), S02 (1), S03 (1), S04 (1), S07 (1), and S08 (1). Under `recommended`, `INJECTED` dropped to 0 across all fault categories.
   - Fail-closed behavior on outage: Fault code S10 (full service outage) resulted in 5 `HONEST_FAILURE` outcomes in both `none` and `recommended` configurations.
   - Silent corruption: `SILENT_CORRUPTION` remained identical at 6 episodes in both configurations (S01: 1 and S04: 5 in `none`; S04: 5 and S05: 1 in `recommended`).

---

## Cost and Credits

Token consumption and credit accounting from `paper/data/l71_flash/ledger_flash.csv` (deduplicated by run ID):

| Metric | `none` (`20261111-202444-07a2ff`) | `recommended` (`20261111-204118-1d7e2e`) | Total |
|---|---|---|---|
| Input Tokens (`tokens_in`) | 1729518 | 1754548 | 3484066 |
| Output Tokens (`tokens_out`) | 161712 | 159631 | 321343 |
| Total Tokens | 1891230 | 1914179 | 3805409 |
| Reported Relay Cost (`cost_usd`) | 0.0 | 0.0 | 0.0 |
| Estimated Credits (Upper Bound) | 33.95 | 34.19 | 68.14 |

### Credit Estimation Methodology

- **Relay Cost**: The OpenAI-compatible relay reports `cost_usd: 0.0` because WorkBuddy bills upstream credits directly rather than returning USD charges in response headers.
- **Credit Rates**: WorkBuddy documents off-peak rates of 14.29 credits/MTok input and 57.1 credits/MTok output.
- **Upper Bound Formula**:
  $$\text{credits} = \left(\frac{\text{tokens\_in}}{1{,}000{,}000}\right) \times 14.29 + \left(\frac{\text{tokens\_out}}{1{,}000{,}000}\right) \times 57.1$$
  This calculation ignores cached token discounts (0.29/MTok) and represents an **UPPER BOUND ESTIMATE**.
- **Budget Hard Cap**: The campaign consumed an estimated 68.14 credits (33.95 for `none` + 34.19 for `recommended`). The operational hard cap of 150 credits was not tripped.

---

## Limitations

This study is subject to several methodological constraints:

- **Single Model**: Evaluates only `compat/deepseek-v4.1-flash-sg`.
- **Single Seed**: Conducted under seed 1 only; variance across random seeds is unmeasured.
- **Reduced Suite**: Covers 56 scenarios rather than the full benchmark.
- **Single Profile**: Tested under `silent-core` only; noisy, adversarial, or cross-source profiles were not run.
- **No Cross-Model Ranking**: Because only a single model was evaluated, relative model rankings cannot be inferred.
- **No Statistically Significant Guard Effect**: Overlapping 95% confidence intervals on SKS and FSR mean no definitive advantage or penalty can be attributed to guards on this sample.
- **No Judge**: Evaluated with rule-based verification only; LLM-as-judge was not enabled.

---

## Reproduction

To regenerate the deterministic numbers file from the source experiment data:

```bash
python paper/make_numbers.py
```

This updates `paper/numbers.json` deterministically with sorted keys, LF line endings, and two-space indentation.
