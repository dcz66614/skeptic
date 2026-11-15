# Free Hunyuan 3 and Hunyuan 4 Contrast Experiment Report (L71)

## Status Banner

> [!IMPORTANT]
> **EXPERIMENTAL DIAGNOSTIC RUN — NOT S16.2 — NOT THE FLASH-SG L74 PAPER**
>
> - **Experiment Only**: This report documents an exploratory contrast between free experimental models (`compat/hy3` and `compat/hy4free`).
> - **NOT S16.2**: The official S16.2 leaderboard matrix (`bench/matrix/leaderboard-v1.yaml`) remains frozen and unfulfilled. These runs do not represent official leaderboard scores.
> - **NOT the Flash-SG L74 Paper**: This work is separate from the paid WorkBuddy Flash study (`compat/deepseek-v4.1-flash-sg`) documented in `docs/reports/leaderboard-l74-reduced-flash.md` and `paper/`.
> - **Small Samples & Infrastructure Focus**: Small sample sizes and infrastructure timeout constraints preclude quality or significance claims.

---

## Setup

The contrast runs evaluated two free OpenAI-compatible experimental endpoints via the local WorkBuddy relay (`http://127.0.0.1:5390/v1`):

### `compat/hy3` Setup
- **Matrix**: `bench/matrix/leaderboard-v1-reduced-free-hy3.yaml` (matrix ID: `leaderboard-v1-reduced-free-hy3`)
- **Suite**: `bench/suites/core-v1-l71-hy3.yaml` (`core-v1-l71-hy3`, 10-scenario slice)
- **Model**: `compat/hy3`
- **Profile**: `silent-core`
- **Seeds**: `[1]` (seed 1)
- **Episode Timeout**: 600s
- **Concurrency**: 2
- **Agent / Prompt**: `reference:${model}`, `plain`
- **Guard Configurations**: `none` and `recommended`
- **Volume**: 84 episodes per guard config (168 total episodes)
- **Git SHA**: `c7a267f`
- **Total Cost USD**: $0.0 (`total_cost_usd: 0.0`)
- **Run IDs**:
  - `none`: `20261113-010228-4d066f`
  - `recommended`: `20261113-011801-780a6c`
- **Sources**:
  - `none`: `C:\Users\Du200\Projects\skeptic_runs\l71_hy3\hy3\00_compat_hy3\summary.json` and `results.jsonl`
  - `recommended`: `C:\Users\Du200\Projects\skeptic_runs\l71_hy3\hy3\01_compat_hy3\summary.json` and `results.jsonl`

### `compat/hy4free` Setup
- **Matrix**: `bench/matrix/leaderboard-v1-reduced-free-hy4.yaml` (matrix ID: `leaderboard-v1-reduced-free-hy4`)
- **Suite**: `bench/suites/core-v1-l71-reduced.yaml` (`core-v1-l71-reduced`, 56 scenarios)
- **Model**: `compat/hy4free`
- **Profile**: `silent-core`
- **Seeds**: `[1]` (seed 1)
- **Episode Timeout**: 180s
- **Concurrency**: 4
- **Agent / Prompt**: `reference:${model}`, `plain`
- **Guard Configurations**: `none` and `recommended`
- **Total Cost USD**: $0.0
- **Run IDs**:
  - `none`: `20261111-235805-0926b0`
  - `recommended`: `20261112-052708-867a59`
- **Sources**:
  - `none`: `C:\Users\Du200\Projects\skeptic_runs\l71_hy4free\hy4\00_compat_hy4free\summary.json` and `results.jsonl`
  - `recommended`: `C:\Users\Du200\Projects\skeptic_runs\l71_hy4free\hy4\01_compat_hy4free\results.jsonl` (no recommended `summary.json`; run was deadline-interrupted)

---

## hy3 Results Table

The verified outcomes across the 84 episodes per guard config for `compat/hy3`:

| Configuration | Run ID | Total Episodes | SUCCESS | FALSE_SUCCESS | HONEST_FAILURE | SILENT_CORRUPTION | NO_ANSWER | ERROR |
|---|---|---|---|---|---|---|---|---|
| `none` | `20261113-010228-4d066f` | 84 | 66 | 4 | 9 | 2 | 3 | 0 |
| `recommended` | `20261113-011801-780a6c` | 84 | 66 | 4 | 7 | 1 | 5 | 1 |

