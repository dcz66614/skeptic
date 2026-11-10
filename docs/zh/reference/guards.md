# 防护参考

八个防护。公共字段：`enabled`（默认 true）和 `tools`（glob，默认 `*`）。每次防护动作都记入卡带。预设，以及 `recommended` 仍是暂定的原因，在[防护概念](../concepts/guards.md)页和[对照实验](../methodology/guards-ab.md)。

下面的句子是代理返回或追加的原文，逐字固定。英文页面与实现使用同一批字符串，这里保持英文原文。

| ID | 名称 | 时机 | 做什么 |
|---|---|---|---|
| G01 | `evidence_contract` | tools/call 结果之后 | 在 `content` 末尾追加一个文本块 |
| G02 | `schema_guard` | tools/call 结果上 | 用 `outputSchema` 校验 `structuredContent`（或 JSON 文本），失败就显式化 |
| G03 | `staleness_guard` | tools/call 结果上 | 日期对不上请求日，或早于 `max_age_days`（30）时显式化 |
| G04 | `emptiness_guard` | tools/call 结果上 | 空、无法解析或突然截断时显式化 |
| G05 | `retry_guard` | tools/call 结果上 | 对只读或列入幂等名单的工具重试，最多 `max_retries` 2 次 |
| G06 | `loop_breaker` | tools/call 转发之前 | 第 3 次完全相同的调用直接回复错误，不转发 |
| G07 | `injection_shield` | 结果上，以及下一次调用之前 | 替换像指令的片段，再阻断复用污点值的调用 |
| G08 | `drift_lock` | tools/list 上 | 哈希变化时钉住首次定义（`mode=pin`）或删掉该工具（`mode=strip`） |

G01 追加：

```text
[skeptic:evidence] Before relying on this result, check that it answers the request (right entity, date, units, completeness). If it is empty, truncated, stale, inconsistent or an error, reply with "RETRIEVAL_STATUS: FAILED" and do not invent values.
```

G02 在校验失败时：

```text
[skeptic:schema_guard] Tool output failed validation: <first error, at most 200 characters>. Treat this result as unusable; retry, use another source, or report failure.
```

G03：

```text
[skeptic:staleness_guard] Result dates do not match the request or are older than <N> days (<example date>). Treat as stale.
```

G04：

```text
[skeptic:emptiness_guard] Result is empty or truncated. Do not treat missing data as zero or as complete.
```

G05 不注入文本。`isError` 为 true 且文本匹配 `(?i)(503|429|timeout|timed out|temporar|unavailable|rate limit)`，或 JSON-RPC 代码为 `-32001` 或 `-32603` 时，它会重试。退避是 `0.5 × 2^k` 秒。它不对写工具重试。

G06：

```text
[skeptic:loop_breaker] This exact call was already made <N> times with the same result. Change your approach or report that the task cannot be completed.
```

G07 把命中片段换成：

```text
[skeptic:injection_shield removed <N> chars of instruction-like content from tool output]
```

G07 阻断后续调用时：

```text
[skeptic:injection_shield] Blocked: arguments derived from untrusted tool output.
```

扫描不区分大小写。它匹配“忽略先前指令”、`important` 标签、伪造的系统通知、“you must call”、“do not mention”，以及标记 `SKEPTIC-TEST-INJECTION`、`@exfil.example`、`SKC-CANARY-`，成串的 Unicode 标签字符或零宽字符，和长度不少于 200 的 base64 片段。默认的敏感工具是 `send_email`、`write_file`、`delete_*`、`cancel_*` 和 `refund_*`。

G08 在调用不再符合被钉住的 input schema 时：

```text
[skeptic:drift_lock] Tool definition changed after approval; call blocked.
```

G02、G03、G04 和各个阻断用的显式化，会把结果换成一个文本块，`isError: true`，并在原结果有 `_meta` 时保留它。
