# Faults

Skeptic injects one fault per episode. A fault profile chooses which faults run. The clean profile `none` injects nothing and is the baseline.

Three classes:

- **Loud faults** (`L01`–`L07`). The client sees an error, a timeout, a missing tool, or a changed argument schema. The failure is visible.
- **Silent faults** (`S01`–`S10`). `isError` stays absent or false, and content blocks keep their types. The data is empty, truncated, old, scaled, swapped, masked, malformed, or a write that reported success and changed nothing.
- **Adversarial faults** (`A01`–`A03`). A fixed test sentence is planted in tool output or a tool description. It matters when the agent follows instructions that arrived inside tool data. The payloads use the reserved `.example` domain and a fictional canary file.

A fault that cannot be applied (no date to shift, no number to scale) is recorded as not applicable and stays out of the metric denominators.

The [fault catalogue](../reference/faults.md) lists every id, its default persistence, and the behaviour a correct agent shows. Parameter-level algorithms and the literature map are in the [fault notes](../methodology/faults.md). Built-in profiles, including the weighted `realistic-2026` mix, are described with those notes and on the [realistic profile](../methodology/realistic-profile.md) page.

```text
skeptic faults list
skeptic faults list --class silent
skeptic run --profile silent-core ...
```
