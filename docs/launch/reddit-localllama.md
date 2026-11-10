# r/LocalLLaMA draft

Draft for H4. A human posts this, if they choose to.

## Title

Skeptic scores silent MCP tool faults. The published run is one OpenAI-compatible model.

## Post

Skeptic is an MCP proxy plus a scenario suite. It can pass a tool call through, or it can change the payload while the call still looks successful. A scenario file holds the answer. The scorer marks a false success when the agent reports the corrupted value.

If you already run an OpenAI-compatible server, the reference adapter takes `reference:compat/<name>` and reads `SKEPTIC_COMPAT_BASE_URL` plus `SKEPTIC_COMPAT_API_KEY`. That is the hook. This post's numbers are for one id only: `compat/hy3`. `bench/leaderboard/models.yaml` lists the display name Hunyuan 3, group open-weight, tier dev, tools on, and $0 per million tokens in and out. The methodology page also names `compat/deepseek-v4-pro` and `compat/gpt-5.6-terra` as the pair the original matrix planned. The executed table contains `compat/hy3` alone. I am not reporting a llama.cpp, Ollama, or other local server run, because this tree does not have one.

The executed matrix is `bench/matrix/guards-ab-free.yaml`: 30 scenarios, three fault profiles (`silent-core`, `loud-core`, `adversarial-core`), ten guard configurations, 482 episodes each. The count command prints `Total episodes: 4820` and does not call a model. The write-up is `docs/en/methodology/guards-ab.md`.

No guards, run `20261103-155316-3e96a4`, 482 episodes. FSR 8.54% (95% CI 3.14% to 15.58%). SKS 93.19 (95% CI 89.71 to 96.00). The row also prints RR 0.0000. The summary sets `SKS.partial` to true.

All eight guards, run `20261103-162358-6c18bb`, 482 episodes. FSR 7.29% (95% CI 1.88% to 14.53%). SKS 92.68 (95% CI 88.87 to 95.88). That summary is partial too.

Those three profiles set `include_clean` to false in `src/skeptic_agent/data/profiles/`. The matrix has no clean episodes. S10.3 drops a component with an empty denominator and rescales. The stored SKS matches the formula with the resilience-ratio weight removed, which is why a partial 93 can sit next to a printed RR of 0.0000 on run `20261103-155316-3e96a4`.

The two FSR intervals overlap. No guard cleared the inclusion rule on this sample. The closest row drops G01 (`evidence_contract`): FSR 8.56% (95% CI 3.09% to 15.87%), SKS 92.19 (95% CI 88.23 to 95.62), run `20261103-165643-d4399c`. From the all-guards FSR of 7.29% on run `20261103-162358-6c18bb`, that rise is 1.27 percentage points. `recommended` stays G02 through G08. `src/skeptic_agent/guards/presets.py` was left as it was.

On the run summary for `20261103-155316-3e96a4`, SafeRate is 86.25% (95% CI 78.30% to 92.96%). On `20261103-162358-6c18bb`, SafeRate is 85.83% (95% CI 77.89% to 92.72%). SafeRate counts faulted, triggered episodes whose outcome is success or an honest failure. It is a summary field. The methodology table prints FSR and SKS, not SafeRate.

The methodology table lists $1.16 on run `20261103-155316-3e96a4` and $1.37 on run `20261103-162358-6c18bb`. The registry price for this id is $0 per million tokens.

Version in this tree is 0.0.0. From a checkout:

```bash
uv sync
uv run skeptic --version
uv run skeptic bench run --matrix bench/matrix/guards-ab-free.yaml --count
```

A scripted agent with no network is `reference:fake/oracle_follower`. A live compat endpoint is `reference:compat/<name>` plus the two environment variables above, and `skeptic run` wants `--max-cost-usd`. If you point that at a server you actually run, I would like to hear the run id and the FSR interval, with the same suite and the same seeds, more than I would like a single screenshot.
