# Guards

A guard is a proxy step that runs on a tool call or a tool list. Guards make bad results explicit, retry a read that failed out loud, stop a repeated identical call, strip instruction-like text, or pin a tool definition that changed after the first listing.

Eight guards, `G01`–`G08`. The [guard reference](../reference/guards.md) quotes the text each guard returns. They run in a fixed order around the fault hooks: loop breaking and taint blocking happen before a call is forwarded; schema, staleness, and emptiness checks happen on the way back, after any retry.

Three presets:

| Preset | Guards |
|---|---|
| `none` | no guards |
| `all` | G01–G08 |
| `recommended` | G02–G08 (`schema_guard`, `staleness_guard`, `emptiness_guard`, `retry_guard`, `loop_breaker`, `injection_shield`, `drift_lock`) |

`recommended` leaves out G01 (`evidence_contract`) because that guard appends text to the tool result. The [guards A/B](../methodology/guards-ab.md) page records the ablation that kept this composition provisional: on the executed run, no single guard met the inclusion rule, and the confidence intervals overlapped.

Pass a preset or a comma-separated list:

```text
skeptic run --guards recommended ...
skeptic run --guards schema_guard,emptiness_guard ...
skeptic proxy stdio --guards recommended -- python -m skeptic_agent.sandboxes.sb_weather
```
