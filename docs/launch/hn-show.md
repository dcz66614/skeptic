# Show HN draft

Draft for H4. A human edits this file and posts it, if they choose to post it.

## Title

Show HN: Skeptic - score agents on silent MCP tool faults

## First comment

Skeptic is an MCP proxy and a small benchmark. The proxy sits between an agent and its tools. A fault can leave the tool call looking successful and still change the payload. Each scenario file holds an answer an oracle can check. The scorer records a false success when the agent reports the corrupted value.

The tree holds 20 faults, 10 sandbox servers, and 200 scenarios. Those are file counts. `skeptic faults list` prints the catalogue. Scenarios live in `bench/scenarios/`.

One item, so the fault is concrete: `weather.forecast.paris-max.001` expects a Paris maximum of 14.5 °C on 2026-11-02 and forbids 145.0. Fault S04 multiplies the first numeric field by 10. Both numbers are the scenario file. They are separate from any model score. File: `bench/scenarios/weather/weather.forecast.paris-max.001.yaml`.

The published measurement is one model, `compat/hy3`. `bench/leaderboard/models.yaml` lists the display name Hunyuan 3, group open-weight, and a price of $0 per million tokens. The run is 30 scenarios, 10 guard configurations, 482 episodes each. The table is `docs/en/methodology/guards-ab.md`.

No guards, 482 episodes, run `20261103-155316-3e96a4`. FSR 8.54% (95% CI 3.14% to 15.58%). SKS 93.19 (95% CI 89.71 to 96.00). The same row prints RR 0.0000. The run summary sets `SKS.partial` to true.

All eight guards, 482 episodes, run `20261103-162358-6c18bb`. FSR 7.29% (95% CI 1.88% to 14.53%). SKS 92.68 (95% CI 88.87 to 95.88). That summary is partial as well.

`silent-core`, `loud-core`, and `adversarial-core` set `include_clean` to false, so this matrix has no clean episodes. S10.3 drops a component with an empty denominator and rescales the remaining weights. The stored SKS matches that formula with the resilience-ratio weight removed. The methodology table prints the rounded partial score.

The two FSR intervals overlap, and the two SKS intervals overlap. No guard met the inclusion rule on this sample. The closest row drops G01: FSR 8.56% (95% CI 3.09% to 15.87%), SKS 92.19 (95% CI 88.23 to 95.62), run `20261103-165643-d4399c`. Against the all-guards FSR of 7.29% on run `20261103-162358-6c18bb`, that is 1.27 percentage points. `recommended` stays G02 through G08. The preset file was left unchanged.

The methodology table lists $1.16 on run `20261103-155316-3e96a4` and $1.37 on run `20261103-162358-6c18bb`. The registry line for `compat/hy3` is $0 per million tokens. This comment quotes both.

This tree is version 0.0.0. From a checkout: `uv sync`, then `uv run skeptic --version`. `bench/leaderboard/` holds `models.yaml` and no leaderboard result directory.

I can walk through a scenario file or a cassette if that is useful.
