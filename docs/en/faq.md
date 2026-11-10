# FAQ

## What is a silent fault?

The tool result still looks successful. `isError` is absent or false, and the content blocks keep their types, while the values are empty, old, scaled, or otherwise wrong. The agent that repeats those values without noticing is the case Skeptic is built to catch. The three classes are on the [faults](concepts/faults.md) page.

## How do I run a score without an API key?

Use FakeLLM. The [quickstart](quickstart.md) runs one weather scenario as `reference:fake/oracle_follower`. Other local scripts are `fake/gullible`, `fake/honest`, and `fake/looper`.

## Which servers can I point this at?

Skeptic's own sandboxes, and MCP servers you list in `skeptic.yaml` because you operate them. It is not a tool for injecting faults into someone else's service. Payloads in the adversarial faults use the reserved `.example` domain.

## Two runs of the same agent disagreed. What now?

A live model is random. Compare runs with more than one seed and read the confidence interval on SKS. Overlapping intervals are one rank group on the leaderboard, not two different winners.

## What does exit code 10 mean?

`skeptic gate` refused the run. The Skeptic Score was under `--min-sks`, the false-success rate was over `--max-fsr`, or the injection-compliance rate was over `--max-icr`. The other exit codes are in the [CLI reference](reference/cli.md).
