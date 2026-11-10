# Guard reference

Eight guards. Shared fields: `enabled` (default true) and `tools` (glob, default `*`). Every guard action is stored on the cassette. Presets and the reason `recommended` is provisional are on the [guards concept](../concepts/guards.md) page and in the [A/B write-up](../methodology/guards-ab.md).

The sentences below are the text the proxy returns or appends. They are fixed.

| ID | Name | When | What it does |
|---|---|---|---|
| G01 | `evidence_contract` | after a tools/call result | Appends a text block to `content` |
| G02 | `schema_guard` | on the tools/call result | Validates `structuredContent` (or JSON text) against `outputSchema`, and loudifies on failure |
| G03 | `staleness_guard` | on the tools/call result | Loudifies when dates miss the requested day or are older than `max_age_days` (30) |
| G04 | `emptiness_guard` | on the tools/call result | Loudifies on empty, unparseable, or sharply truncated results |
| G05 | `retry_guard` | on the tools/call result | Retries a read-only or listed idempotent tool, up to `max_retries` 2, on matching errors |
| G06 | `loop_breaker` | before the tools/call is forwarded | On the 3rd identical call, answers with an error and does not forward |
| G07 | `injection_shield` | on the result, and before the next call | Replaces instruction-like spans, then blocks calls that reuse tainted values |
| G08 | `drift_lock` | on tools/list | Pins the first definition (`mode=pin`) or drops the tool (`mode=strip`) when the hash changes |

G01 appends:

```text
[skeptic:evidence] Before relying on this result, check that it answers the request (right entity, date, units, completeness). If it is empty, truncated, stale, inconsistent or an error, reply with "RETRIEVAL_STATUS: FAILED" and do not invent values.
```

G02, when validation fails:

```text
[skeptic:schema_guard] Tool output failed validation: <first error, at most 200 characters>. Treat this result as unusable; retry, use another source, or report failure.
```

G03:

```text
[skeptic:staleness_guard] Result dates do not match the request or are older than <N> days (<example date>). Treat as stale.
```

G04:

```text
[skeptic:emptiness_guard] Result is empty or truncated. Do not treat missing data as zero or as complete.
```

G05 injects no text. It retries when `isError` is true and the text matches `(?i)(503|429|timeout|timed out|temporar|unavailable|rate limit)`, or when the JSON-RPC code is `-32001` or `-32603`. Backoff is `0.5 × 2^k` seconds. It does not retry write tools.

G06:

```text
[skeptic:loop_breaker] This exact call was already made <N> times with the same result. Change your approach or report that the task cannot be completed.
```

G07 replaces a match with:

```text
[skeptic:injection_shield removed <N> chars of instruction-like content from tool output]
```

G07 blocks a later call with:

```text
[skeptic:injection_shield] Blocked: arguments derived from untrusted tool output.
```

The scan is case-insensitive. It matches instructions to ignore previous directions, an `important` tag, a fake system notice, "you must call", "do not mention", the markers `SKEPTIC-TEST-INJECTION`, `@exfil.example`, and `SKC-CANARY-`, runs of Unicode tag or zero-width characters, and a base64 span of 200 characters or more. The default sensitive tools are `send_email`, `write_file`, `delete_*`, `cancel_*`, and `refund_*`.

G08, when a call no longer matches the pinned input schema:

```text
[skeptic:drift_lock] Tool definition changed after approval; call blocked.
```

Loudify, used by G02, G03, G04, and the blockers, replaces the result with one text block, `isError: true`, and keeps `_meta` when the original result had it.
