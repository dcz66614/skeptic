# The `realistic-2026` profile: how its weights were set

`realistic-2026` is the profile that draws faults with the mix we believe
mirrors 2026 production agents, so a run under it says "how does this agent hold
up under a typical spread of tool failures" rather than "how does it handle one
specific fault". This page records the weights, the sources behind them, and how
we intend to replace the guesswork with measured data. The fault definitions
themselves are in `faults.md`.

## What the profile does

The file is `src/skeptic_agent/data/profiles/realistic-2026.yaml`. It is a
`sampled` profile (S7.2): for each scenario and seed, the run draws three faults
with replacement, by weight, from one RNG seeded from the run seed, the scenario
id and the profile id (S7.4). Every entry uses `persistence: mixed` with
`permanent_p: 0.6`, so a given episode sees the chosen fault either permanently
or once.

```text
episodes per seed = sum over scenarios of samples_per_scenario (= 3)
```

`include_clean` is false: the clean baseline is what the `none` profile is for,
and the bench's recoverability work (S39) runs the baseline once per scenario
rather than three times per sampled profile.

## The weights

| Fault | What it is | Weight | Class |
|---|---|---|---|
| L01 | timeout | 0.10 | loud |
| L02 | jsonrpc_error | 0.05 | loud |
| L03 | tool_error | 0.10 | loud |
| L05 | rate_limited | 0.08 | loud |
| L06 | tool_missing | 0.04 | loud |
| L07 | schema_drift | 0.05 | loud |
| S01 | empty_ok | 0.08 | silent |
| S02 | truncated | 0.08 | silent |
| S03 | stale | 0.10 | silent |
| S04 | numeric_corruption | 0.07 | silent |
| S05 | wrong_entity | 0.05 | silent |
| S06 | redacted | 0.03 | silent |
| S07 | malformed_ok | 0.04 | silent |
| S08 | unit_swap | 0.03 | silent |
| S10 | phantom_write | 0.05 | silent |
| A01 | output_injection | 0.03 | adversarial |
| A02 | description_poisoning | 0.01 | adversarial |
| A03 | rug_pull | 0.01 | adversarial |
| **Total** | | **1.00** | |

L04 (`http_status`) is left out: it only applies over HTTP, and a stdio run
would have to drop every L04 episode, which would quietly shift the whole
distribution. Add it in a run that carries HTTP scenarios.

By class the mix is 0.42 loud, 0.53 silent, 0.05 adversarial. The silent share
is the largest because that is the side of the problem this project exists for:
silent failures are the ones agents report least and retry least (see below).

## Why these numbers: the argument, and where it is weak

**This is a hypothesis, not a measurement.** The 2026 papers the project book
cites tell us *which* kinds of failure are common and how agents respond to
them. None of them publishes a fault-frequency table over production MCP servers
that we could copy into weights. The numbers below are a qualitative reading of
those findings, rounded to hundredths and normalised to sum to 1. The plan calls
this out explicitly (F25): the weights are "an assumption from a qualitative
reading of the literature". Treat a `realistic-2026` score as "how this agent
does across a plausible 2026 mix", not as an estimate of its failure rate in the
wild.

### Loud versus silent

[29] Loud Failures, Quiet Failures reports agents notice 91.3% of explicit errors
but only 58.8% of plausible wrong values; [31] RITE says silent errors roughly
halve task success and are harder than explicit ones; [28] finds the dishonest
answer rate jumps to 45.3% when a tool returns `status:ok` with damaged content,
against 0% for `status:error`. Taken together the silent faults deserve more
weight than the loud ones. They get 0.53 against 0.42 only - not a large margin,
because loud faults are still the majority of what any monitoring system catches
and the profile should not starve the retry and fallback behaviour.

### The individual loud faults

- L01 timeout, 0.10, and L05 rate_limited, 0.08, are the two transport errors
  every MCP deployment meets; the runtime-failure reports summarised in [51]
  discuss them as routine. L05 is slightly lower because a rate limit, unlike a
  timeout, cannot masquerade as a hung server.
- L03 tool_error, 0.10, is the plain upstream error, the most common explicit
  failure in the MCP fault study [30].
- L02 jsonrpc_error, 0.05, is a protocol-level error; it is rarer than a tool
  error because servers usually wrap failures in the tool result.
- L06 tool_missing, 0.04, and L07 schema_drift, 0.05, are configuration and
  deployment drift. ToolBench-X [34] and the MCP fault study [30] both note
  servers whose tool surface does not match what the client expects. They are
  low because they need a deploy between the agent's discovery step and its
  call, but persistent enough to matter to a long-running agent.

### The individual silent faults

- S03 stale, 0.10: the highest silent weight. AgentCheck [32] finds retries do
  not help against stale data (success stuck at 3-4 of 10), and ToolMaze [35]
  is built around replanning when data is out of date; stale caches and
  last-known values are everywhere in production.
- S01 empty_ok, 0.08, and S02 truncated, 0.08: empty and partial results are the
  most common shape of "success with missing data"; [28] groups them with the
  `status:ok` cases that trigger fabrication.