### hy3 Observations
- **Identical SUCCESS Counts**: `SUCCESS` counts are identical (66 in both `none` and `recommended`).
- **No Guard Effect Evidence**: This small sample does not support a claim that guards helped or hurt.
- **Single Error in Recommended**: The 1 `ERROR` outcome in the `recommended` run occurred on scenario `sqlshop.comprehensive.shop-analysis.020`. This was an upstream LLM API status 500 error from WorkBuddy (`"model service unavailable"`; `flags.timed_out=false`).
- **Ledger De-duplication Note**: In `C:\Users\Du200\Projects\skeptic_runs\l71_hy3\ledger_hy3.csv`, multiple duplicate rows were recorded due to resume retries (each run row appears three times). If anyone totals token counts in subsequent analyses, these rows must be de-duplicated by `run_id`:
  - `none` (`20261113-010228-4d066f`): 363,110 tokens in, 76,167 tokens out (cost: $0.0).
  - `recommended` (`20261113-011801-780a6c`): 394,441 tokens in, 75,267 tokens out (cost: $0.0).
  - Combined de-duplicated tokens: 757,551 input tokens, 151,434 output tokens, total cost $0.0.

---

## hy4free Results and Why They Are Not a Quality Verdict

The outcomes recorded for `compat/hy4free`:

| Configuration | Run ID | Completed / Target Episodes | SUCCESS | ERROR | NO_ANSWER | SILENT_CORRUPTION | Error Breakdown |
|---|---|---|---|---|---|---|---|
| `none` | `20261111-235805-0926b0` | 446 / 446 | 10 | 434 | 1 | 1 | 394 timeouts (`flags.timed_out`), 40 MCP start failures |
| `recommended` | `20261112-052708-867a59` | 103 / 446 (interrupted) | 1 | 102 | 0 | 0 | 94 timeouts (`flags.timed_out`), 8 MCP start failures |

### Why This is NOT a Quality Verdict on hy4free or Guards

These results reflect an **infrastructure and timeout reliability breakdown**, NOT a quality verdict on `hy4free` or on guard efficacy:

1. **Timeout Mismatch**: The run used a 180s per-episode timeout. For `compat/hy4free` routed through the upstream relay, 180s proved insufficient for multi-turn tool interaction, leading to timeouts in 394 of 446 episodes under `none` and 94 of 103 episodes under `recommended`.
2. **MCP Launch Contention**: Concurrency 4 led to process contention during local MCP server startup, triggering 40 MCP start failures under `none` and 8 under `recommended`.
3. **Execution Interruption**: The `recommended` configuration was deadline-interrupted after only 103 of 446 episodes were logged to `results.jsonl`, generating no `summary.json`.
4. **Conclusion**: With over 97% of episodes terminating in timeout or process-launch errors before agent completion, the experiment yielded zero evaluable reasoning signal. This is an operational execution failure rather than a model capability finding.
5. **Ledger Status**: `C:\Users\Du200\Projects\skeptic_runs\l71_hy4free\ledger_hy4.csv` records only the completed `none` run (66,246 input tokens, 11,700 output tokens, cost $0.0); no row exists for the interrupted `recommended` run.

---

## Limitations

- **Small hy3 Sample**: The `hy3` run covered only a 10-scenario slice (84 episodes per guard config). The statistical sample is too small to draw conclusions regarding guard impact or model performance.
- **Interrupted hy4free Run**: The `hy4free` `recommended` configuration was truncated mid-run at 103/446 episodes due to deadline expiration, leaving incomplete results and no summary JSON.
- **No Significance Claimed**: Because confidence intervals overlap and outcome distributions are dominated by sample noise (hy3) or timeout aborts (hy4free), no statistical significance is claimed. No significance tests are conducted or warranted.
- **Cost $0.0**: Both models were evaluated strictly via zero-cost routes (`usage.credit=0` confirmed for `compat/hy4free` on 2026-11-11; $0.00 relay pricing for `compat/hy3`).
- **Single Seed and Profile**: All executions were restricted to seed 1 and profile `silent-core`.

---

## Reproduction Pointers

To inspect or reproduce these experimental matrix configurations:

- **Matrix Definitions**:
  - `bench/matrix/leaderboard-v1-reduced-free-hy3.yaml` (matrix ID: `leaderboard-v1-reduced-free-hy3`)
  - `bench/matrix/leaderboard-v1-reduced-free-hy4.yaml` (matrix ID: `leaderboard-v1-reduced-free-hy4`)
- **Suite Definitions**:
  - `bench/suites/core-v1-l71-hy3.yaml` (suite ID: `core-v1-l71-hy3`)
  - `bench/suites/core-v1-l71-reduced.yaml` (suite ID: `core-v1-l71-reduced`)
- **Model Registry**:
  - `bench/leaderboard/models.yaml` (entries `compat/hy3` and `compat/hy4free`, `tier: experiment`)
- **Disclaimer**: These matrices are internal diagnostic experiments. They must NOT be cited or published as official Skeptic S16.2 leaderboard evaluations.
