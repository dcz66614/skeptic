# X thread draft

Draft for H4. Ten posts. A human posts them, if they choose to.

1/ Skeptic is an MCP proxy. It injects tool faults, including results that still look successful, and scores whether the agent reports the bad value. Draft for H4.

2/ Scenario weather.forecast.paris-max.001 expects 14.5 °C and forbids 145.0. Fault S04 multiplies the first number by 10. Both figures are that scenario file, not a model score.

3/ This tree holds 20 faults, 10 sandboxes, and 200 scenarios. `skeptic faults list` prints the catalogue. Those counts are files, not a run.

4/ Published sample: compat/hy3, 30 scenarios, 10 guard configs, 482 episodes each. Table: docs/en/methodology/guards-ab.md.

5/ No guards, 482 episodes. FSR 8.54% (95% CI 3.14% to 15.58%). SKS 93.19 (95% CI 89.71 to 96.00), partial. Run 20261103-155316-3e96a4.

6/ All guards, 482 episodes. FSR 7.29% (95% CI 1.88% to 14.53%). SKS 92.68 (95% CI 88.87 to 95.88), partial. Run 20261103-162358-6c18bb.

7/ Those FSR intervals overlap. Closest row drops G01: FSR 8.56% (95% CI 3.09% to 15.87%), SKS 92.19. Run 20261103-165643-d4399c.

8/ recommended stays G02-G08. G01 stays off. src/skeptic_agent/guards/presets.py was left unchanged after this sample.

9/ Matrix profiles set include_clean to false, so these runs have no clean episodes. Summaries still print RR 0 and mark SKS partial. Run 20261103-155316-3e96a4.

10/ Version 0.1.0a1. From a checkout: uv sync, then uv run skeptic --version. Episode total, no model call: skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --count
