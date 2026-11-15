# R80 Linux wheel + Quickstart (orchestrator box evidence)

Date: 2026-11-15 (Europe/London, UTC+0)
Source: git archive of d879d4c
Host: Linux box, Python 3.12.15 via uv, clean venv at /workspace/r80/clean
Wheel: skeptic_agent-0.0.0-py3-none-any.whl (built with `uv build --wheel`)

## What passed

- `skeptic --version` printed `0.0.0`
- `skeptic faults list` printed all 20 fault ids
- Default runtime install of the wheel resolved 47 packages and completed cleanly

## What failed

`skeptic scenario validate bench/scenarios/weather/weather.forecast.paris-max.001.yaml` crashed:

```
FileNotFoundError: [Errno 2] No such file or directory:
'/workspace/r80/clean/lib/python3.12/schemas/scenario.schema.json'
```

Cause: `src/skeptic_agent/scenario/validate.py` sets
`SCHEMA_FILE = Path(__file__).resolve().parents[3] / "schemas" / "scenario.schema.json"`.
That is the repo root in a source checkout, but in a wheel install it points at
`lib/python3.12/schemas/...`. The wheel also does not package the `schemas/`
directory (inspected namelist: no `*.schema.json`).

The same `parents[3]` repo-root pattern is used in other modules that Quickstart
`skeptic run` / `report` / `gate` will need after validate is fixed, including
(non-exhaustive): `runner/fake_llm.py` (`tests/fixtures/fake_scripts`),
`runner/episode.py` (`schemas/result.schema.json`, `bench/recoverability.json`),
`faults/profiles.py` (`schemas/profile.schema.json`).

R80 should fix packaging and path lookup so a clean venv with only the wheel
installed can run the Quickstart (FakeLLM). Do not invent a Linux pass.
Full command transcript: docs/reports/r80-quickstart-linux.log
