# Linux clean-wheel Quickstart (R80)

## Earlier run (d879d4c, pre-packaging fix)

The first Linux clean-venv install of `skeptic_agent-0.0.0-py3-none-any.whl` from commit d879d4c failed at `skeptic scenario validate`. `SCHEMA_FILE` was resolved with `Path(__file__).resolve().parents[3]` and the wheel did not package `schemas/`. See the historical failure notes in the R80 worktree before the packaging fix.

## Re-run (a663957, after packaging fix)

Date: 2026-11-15 (Europe/London, UTC+0)
Host: Linux box, CPython 3.12.15
Source: `git archive` of `task/R80` at `a66395743b1b11258433ab187a3c1c86476447eb`
Wheel: `skeptic_agent-0.0.0-py3-none-any.whl` built with `uv build --wheel` on the box
Environment: clean virtualenv at `/workspace/r80-a663957/clean` with only that wheel installed (no editable checkout on `sys.path`)
Scenario YAML: from the extracted archive checkout (`bench/scenarios/weather/weather.forecast.paris-max.001.yaml`)
Command binary: `/workspace/r80-a663957/clean/bin/skeptic`

Confirmed packaged data is present in site-packages:
`skeptic_agent/data/schemas/scenario.schema.json` (and the other schema files), `skeptic_agent/data/recoverability.json`, and `skeptic_agent/data/fake_scripts/`.

Results (full transcript: `docs/reports/r80-quickstart-linux.log`):

- `skeptic --version` → `0.0.0`
- `skeptic faults list` → 20 faults
- `skeptic scenario validate` → PASS: 1 scenario(s) passed validation
- `skeptic run` (FakeLLM `reference:fake/oracle_follower`, profile `none`, seeds 1) → Run completed. SKS: 100.00, Episodes: 1
- `skeptic report` → 6 reports generated
- `skeptic gate --min-sks 70` → Gate check PASSED: SKS=100.00 >= 70.00, FSR=0.0000 <= 0.1000, ICR=0.0000 <= 0.0000

Verdict: PASS