- S04 numeric_corruption, 0.07: [28], [29], [31] all use wrong numbers as the
  canonical silent failure, but a wrong number is also the one a careful agent
  can sometimes catch by cross-checking, so it sits below stale/empty.
- S05 wrong_entity, 0.05: [31] and [38] both describe answers about the wrong
  object in multi-tool flows; a mid weight because it needs an entity-shaped
  query.
- S06 redacted, 0.03, and S08 unit_swap, 0.03: masking and unit confusion
  ([40], [39], [38]) are real but narrower - they need the right keys - so they
  are the smallest silent weights.
- S07 malformed_ok, 0.04: providers that return half-JSON are common enough to
  sit above masking and below truncation ([40]).
- S10 phantom_write, 0.05: [51]'s runtime-failure discussions, plus the RITE and
  fabrication findings, put writes that did not apply among the costliest and
  least noticed failures. It is held at a mid weight because write scenarios are
  a smaller share of the bench than reads (S37, S38 proportions).

### The adversarial faults

- A01 output_injection, 0.03: the injection that sits inside tool output, the
  case attacker-controlled data is most likely to hit.
- A02 description_poisoning, 0.01, and A03 rug_pull, 0.01: these need a
  compromised or changed server, which is rarer but the most severe when it
  happens ([27] studies malicious skills in the wild, [51] reports tools whose
  behaviour changed after publication). At 0.05 combined, an adversarial episode
  appears roughly once every 20 draws, so a three-draw profile meets one often
  enough to be scored but not so often that it drowns the rest.

## How to recalibrate with real incident data

The weights become a measurement when we have counts, not anecdotes. The
intended path:

1. **Collect episodes, not votes.** From cassette-based runs and real incident
   write-ups, record each failure with its fault id, its tool, and whether the
   agent recovered. A run of `realistic-2026` already tags every episode with the
   fault id, so runs under any profile produce this data.
2. **Estimate frequencies with uncertainty.** Use a Dirichlet-multinomial (or
   the same bootstrap in `scoring/bootstrap.py`) over fault counts, with a
   general-purpose prior. With few observations the posterior stays close to the
   current weights; with many it moves. This avoids a handful of loud incidents
   hijacking the mix.
3. **Condition on context.** Fault frequency depends on the tool class (reads vs
   writes vs cross-source) and the transport. Rather than one global table, allow
   a per-context table and produce `realistic-2026` as that table applied to the
   bench's scenario mix.
4. **Re-validate the agents' score.** When the weights change, re-run the
   leaderboard so rankings are comparable; record the weight table's version
   alongside each leaderboard run, exactly as model versions are recorded.
5. **Write an ADR.** Changing the built-in membership or weights of a frozen
   profile is an interface change (ADR-0002); publish the new table and the data
   behind it as a new ADR.

Until step 1 has enough data, the weights above stand as the documented default,
and every result produced under them should be read with the caveat in this
page.

## Sources

References are numbered as in the project book, section 16. Access dates there
are 2026-10-27.

- [27] Liu et al., *"Do Not Mention This to the User": Detecting and
  Understanding Malicious Agent Skills in the Wild*, USENIX Security 2026.
- [28] *Fabrication After Tool Failure: Tool-Augmented Agents Assert Values
  Their Tools Did Not Return*, arXiv:2609.14758.
- [29] *Loud Failures, Quiet Failures: Fault Detection and Recovery in
  Tool-Using Language Model Agents*, arXiv:2610.10062.
- [30] *Tool-Calling LLM Agents Under Realistic MCP Faults: Scale Does Not
  Purchase Fault Tolerance*, arXiv:2610.32555.
- [31] *RITE: Evaluating End-to-End Resilience to Silent Tool Errors in
  E-Commerce Agentic Systems*, arXiv:2610.27777.
- [32] *AgentCheck: A Reproduce-Intervene-Mitigate Workbench for LLM Agents over
  MCP*, arXiv:2607.11098.
- [35] *When Tools Fail: Benchmarking Dynamic Replanning and Anomaly Recovery in
  LLM Agents (ToolMaze)*, arXiv:2606.05806.
- [38] *ComplexMCP: Evaluation of LLM Agents in Dynamic, Interdependent, and
  Large-Scale Tool Sandbox*, arXiv:2605.10787.
- [39] *ToolFailBench: Diagnosing Tool-Use Failures in LLM Agents*,
  arXiv:2607.04686.
- [40] *Auditing Automated Evaluation, Error Propagation, and Runtime Mitigation
  in Tool-Using Language Agents (AgentProp-Bench)*, arXiv:2604.16706.
- [51] MCP fault studies: arXiv:2606.05339 (837 runtime-failure discussions from
  473 repositories) and arXiv:2603.05637 (classification of 407 MCP-related
  issues).

No other source is used for the weights. Citations above are to the findings as
the project book states them; we did not re-read the papers, so a number quoted
here should be checked against the paper before it appears in an external
publication.
