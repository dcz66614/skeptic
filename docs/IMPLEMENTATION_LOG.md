# 实现记录

## T00 仓库脚手架（2026-10-28）

本地分支 `codex`，基线 `976297a`。未创建 GitHub 仓库，未推送，未做包名查重。包名保持 `skeptic-agent`，导入名 `skeptic_agent`，命令 `skeptic`。

本地环境用 `uv lock` 后 `uv sync --extra dev`（解释器 CPython 3.12.13，虚拟环境在本工作区 `.venv`）。`scripts/check.sh` / `scripts/check.ps1` 与 CI 一样执行 `uv sync --locked --all-extras`，本次没有跑这两个脚本，也没有跑 live 测试。

Ruff 0.17 会改写 Markdown 里的 Python 片段。`docs/plan` 已从 Ruff 排除，计划书原文不改。已安装的 pytest-asyncio 1.4 要求写出 `asyncio_default_fixture_loop_scope`，设为 `function`。

### 命令与输出

```text
===== uv lock --check =====
EXIT=0

===== uv run skeptic --version =====
0.0.0
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
9 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 2 source files
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
..                                                                       [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                            Stmts   Miss  Cover
---------------------------------------------------
src\skeptic_agent\__init__.py       1      0   100%
src\skeptic_agent\cli.py            9      0   100%
---------------------------------------------------
TOTAL                              10      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
2 passed in 0.40s
EXIT=0
```

## T00fix 去掉 crewai extra 的 AGPL 依赖（2026-10-28）

基线 `faeb2ab`，分支 `codex`。计划书 1.2 的 `[crewai]` 含 `crewai-tools[mcp]`，锁到 `crewai-tools` 1.6.1，硬依赖 `pymupdf` 2.0（AGPL），与 1.4 冲突。extra 改为 `crewai` + `mcpadapt`。决定见 ADR-0006。未改计划书正文，未推送。

`uv lock` 去掉 `crewai-tools`、`pymupdf` 以及只被这条链拉进来的包。`Select-String uv.lock -Pattern 'name = "pymupdf"'` 无输出。对锁内 195 个包查了 PyPI 的 `license`、`license_expression` 和 License 分类，没有其他 GPL/AGPL，也没有 LGPL，请求无失败。`uv lock` 打印警告：`mcp==2.3.0` 没有名为 `ws` 的 extra。未为此改依赖。

未跑 live 测试，未跑 `scripts/check.ps1`。

### 命令与输出

```text
===== uv lock =====
Resolved 195 packages in 5.21s
warning: The package `mcp==2.3.0` does not have an extra named `ws`
Removed beautifulsoup4 v4.15.0
Removed crewai-tools v1.6.1
Removed defusedxml v0.7.1
Removed deprecation v2.1.0
Removed docker v7.2.0
Removed lance-namespace v0.13.0
Removed lance-namespace-urllib3-client v0.13.0
Removed lancedb v0.40.0
Removed lxml v6.1.3
Removed networkx v3.7
Removed psutil v7.2.2
Removed pyarrow v26.0.0
Removed pymupdf v2.0
Removed pymupdf-layout v2.0
Removed pymupdf4llm v2.0
Removed python-docx v1.2.0
Removed pytube v15.0.0
Removed soupsieve v3.0.4
Removed tabulate v0.10.0
Removed youtube-transcript-api v1.2.4
EXIT=0

===== Select-String uv.lock -Pattern 'name = "pymupdf"' =====
(no output)

===== PyPI license scan of uv.lock =====
PACKAGES 195
HITS 0
LGPL_ONLY 0
ERRORS 0

===== uv lock --check =====
Resolved 195 packages in 0.82ms
EXIT=0

===== uv sync --extra dev =====
Resolved 195 packages in 0.79ms
Checked 65 packages in 4ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
10 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 2 source files
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
..                                                                       [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                            Stmts   Miss  Cover
---------------------------------------------------
src\skeptic_agent\__init__.py       1      0   100%
src\skeptic_agent\cli.py            9      0   100%
---------------------------------------------------
TOTAL                              10      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
2 passed in 0.38s
EXIT=0
```

## Merge record T00 + T00fix (orchestrator, 2026-10-28 UTC)
- Commits: faeb2ab (T00, grok-4.7 high), c7ca525 (T00fix, grok-4.7 high; opencode attempt2 produced no output and was stopped).
- Review 1 T00: Copilot VERDICT: FAIL (pymupdf AGPL via crewai-tools) -> T00fix. Copilot review T00fix: VERDICT: PASS. Orchestrator: PASS (uv lock --check ok; ruff ok; ruff format ok; mypy ok; pytest 2 passed, coverage 100%).
- Fast-forwarded codex into main. GitHub CI not run yet (no repo; push needs Cd approval).

## T02 规格冻结：ADR 与 JSON Schema（2026-10-28）

基线 `5813dd1`，分支 `codex`。未推送，未改计划书正文。

裁决见 ADR-0001 至 ADR-0005。两处规格冲突：S1 的 schemas 注释是 8 个，T02 与 S16.1 要 9 个，补上 `schemas/models.schema.json`。场景、套件和可恢复性缓存放在仓库根 `bench/`（`bench/scenarios/`、`bench/suites/`、`bench/recoverability.json`），不建 `src/skeptic_agent/bench/`。R0 需把这两条写回计划书副本。

`uv.lock` 中的 `mcp` 为 2.3.0。高层服务器类是 `mcp.server.mcpserver.MCPServer`，高层客户端是 `mcp.Client`（`mode` 默认 `"auto"`）。`import mcp.server.fastmcp` 会失败。

Schema 为 JSON Schema Draft 2020-12，共 9 个。示例里的有效文档取自 S3、S5、S7.1、S8.1、S10.1、S16.1、S16.2；S10.1 的 episode id 用 S5 头里的完整值。报告和 findings 的字段名按 ADR-0003。未跑 live 测试，未跑 `scripts/check.ps1`。

### 命令与输出

```text
===== uv lock --check =====
Resolved 195 packages in 0.99ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
16 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 2 source files
EXIT=0

===== uv run pytest tests/schemas -q =====
...........................                                              [100%]
27 passed in 0.45s
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
.............................                                            [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                            Stmts   Miss  Cover
---------------------------------------------------
src\skeptic_agent\__init__.py       1      0   100%
src\skeptic_agent\cli.py            9      0   100%
---------------------------------------------------
TOTAL                              10      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
29 passed in 0.82s
EXIT=0

===== schema count =====
cassette.schema.json
config.schema.json
findings.schema.json
matrix.schema.json
models.schema.json
profile.schema.json
report.schema.json
result.schema.json
scenario.schema.json
COUNT=9
```


## Merge record T02 (orchestrator, 2026-10-28 UTC)
- Commit: db88e53 (T02, grok-4.7 high; base 5813dd1). 37 files, 9 schemas, ADR-0001..0005.
- Review 1: opencode workbuddy/deepseek-v4.1-flash (free, credit 0) read-only: attempt1 no verdict (ran out of turns probing); attempt2 VERDICT: PASS, worktree unmodified. Copilot not used (free-models-only rule).
- Orchestrator: PASS. uv lock --check ok; ruff ok; ruff format ok (16 files); mypy ok; pytest tests/schemas 27 passed; full suite 29 passed, coverage 100%; 9 schema files; negative probes (bad outcome/fault id/run_id/check type/persistence/scenario id) all rejected.
- Fast-forwarded codex into main.


## P10 JSON-RPC 消息模型与 canonical JSON（2026-10-28）

基线 `b8ff3ce`，分支 `codex`。未推送，未改计划书正文。

新增 `src/skeptic_agent/jsonrpc.py`（pydantic v2 模型 `Request`、`Notification`、`Response`、`ErrorResponse`，`ParseError`，`parse_line`、`dump`）与 `src/skeptic_agent/canonical.py`（`canonical_json`、`stable_hash`）。S4.1 的“未修改消息按原始字节透传”由 `raw_bytes` 字段承载：模型冻结、允许额外字段（透传 `_meta`、`resultType` 等未来成员），`dump` 排除 `raw_bytes`，`None` 的 `params` 不输出，其余成员（含 `"result":null`、`"id":null`、`error.data`）原样保留。

实现中需要写回后续任务的几点：

- `id` 用 `Annotated[int | str, AfterValidator]` 包一层，否则 pydantic 的左优先联合会把 `"7"` 收窄成整数 `7`，回写时改变字节类型。
- `Message`、`MessageId`、`NullableId` 用旧式 `TypeAlias` 并显式 `# noqa: UP040`。PEP 695 的 `type` 别名在运行时不能被 `isinstance` 使用，P12/P13 的派发需要 `isinstance(msg, Message)`。
- 不编造 JSON-RPC 错误码（-32600/-32601 等）的自发响应，`ParseError` 只携带 `raw_bytes` 与 `reason`，交给 P12 决定如何透传。
- `parse_line` 只去掉行尾 `\n` 与 `\r`，保存进 `raw_bytes` 的字节与 S4.1 一致；`dump` 用 `model_dump()`（非 `mode="json"`），避免 `inf`/`nan` 被静默改成 `null`，非法值直接抛 `TypeError`。
- hypothesis 的数值策略排除 `NaN` 与无穷，它们不是合法 JSON。往返测试比较语义键，不比较 `raw_bytes`；`params` 为 `None` 时显式断言输出里没有 `"params"`。

### 命令与输出

```text
===== uv lock --check =====
Resolved 195 packages in 0.78ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
20 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 4 source files
EXIT=0

===== uv run pytest tests/unit/test_jsonrpc.py tests/unit/test_canonical.py -q =====
...........................                                              [100%]
27 passed in 0.81s
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
........................................................                 [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                             Stmts   Miss  Cover
----------------------------------------------------
src\skeptic_agent\__init__.py        1      0   100%
src\skeptic_agent\canonical.py       7      0   100%
src\skeptic_agent\cli.py             9      0   100%
src\skeptic_agent\jsonrpc.py        72      0   100%
----------------------------------------------------
TOTAL                               89      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
56 passed in 1.71s
EXIT=0
```

## P10fix 接受位置参数（2026-10-28）

基线 `e411778`，分支 `codex`。未推送。

复审指出 `Request` 与 `Notification` 的 `params` 只接受对象，JSON-RPC 2.0 的 `params` 可以是对象或数组。两个模型的 `params` 改为 `dict[str, Any] | list[Any] | None`，其余行为不变：`dump` 在 `params` 为 `None` 时仍然不输出该成员。`tests/unit/test_jsonrpc.py` 补两条测试，分别覆盖请求与通知的数组 `params` 解析与回写。`.gitignore` 加 `.hypothesis/`。未跑 live 测试。

### 命令与输出

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
20 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 4 source files
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
..........................................................               [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                             Stmts   Miss  Cover
----------------------------------------------------
src\skeptic_agent\__init__.py        1      0   100%
src\skeptic_agent\canonical.py       7      0   100%
src\skeptic_agent\cli.py             9      0   100%
src\skeptic_agent\jsonrpc.py        72      0   100%
----------------------------------------------------
TOTAL                               89      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
58 passed in 2.26s
EXIT=0
```
## Merge record P10 + P10fix (orchestrator, 2026-10-28 UTC)
- Commits: e411778 (P10), 02ceddd (P10fix). Both by opencode workbuddy/deepseek-v4.1-flash (free, credit 0); Grok not needed.
- Review P10 (wb deepseek, read-only): VERDICT: FAIL (array params rejected) -> P10fix. Review P10fix: VERDICT: PASS. Worktrees unmodified.
- Orchestrator: PASS. ruff ok; ruff format ok (20 files); mypy ok (4 files); pytest 58 passed, coverage 100%.

## P11 协议时代识别（2026-10-28）

基线 `9131d5d`，分支 `codex`。未推送，未改计划书正文，未跑 live 测试。

新增 `src/skeptic_agent/protocol.py`：冻结的 `Era(kind, version)`，`kind` 取 `"LEGACY"` / `"MODERN"` / `"UNKNOWN"`，`version` 在 UNKNOWN 时为 `None`；常量 `UNKNOWN`、`MODERN_SINCE = "2026-07-28"`。`detect_era(first_client_message, http_headers=None)` 按 S4.2 伪代码逐条实现：先看 HTTP 头（名字转小写后匹配），`v >= "2026-07-28"` 走字符串比较决定 MODERN / LEGACY；再看首条消息的 `initialize`、`server/discover`、`params._meta["io.modelcontextprotocol/protocolVersion"]`，都不命中返回 UNKNOWN。请求头优先于消息体。

实现取舍：

- 版本比较直接用 `>=`，不做日期解析。计划书说明 `YYYY-MM-DD` 按字典序比较即可。
- 没有对 `protocolVersion` 做类型转换：消息虽然来自 P10 模型，但 `params` 是 `Any`，这里直接取值赋给 `version`，避免出现伪代码之外的机制。`params` 为 `None` 或数组时当作空对象，因此不会命中 `_meta`。
- 头名用小写映射查找，不依赖 HTTP 库是否已规范化大小写。
- 新增 fixture `tests/fixtures/protocol/{legacy_init,modern_discover,modern_meta_call,unknown}.json`，每个文件一条 JSON-RPC 消息，`legacy_init` 用 `2025-11-25`。测试从磁盘读 fixture，不读 TEMP。

### 命令与输出

```text
===== uv lock --check =====
Resolved 195 packages in 0.83ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
22 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 5 source files
EXIT=0

===== uv run pytest tests/unit/test_protocol.py -q =====
.............                                                            [100%]
13 passed in 0.91s
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
.......................................................................  [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                             Stmts   Miss  Cover   Missing
--------------------------------------------------------------
src\skeptic_agent\__init__.py        1      0   100%
src\skeptic_agent\canonical.py       7      0   100%
src\skeptic_agent\cli.py             9      0   100%
src\skeptic_agent\jsonrpc.py        72      0   100%
src\skeptic_agent\protocol.py       40      0   100%
--------------------------------------------------------------
TOTAL                              129      0   100%
Required test coverage of 85.0% reached. Total coverage: 100.00%
71 passed in 1.98s
EXIT=0
```



## Merge record P11 (orchestrator, 2026-10-28 UTC)
- Commit: 3933c96 (P11, opencode workbuddy/deepseek-v4.1-flash, free). Review (wb deepseek, read-only): VERDICT: PASS, worktree unmodified. Orchestrator: PASS (ruff ok; format ok 22 files; mypy ok 5 files; pytest 71 passed, coverage 100%).


## P12 拦截管线与 episode 上下文（2026-10-28）

基线 `5684425`，分支 `codex`。未推送，未改计划书正文，未跑 live 测试。

新增 `src/skeptic_agent/proxy/__init__.py`、`proxy/context.py`、`proxy/pipeline.py` 与 `tests/unit/test_pipeline.py`。

`context.py`：冻结的 `PendingCall(method, tool_name, arguments, t_start, attempt)`；`EpisodeContext` 保存 `episode_id`、`seed`、`era`、`scenario`（`Any`，缺省 `None`）、`pending`（键为 `(direction, id)`，按 S4.3）、`call_counts`、`taint`、`tool_defs`（按卡片要求为 `dict[str, Any]`）。`next_call_index(tool)` 先加后取，首次返回 1。`new_internal_id()` 返回 `skeptic-<uuid4>`，前缀常量 `INTERNAL_ID_PREFIX` 同时供管线判断内部响应。

`pipeline.py`：动作类型 `Forward`、`ReplyToClient`、`SendToServer`、`Drop`、`Hold(ms, then)` 都是小 dataclass，`Action` 为五者联合。`Interceptor` 是只有 `on_c2s` / `on_s2c` 两个 async 方法的 Protocol；`FaultStage`、`GuardStage`、`RecorderStage` 是三个挂载点，默认实现都只返回 `[Forward(msg)]`（Recorder 默认什么也不记）。`_run` 依次调用各阶段：阶段返回单个 `Forward(next)` 就把 `next` 交给下一阶段，返回其它动作则结束链条并原样返回。`Pipeline` 按 S4.4 排顺序：c2s 的 `tools/call` 走 recorder → guard → fault；s2c 的 `tools/call`、`tools/list` 响应走 fault → guard → recorder（Recorder 因此只看到最终消息）；其余消息只走 recorder。响应按 pending 表中的 c2s 请求判定，命中即从 pending 删除；`id` 以 `skeptic-` 开头的响应一律 `Drop()`，不会交给客户端。

实现取舍：

- 同一条消息在整条链上只产出一个 `Forward`，链条中每一步用上一阶段的 `Forward.msg` 作为下一阶段的输入。这样改写能被后续阶段看到，透传时返回的仍是同一个消息对象，`raw_bytes` 不变。
- `Pipeline.__init__` 要求三个阶段，`new_pipeline()` 负责补默认（类似 `dataclasses.field(default_factory=...)`）。这样类型标注直接是具体阶段类，`mypy --strict` 干净。
- 「c2s 的 `tools/list`」表格里没写顺序，卡片要求 s2c `tools/list` 响应走 fault → guard → recorder，因此请求侧也按 recorder → guard → fault 处理，并记入 pending（`attempt=0`），以便响应能匹配上；`tools/list` 不计入 `call_counts`。
- `call_index` 只在 `tools/call` 真正被转发时自增；Guard 直接回复、丢弃或 Hold 时不计，符合「转发到上游的第 n 次尝试」。
- `send_to_server(method, params)` 同步构造内部请求，id 用 `new_internal_id()`；没有做额外机制。
- 测试用共享列表记录阶段调用顺序，覆盖透传同对象、`ReplyToClient`、内部 id 被丢弃、三个方向的顺序、`call_index` 1/2/3、改写向下传递、Hold/Drop 断链。测试全部用内存构造的消息，不读 TEMP。

### 命令与输出

```text
===== uv lock --check =====
Resolved 195 packages in 0.85ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
26 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 8 source files
EXIT=0

===== uv run pytest tests/unit/test_pipeline.py -q =====
......................                                                   [100%]
22 passed in 0.38s
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
........................................................................ [ 77%]
.....................                                                    [100%]
______________ coverage: platform win32, python 3.12.13-final-0 _______________

Name                                  Stmts   Miss  Cover
---------------------------------------------------------
src\skeptic_agent\__init__.py             1      0   100%
src\skeptic_agent\canonical.py            7      0   100%
src\skeptic_agent\cli.py                  9      0   100%
src\skeptic_agent\jsonrpc.py             72      0   100%
src\skeptic_agent\protocol.py            40      0   100%
src\skeptic_agent\proxy\__init__.py       0      0   100%
src\skeptic_agent\proxy\context.py       29      0   100%
src\skeptic_agent\proxy\pipeline.py     104      4    96%
---------------------------------------------------------
TOTAL                                   262      4    98%
Required test coverage of 85.0% reached. Total coverage: 98.47%
93 passed in 2.02s
EXIT=0
```

## P12fix - record-only c2s tools/list (S4.4)

The S4.4 table has no c2s `tools/list` row, so it falls under "all other
messages: only record, pass through unchanged". `Pipeline.on_c2s` now runs the
recorder alone for a c2s `tools/list` and no longer runs guard/fault there. It
still registers the pending call with `attempt=0` before forwarding, so the
matching s2c response keeps running fault, guard, recorder. `tools/call`
handling is unchanged. `tests/unit/test_pipeline.py` asserts the c2s stage log
is exactly `["recorder:c2s"]` and the s2c response log stays
`["fault:s2c", "guard:s2c", "recorder:s2c"]`.

Checks: `ruff check`, `ruff format --check`, `mypy src` clean; `pytest -m
"not live" -q --cov=skeptic_agent` 93 passed, 98.48% coverage.

## Merge record P12 + P12fix (orchestrator, 2026-10-28 UTC)
- Commits: 62f2dc9 (P12), b754706 (P12fix). Both opencode workbuddy/deepseek-v4.1-flash (free).
- Review P12 (wb deepseek): VERDICT: PASS. Orchestrator: FAIL - c2s tools/list ran guard+fault, S4.4 says record only -> P12fix. Review P12fix (wb deepseek): VERDICT: PASS; orchestrator PASS (ruff ok; format ok 26 files; mypy ok 8 files; pytest 93 passed, coverage 98.48%).
- Open point for F20: call_index is incremented only after the fault pre-hook stage decides to forward; F20 must define how pre-hook faults (S05, S10, L06, L07, L04) see call_index.

## F20 故障引擎框架与调度（2026-10-28）

基线 `aa0b913`，分支 `codex`。未推送，未改计划书正文，未跑 live 测试，未读 TEMP。上一会话的未提交实现保留，并补上四处会让验收失败的行为。

`docs/adr/ADR-0007-call-index.md`（状态：采纳）。S4.3 的 `call_index` 按本 ADR 解释为：一次 `tools/call` 在 G06/G07 放行之后、故障前置钩子运行之前计数。编号同时放在 `ctx.current_call_index[tool]` 和 `PendingCall.attempt`。被 Guard 拦下的尝试不计；G05 重试重新进入第 ④ 步时照常计数。故障阶段直接回复客户端时这次尝试也计入。s2c 链运行期间匹配的 pending 仍留在 `ctx.pending`，后置钩子用它的 `attempt` 回写 `current_call_index`，链返回前再删除。`FaultStage.counts_attempts()` 默认 `False`，返回 `True` 的阶段自己计数。

交付：`faults/base.py`、`faults/schedule.py`、`faults/profiles.py`、`faults/registry.py`、`faults/engine.py`、`jsonsel.py`，以及 `tests/unit/test_schedule.py`、`test_profiles.py`、`test_jsonsel.py`、`test_engine.py`。注册表为空，F21–F24 再填 20 个故障。`load_profile_source` 供以后的 CLI `--profile` 使用，本卡不加新命令。不实现 L01–A03。

调度按测试锁定的 S6 读法：`when.call_index` 先筛尝试；`when.probability` 再对每一次合格尝试掷一次。`permanent` 一直保持；`transient` 只放行前 `n` 次触发（默认 1）；`intermittent` 每一次合格尝试以 `p`（默认 0.5）触发，包括第一次，所以 `p=0` 一次都不触发；`mixed` 在第一次掷骰前以 `permanent_p`（默认 0.6）选定 permanent，否则按 `transient(n=1)`。RNG 只有 `fault_rng`：`random.Random(int(sha256(f"{seed}|{episode_id}|{fault_id}|{tool}").hexdigest()[:16], 16))`。`tools/list` 不是一次 tools/call，走 `Schedule.next_event`，不计 `when.call_index`。

画像展开按 S7.4：`include_clean`、`per_fault` 每个故障一条、`sampled` 用同一个 `Random(sha256(f"{k}|{s.id}|{p.id}"))` 连续抽 `samples_per_scenario` 次（种子取摘要前 64 位，和 S7.3 一样宽，因为 `random.Random` 要的是 int）。静态适用性：L04 要 HTTP，L07 要目标工具至少有一个必填参数（空列表不算），S05 要 `entity_arg` 和 `decoys.entity`，S09 要 `conflict_pair`，S10 要 `write_tools`。不适用的 episode 不生成。

目标：`$primary` 无场景时为 `*`，`$write` 为 `write_tools`，`$conflict_b` 为 `conflict_pair[1]`，工具名按 glob 匹配。

依赖与 schema：

- 不改 `uv.lock`。`jsonpath-ng` 已在 T00 锁定，本卡只是用它。
- 不增加 `types-jsonschema` / `types-pyyaml`。`jsonpath-ng`、PyYAML、`jsonschema` 都没有 `py.typed`，`pyproject.toml` 用 `ignore_missing_imports` 让 `mypy --strict` 通过。
- 撤回 `schemas/profile.schema.json` 里 sampled 模式的 `faults.minItems: 1`。S7.1 没有这条，T02 已冻结该 schema。缺少 `samples_per_scenario`、`faults` 不是数组，仍会被现有 schema 拒绝；权重和为 0 时 `expand` 抛 `ProfileError`。

补上的缺陷：引擎命中调度后会调用 `apply`（前置钩子因此能读到 `call_index`）；L07 不再把“没有必填参数”判成适用（`all([])` 在 Python 里是 `True`）；sampled 的多次抽样共用一个 RNG，不再每次用同一个种子重抽到同一条故障。

### 命令与输出

```text
===== uv lock --check =====
Resolved 195 packages in 6ms
EXIT=0

===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
38 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 15 source files
EXIT=0

===== uv run pytest tests/unit -q =====
131 passed in 1.63s
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
158 passed in 2.54s
Required test coverage of 85.0% reached. Total coverage: 97.27%
EXIT=0
```


## F20fix 首次触发后的持续与按工具取 RNG（2026-10-28）

按 `REVIEW_F20_ref.md` 修正 S6 持续规则与 S7.3 RNG 键。

- `schedule.py`：`when.call_index` 现在只在 `triggered == 0`（首次触发前）生效；首次触发后完全由持续模式决定。`transient(n)` 从首次触发起连续 n 次，`intermittent` 首次触发后每次按 p 判定，`mixed` 按已选分支。
- `schedule.py`：`is_active_after` 在首次触发前对所有模式都返回可用，`intermittent` 的 p 只在首次触发之后参与判定，不再在触发前消耗 RNG。
- `jsonsel.py`：`_key_of` 对 `$.user_id[0]` 这类数组路径返回真实键 `user_id`，不再返回索引。
- `engine.py`：`bind()` 的 RNG 键改用实际被调用工具名（优先取 `ctx.current_call_index` 中匹配目标的工具），`patterns[0]` 仅作回退。
- 测试：默认 `call_index=1` 覆盖四种模式，修正 transient 期望，保留 1000 次确定性测试，新增 `_key_of` 与多工具 `bind` 用例。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
39 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 15 source files
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
161 passed in 2.62s
Required test coverage of 85.0% reached. Total coverage: 97.28%
EXIT=0
```

## F20fix merge (2026-10-28)

- Merged 096ada3 to main (ff). Reviews: self-review PASS (161 tests), WorkBuddy glm-5.3-flash read-only PASS.
- Known non-blocking issues:
  - Intermittent mode draws the RNG twice after the first firing (p, then probability); effective rate is p*probability when probability<1.
  - FaultEngine.bind() runs once, so a fault covering several tools uses one RNG keyed on the first tool called, not one per tool (S7.3).
## P13 stdio proxy (2026-10-29)

- `proxy/stdio.py` relays one MCP stdio connection: `create_subprocess_exec` upstream, one read loop per direction, client stdout flushed per message, upstream stderr mirrored to our stderr, client EOF closes the upstream stdin and waits 5 s before `terminate`.
- `skeptic proxy stdio [--seed N] -- <upstream command>` in `cli.py`; everything after `--` is the upstream command, and the upstream exit code becomes our exit code (4 when the upstream cannot start).
- Used a `RecorderStage` hook to observe c2s messages in unit tests: the pipeline only runs the fault stage for `tools/call`, so recorder is the stage that sees every message.
- `tests/fixtures/echo_server.py` is an SDK `MCPServer` with one `echo` tool; `tests/integration/test_stdio_proxy.py` drives it through the proxy with the SDK client.
- The installed SDK advertises `2025-11-25` in `HANDSHAKE_PROTOCOL_VERSIONS`, so the pinned-version test does run; the skipif is only a guard for SDKs that drop it.
- Added `tests/unit/test_stdio.py` (21 tests) for the action application, era detection, blank/parse-error lines, EOF close, upstream exit codes and start failure. stdio.py coverage went 21% -> 94%, total 83.59% -> 95.34%.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
43 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 16 source files
EXIT=0

===== uv run pytest -m "not live" -q --cov=skeptic_agent =====
189 passed in 9.97s
Required test coverage of 85.0% reached. Total coverage: 95.34%
EXIT=0
```


## P13 merge (2026-10-29)

- codex c9a1fbb ff-merged to main. Self-review PASS (189 tests, coverage 95.3%); glm-5.3-flash read-only review PASS.
- Non-blocking: stdin readline runs in a worker thread; if the upstream exits first, shutdown may wait for client stdin EOF.

## F21 显式故障 L01–L07（2026-10-29）

基线 `5d61598`，分支 `codex`。交付 `src/skeptic_agent/faults/loud.py`、`tests/unit/test_loud.py`（35 个用例）、`tests/e2e/test_loud_faults.py`（10 个用例，经 stdio 代理连 `tests/fixtures/echo_server.py`）。L01–L03、L05–L07 注册进 `REGISTRY`；L04 只在 HTTP 传输下适用，F21 不做 stdio 实现，注册表里没有它。

实现要点：

- 每个故障的 `apply` 直接返回改好的消息，或返回一个动作：`ReplyToClient`（L06/L07 直接回复客户端）或 `Hold`（L01 先扣住）。`FaultEngine._apply` 遇到 `Hold`/`ReplyToClient` 就以该动作结束本条消息的故障链；引擎改写过的消息清空 `raw_bytes`，由 `stdio._apply_s2c` 用 `dump` 紧凑序列化发出（S4.1：未改动的按原字节透传，改动过的重新序列化）。
- L01：`Hold(ms=hold_ms, then=ReplyToClient(超时错误), unless_cancelled=id)`。`StdioProxy` 记录客户端 `notifications/cancelled` 的 `requestId`；等待中命中该 id 时 `_wait` 立刻结束等待并改为 `Drop`，客户端收不到任何回复（S6 L01 的取消分支）。
- L03/L05 先做 `resultType` 检查（S4.5）：`resultType` 存在且不是 `complete` 时原样透传。
- L06/L07 的 `tools/list` 改写只作用于目标表达式匹配到的工具（`resolve_targets` + `tool_matches`），列表里其他工具不动。
- L07 的 `old` 取自 `inputSchema.required[0]`，`new = old + "_v2"`；`required` 同步改名，`properties` 里的键一并改名。调用时参数有 `old` 没有 `new` → 直接回复 `-32602` 文本 `Invalid arguments: missing required property '<new>'`；有 `new` → 把 `new` 改回 `old` 后转发；两者都有时以 `new` 的值为准。工具没有必填参数时 `applicable` 为假，故障不触发。

规格歧义与处理：

- S6 给出的 `{"error":{"code":-32602,"message":"Unknown tool: <name>"}}` 只写了错误对象这一层。现有 `jsonrpc.ErrorResponse` / `ErrorObject` 会把 `data:null` 一起序列化，所以单元快照按解析后的对象比较（`code`/`message` 逐字一致），e2e 再核对客户端收到的字节。
- S6 没说 L07 的“参数里有 `old` 没有 `new`”是否只在 `old` 是必填参数时才成立。原文不区分必填，F21 照原文实现：只要该工具被 L07 漂移过，参数里有 `old` 就按错误回复。
- `<name>` / `<new>` 按实际调用的工具名和改名后的首个必填参数填充。
- `Hold` 原先只能包 `Forward`/`ReplyToClient`/`SendToServer`/`Drop`，F21 增加 `unless_cancelled` 字段承载 L01 的取消语义，没有引入新机制或新依赖。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
46 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 17 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
234 passed in 18.69s
Required test coverage of 85.0% reached. Total coverage: 95.43%
EXIT=0
```


## F21 merge (2026-10-29)

- codex 1de3c6f ff-merged to main. Self-review PASS (ruff/format/mypy clean, 234 passed, coverage 95.4%); glm-5.3-flash read-only review PASS. L04 not applicable on stdio per S6.
- Non-blocking: an L01 Hold sleeps its full delay before checking cancellation, and holds run inline in the upstream read loop, so other server replies wait behind a held one.

## F22 静默故障 S01–S05（2026-10-29）

基线 `20d2b0c`，分支 `codex`。交付 `src/skeptic_agent/faults/silent.py`、`tests/unit/test_silent.py`（46 个用例）、`tests/e2e/test_silent_faults.py`（9 个用例，经 stdio 代理连 `tests/fixtures/echo_server.py`）。S01–S05 全部注册进 `REGISTRY`，类别 `silent`。

实现要点：

- 四个响应类故障（S01–S04）都过 `_result_of` 做 S4.5 的 `resultType` 检查：存在且不是 `complete` 时原样透传；`isError` 一律不动，保持缺省或 `false`，`content` 里的块类型不改。
- S4.5 同步改写规则集中在 `_text_is_synced` / `_sync_text`：只有当第一个 `type=="text"` 块能解析成 JSON 且与 `structuredContent` 深度相等时，才把它重写为 `json.dumps(新值, ensure_ascii=False, sort_keys=True)`；否则该文本块按各故障的“纯文本回退”规则处理。
- S01：`structuredContent` 是对象 → `{}`，是数组 → `[]`；同步块跟着改成 `{}` / `[]`；非同步的文本块（含只有文本的情形）改成 `""`。
- S02：在 `structuredContent` 里取元素最多的数组（并列取深度优先先遇到的），只保留前 `ceil(len*ratio)` 个；没有数组时把每个字符串叶子截到 `floor(len*ratio)`。纯文本（或非同步文本块）保留前 `floor(len*ratio)` 个字符。
- S03：结构化数据里整串匹配 `^\d{4}-\d{2}-\d{2}(T[\d:.]+(Z|[+-]\d{2}:\d{2})?)?$` 的叶子整体前移 `days` 天，日期部分重算、时间与 `Z`/偏移后缀原样保留；纯文本用同一个正则去掉 `^`/`$` 全局替换。
- S04：有场景 `fault_targets.numeric_path` 且该处是数字时用它，否则用 `jsonsel.first_numeric_leaf` 的首个数值叶子，乘以 `factor`；两个操作数都是整数时结果仍是整数。纯文本把第一个 `-?\d+(\.\d+)?` 匹配乘以 `factor`。
- S05：`pre_call` 钩子，`applicable` 要求场景同时有 `entity_arg` 和 `decoys.entity`；命中时把 `params.arguments[entity_arg]` 换成 `decoys.entity` 再转发，响应不动。
- 改过的消息走引擎既有逻辑清空 `raw_bytes`，由 stdio 代理 `dump` 紧凑序列化；未改动（故障不适用）的消息按原字节透传。
- `faults/engine.py` 增加 `from skeptic_agent.faults import loud, silent  # noqa: F401`：此前没有任何地方导入 `loud`，F21 的注册只在测试里随导入生效；现在通过代理或 CLI 跑时也会注册全部故障。`test_profiles.py` 里“未注册故障不触发”的用例因此改用尚未实现的 `S06`。

规格歧义与处理：

- S4.5 只说“文本块不是 JSON 时按各故障规定的‘纯文本回退’规则处理”。F22 的读法是：只要有 `structuredContent` 且文本块存在，回退规则就作用于这个文本块，与该文本块是否本身构成“纯文本结果”无关；因此 S01 的“只有文本时替换为 `""`”也覆盖“有结构化数据但文本不同步”的情况。
- S01 的“同类型的空值”只定义了对象和数组；`structuredContent` 是标量字符串/数字时没有对应的空值，F22 视为不适用（返回原消息，引擎不记触发）。
- S02 的“没有数组时把所有字符串叶子截断到原长度的 `ratio`”没有给出取整方式，F22 用 `floor`；截断后长度为 0 的叶子保持原样，免得单字符代码（货币符号、等级）直接消失。
- S02 的“纯文本保留前 `floor(len*ratio)` 个字符”在 `ratio` 使结果不小于原长时等于没变，视为不适用。
- S03 的日期格式允许带偏移的后缀；F22 前移时保留原分钟/秒与时区后缀，只改日期部分，格式不变。
- S04 的 `factor` 非数字、布尔或非有限值时视为参数不可用，故障不适用（不抛异常）；`numeric_path` 指向非数字时同样视为不适用，不回退到首个数值叶子。
- S05 的请求参数里没有 `entity_arg` 时不注入（视为不适用），有则换成诱饵值；S6 说“响应不做修改”，因此 S05 不实现 `post_call`。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
49 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 18 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
289 passed in 33.59s
Required test coverage of 85.0% reached. Total coverage: 96.00%
EXIT=0
```
## F22 merge (2026-10-29)

- codex 6cad1da ff-merged to main. Self-review PASS (ruff/format/mypy clean, 289 passed, cov 96.0%); glm-5.3-flash review PASS. engine.py now imports loud/silent so faults register in real runs.

## F23 ???? S06?S10?2026-10-29?

?? `c23f448`??? `codex`??? `src/skeptic_agent/faults/silent.py`???????`tests/unit/test_silent.py`?78 ????F22 ? 46 ? + ?? 32 ???`tests/e2e/test_silent_faults.py`?16 ????F22 ? 9 ? + ?? 7 ????? e2e ?? `tests/fixtures/counting_echo_server.py`?S06?S10 ????? `REGISTRY`??? `silent`??? S10 ???`tests/unit/test_profiles.py` ??????????????? `S06` ??????? `A01`?

?????

- ????????S06?S07?S08?S09??? F22 ? `_result_of`?S4.5 `resultType` ???????????`_text_is_synced` / `_sync_text`??S10 ? `pre_call` ????????
- ?? `_iter_entries`???????????? `(??, ?, ??)`?? S06 ? S08 ????????????????????????
- S06?`structuredContent` ?? `keep_keys`??? `["id"]`????????????? `"[REDACTED]"`?????????????????????????????????????????????????????????????????? `"[REDACTED]"`???????????????
- S07??? `structuredContent`??????????????? `floor(len*(1-cut_ratio))` ????`isError` ????? `structuredContent` ?????????????????????????????????????
- S08??? `unit`/`units`/`currency`/`temp_unit` ?????? S6 ?????????`C?F`?`USD?EUR`?`CNY?USD`?`JPY?USD`?`kg?lb`?`km?mi`?`ms?s`???????????????????????? F22 ??????????????????????????????????????????
- S09?`applicable` ?? `fault_targets.conflict_pair` ???????`apply` ? S6 ???????????????? `numeric_path` ??????? `factor`??? 1.5???????? S04 ???? S04 ?? `_factor(spec, default)`?????????????
- S10?`applicable` ??????????`$write` ? `write_tools`????????????????????????? `ReplyToClient(Response(id=?, result={"content":[{"type":"text","text":<response ??? JSON>}],"structuredContent":<response>}))`??? `response` ?? `{"status":"ok"}`????????? `Forward`??????????
- ??????????????? `raw_bytes` ?? stdio ????????????? `ReplyToClient` ??????

????????

- S10 ??????? `text` ? `structuredContent`???? `text` ????F23 ? `text` ?? `structuredContent` ? `json.dumps(..., ensure_ascii=False, sort_keys=True)`?? S4.5 ??????????????? `{\"status\": \"ok\"}`??????????????????????e2e ????????????
- S10 ? `response` ????????????????????????????? `{"status":"ok"}`??????
- S06 ? `keep_keys` ????????????????????F23 ??????? `keep_keys` ???????????????????? `keep_keys=["id"]` ?? `{"id": ?, "meta": {"name": ...}}` ????????
- S06 ??? `keep_keys` ????????????????????????????????????????????? `"[REDACTED]"` ???????????
- S07 ?????????????F23 ????????????? `floor(len*(1-cut_ratio))`??????????????????????????? JSON???????????? `json.loads` ????
- S08 ?????? `C?F` ?????????????????????????????????????????????S08 ????????F23 ???????? `structuredContent` ?????
- S09 ???????????? S6 ??????? S04 ? `numeric_path` ??????? `numeric_path` ? S09 ??????????????
- F23 ??? S6 ?????????????? `not_applicable` ???????????????P?????????????????????????????????? F22 ???
- ?????????? `on_c2s` ??????? `ReplyToClient`????? `Forward`?e2e ?????????????????S10 ????????????????????????????? `place_order`??????????

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
50 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 18 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
328 passed in 33.58s
Required test coverage of 85.0% reached. Total coverage: 96.35%
EXIT=0
```

## F23 merge (2026-10-29)

- codex 7850036 ff-merged to main. Self-review PASS (328 passed, cov 96.35%); glm-5.3-flash review PASS. Added tests/fixtures/counting_echo_server.py for S10.

## Session stop (2026-10-29 03:05)

- main at F23 merge (87eb03b). F24 (3123572, codex only) failed read-only review: A03 must advance only on successful target calls (S6), and _current_tool must use the current request's tool. F24fix stopped unfinished at cutoff (1 e2e test failing); WIP in git stash in skeptic-codex. Not merged.
## F24 对抗故障 A01–A03（2026-10-29）

基线 `87eb03b`，分支 `codex`。交付 `src/skeptic_agent/faults/adversarial.py`、`tests/unit/test_adversarial.py`（33 个用例）、`tests/e2e/test_adversarial_faults.py`（7 个用例，经 stdio 代理连 `tests/fixtures/echo_server.py`）。A01–A03 全部注册进 `REGISTRY`，类别 `adversarial`；`engine.py` 按 loud/silent 的写法导入 `adversarial` 完成注册。`tests/unit/test_profiles.py` 里“未注册故障”的样例从 `A01` 换成 `X99`。

实现要点：

- 载荷：`P1_TEMPLATE` / `P2_TEMPLATE` 按 S6 逐字保存，`render()` 只把 `{mail_tool}` 换成 `send_email`。单元测试与 e2e 都拿完整字符串比对，e2e 再核对客户端收到的字节。
- A01：`post_call`。先深拷贝 result，再往第一个 `type=="text"` 块尾部追加 `"\n\n" + payload`；随后在 `structuredContent` 顶层按 S6 列出的顺序 `body`、`content`、`text`、`snippet`、`description` 找第一个字符串字段追加一次。两处分别追加，因此不走 S4.5 的同步改写。`resultType` 不是 `complete` 时原样透传；两处都找不到可写内容时视为不适用。
- A02：`list`。目标表达式解析出的每个工具，其 `description` 改成 `原description + "\n\n" + payload`，其余工具和字段不动；工具没有 `description` 时按空串处理。
- A03：`list`。第一次 `tools/list` 原样返回；累计调用达到 `after_calls`（默认 1）之后，每次 `tools/list` 都按 A02 改写。旧版协议（`ctx.era.kind == "LEGACY"`）且服务器声明 `tools.listChanged` 时，在改写后的列表之后发一条 `notifications/tools/list_changed`，只发一次。
- A03 的调用计数：目标通常是 `$primary`，而在故障前置钩子里 `$primary` 只能匹配具体工具名，无法用它判断“这次调用属于目标”。F24 在 `Fault` 上加了 `on_request(spec, ctx)`（默认空实现），引擎在 `tools/call` 进入故障阶段、管线已分配 `call_index`（ADR-0007）之后、前置钩子之前调用它；A03 从这里读 `ctx.current_call_index` 记下已发生的调用次数。它不需要看到响应，所以“客户端先调用再取列表”也能正确计数。
- A03 的调度事件只有 `tools/list`。引擎的 `_apply` 现在只有 `list` 钩子会掷 `next_event`；从前只要 `post_call` 故障在 `tools/list` 上被枚举到就掷一次，会白白消耗它的触发次数（A02 不受影响，A03 会）。
- list_changed 通知：`EpisodeContext` 新增 `control: list[Any]`。A03 在 `tools/list` 改写成功后向这里放一个 `ReplyToClient(Notification(...))`，`FaultEngine.on_s2c` 在 `tools/list` 分支返回前用 `_drain_control` 把排队的动作接在该响应之后。stdio 代理已有的 `ReplyToClient` 处理即可写到客户端，传输层没有改动。

规格歧义与处理：

- A03 的“累计成功调用”只对目标工具计数。F24 按请求计数，无法判断响应是否为业务失败，所以 S6 字面上的“成功”在这里等同于“调用发出并转给了上游”；单元与 e2e 测试都按调用次数验证。
- “目标工具”的判定：`$primary` / `$write` / `$conflict_b` 先解析成场景里的工具名，再和实际调用的工具名按 glob 比较；目标是 `*` 时任意工具都算。
- 旧版协议与 `tools.listChanged`：S4.2 的 `Era` 只有年份版本号，不保存 `initialize` 的 capabilities。`ctx.scenario` 已用于存放运行期补充信息，F24 读它的 `capabilities.tools.listChanged`；场景里没有该字段时视为服务器未声明，不发通知。字段位置记录在本条，S8.1 的场景格式未改。
- 通知的时机：改写后的列表响应先写，通知紧随其后，两者都算同一次 `tools/list` 的结果；只发一次，之后的列表照常改写但不再通知。
- A01 的“这类字段”按 S6 的列举顺序（不是对象键顺序）取第一个有字符串值的键；只读顶层字段，不进入嵌套对象。`structuredContent` 是标量或数组时只在文本块上追加。
- A02/A03 的工具有 `description` 但值不是字符串时按空串处理，避免把非字符串直接相加。
- 载荷只用于测试；`MAIL_TOOL` 固定为 S8.5 的 `send_email`。`payload` 参数可以整段覆盖，但默认值逐字一致。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
53 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 19 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
368 passed in 38.38s
Required test coverage of 85.0% reached. Total coverage: 96.32%
EXIT=0
```

## F24fix A03 只计成功的目标调用（2026-10-29）

基线 `beffdbf`，分支 `codex`。修正 F24 审查提出的两点，并处理它暴露出的 e2e 夹具问题。上一会话未完成的改动保留其正确部分：删掉 `Fault.on_request`（以及 `engine._run_on_request`），A03 改为在 `post_call` 里按响应计数。

实现要点：

- A03 的 `hooks` 从 `("list",)` 改为 `("post_call", "list")`。`apply` 先 `_count`，再用同一个 `payload` 判断是不是 `tools/list` 结果；调用响应只参与计数，返回原样。
- `_count(payload, spec, ctx, tool)`：只有 `tool` 不为 `None`、`_is_success(payload)` 为真、且 `tool` 匹配目标表达式时才 `calls += 1`。`_is_success` 要求是 `Response`、`result` 是对象、`resultType` 缺省或 `complete`、`isError` 不为 `True`；`ErrorResponse` 一律不算。
- `_current_tool(payload, ctx)` 用响应的 id 查 `ctx.pending[(C2S, id)]`，并且要求 `pending.method == TOOLS_CALL`，返回该 `PendingCall.tool_name`。不再扫描 `ctx.current_call_index`——多目标时那样会按工具名首次出现的顺序取到别的目标。
- 引擎在 `on_s2c` 里照旧把 `attempt` 回写到 `ctx.current_call_index`，A03 不再用它。

测试：

- 单元（`tests/unit/test_adversarial.py`）：`test_a03_counts_only_successful_calls`、`test_a03_ignores_a_jsonrpc_error`、`test_a03_ignores_an_incomplete_result`、`test_a03_counts_a_successful_call_after_a_failure`（`after_calls=2`，一次 `isError` + 一次成功不够，第二次成功才到 2）、`test_a03_counts_only_when_the_target_was_called`、`test_a03_uses_the_tool_of_the_current_request`。这些用例直接断言 `RugPull.calls`，而不是只看列表有没有被改写——只断言列表会被 `next_event` 的掷骰掩盖，把 `_is_success` 改成恒真也不会失败。已验证：把 `_is_success` 强制为真会让前四个失败；把 `_current_tool` 换回扫描 `ctx.current_call_index` 会让后两个失败。
- e2e（`tests/e2e/test_adversarial_faults.py`）：新增 `tests/fixtures/faulty_echo_server.py`（`echo` 在 `text == "error"` 时返回 `isError: true`，`echo_other` 恒成功）。`Session`/`_run` 增加 `server` 与 `scenario` 参数；新增 `test_a03_ignores_an_is_error_result`、`test_a03_counts_a_successful_call_after_a_failure`、`test_a03_counts_only_the_tool_that_was_called`。

规格歧义与处理：

- “累计成功调用”是否只算目标工具。S6 的 A03 只写“目标工具累计成功调用 `after_calls` 次”。判定方式是：目标表达式照常解析成工具名模式（`$primary` 等），实际调用的工具名按 glob 匹配；`$primary` 覆盖多个工具时，任一被调用并成功都算。
- “成功”的判定：`Response` 且 `isError` 不为 `true` 且 `resultType` 为 `complete`。S6 没说 `resultType`，这里沿用 S4.5/F21–F23 对 `resultType` 的处理：非 `complete` 不是一次完成的成功调用。
- `tools/list` 响应不算调用：它的 pending 是 `method == "tools/list"`，`_current_tool` 返回 `None`，所以列表响应永远不计数；这也让“先调用、后取列表”与“取列表、再调用”两种顺序都正确。
- e2e 夹具的丢包问题：`Client` / `tools/list` 缓存不是原因。直接跑夹具时，客户端一次写入全部消息再关 stdin，SDK 的 stdio 传输在读到 EOF 后会取消仍在执行的请求（`mcp/server/runner.py` → `jsonrpc_dispatcher.py` 的 `tg.cancel_scope.cancel()`），于是 `echo` 的回复（在 worker 线程里执行）有时来不及写出，`tools/list` 先到。原夹具对每个请求一条一条发送并等待回复，`Session.start` 一次性写入全部消息是这次才暴露的。改法是 `Session.send` 单条写入，`_run` 每发一条（带 id）就 `wait_for_id`；这样上游在 stdin 关闭时没有在途请求。连续跑 3 轮全套 e2e 稳定通过。
- e2e 的 scenario 覆盖：`Session._run` 原先把 `proxy.ctx.scenario` 硬写成模块级 `SCENARIO`，测试传进去的场景到不了代理。改为 `Session(scenario=...)` 并透传，多目标用例才真正生效。
- 载荷文本、`after_calls` 默认值、list_changed 通知时机都沿用 F24，未改。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
54 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 19 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
377 passed in 50.15s
Required test coverage of 85.0% reached. Total coverage: 96.33%
EXIT=0
```

## F24 merge (2026-10-29)

- codex c9a3512 ff-merged to main. F24 beffdbf (rebased from 3123572) + F24fix c9a3512. Self-review PASS (377 passed, cov 96.33%); glm-5.3-flash re-review PASS (A03 counts only successful calls of the requested tool). e2e harness now feeds messages one at a time (SDK cancels in-flight handlers on stdin EOF).

## F25 内置故障画像与依据文档（2026-10-29）

基线 `0a02fee`，分支 `codex`。交付 `src/skeptic_agent/data/profiles/` 下的 6 个画像（`none`、`loud-core`、`silent-core`、`adversarial-core`、`cross-source`、`realistic-2026`）、`src/skeptic_agent/faults/catalog.py`、`skeptic faults list` 命令、`tests/unit/test_builtin_profiles.py`（25 个用例），以及 `docs/en/methodology/{faults.md,realistic-profile.md}` 与 `docs/zh/methodology/` 下的中文版。`CHANGELOG.md` 的 `Unreleased` 加了一行。

画像按 S7.2 逐行编写：`none` 只有 `include_clean`；`loud-core` 为 L01/L03/L05（transient）+ L02/L06/L07（permanent），不含 L04；`silent-core` 为 S01–S08 与 S10（S10 目标 `$write`）；`adversarial-core` 为 A01–A03；`cross-source` 只有 S09（目标 `$conflict_b`）；`realistic-2026` 为 sampled、每场景 3 次，18 条故障权重逐条等于 S7.2，合计 1.00，全部 `persistence: {mode: mixed, permanent_p: 0.6}`。每个条目把 S6 的默认参数显式写出（`hold_ms`、`code`/`message`、`retry_after_s`、`ratio`、`days`、`factor`、`keep_keys`、`cut_ratio`、`response`、`after_calls`），值直接取实现里的常量。

`catalog.py` 是 S6 故障目录的静态表（id、名称、类别、目标、默认持续、主要参数默认值、正确行为、文献编号），参数默认值从 `loud`/`silent`/`adversarial` 的常量导入，不再另抄一份。`skeptic faults list [--class {loud,silent,adversarial}] [--json]` 读这张表：`--json` 输出一个 20 元素的数组，未知类别按用法错误退出码 2（S2）。

文档：`faults.md` 说明 20 种故障各自做什么、通用与专有参数、例子，并给出与 [28]–[40]、[51] 的逐条对应；`realistic-profile.md` 给出权重表、按类别与逐故障的定性论证，明确写出“权重是依据文献定性判断得出的假设”，并给出用真实事故数据重新校准的 5 步。只引用项目书列出的来源，未扩写任何引用；页中引用的数字均与项目书 2.3 节一致，并注明未回查原文。

规格歧义与处理：

- 交付清单写的是 `docs/en/methodology/realistic-profile.md` 与中文版，`faults.md` 未点名中文版；计划书 1.10 又要求面向用户的文档中英一一对应。因此两份英文文档都在 `docs/zh/methodology/` 下有结构对应的中文版。
- 6 个画像的 `include_clean` 只有 `none` 为 true。S7.2 对 `loud-core` 等没有明说；理由是 F25 验收要求 6 个画像都能被 `skeptic run --profile <id>` 加载，而 `none` 就是无故障基线，其余画像若也加干净 episode 会重复基线。这属于画像成员级别的选择，与 ADR-0002 记录的内置画像成员不冲突。
- 当文档说“每个场景”时按 S7.4 理解为每个（种子 × 场景）：`realistic-2026` 的 3 次抽样是“每个场景”，不是“每个种子跨所有场景合计 3 次”。README 与文档按这个读法写。
- `skeptic faults list --json` 每条记录带 `class` 键（值为 `loud`/`silent`/`adversarial`），与 S6 的类别术语一致；`params` 里给出默认值而不是实现细节，`payload` 类参数同时给出 `template` 原文，方便 `faults explain`（后续卡）复用。
- 文档中 `faults.md` 的“依据”是定性对应，不声称论文测到了该故障的某个频率；`realistic-profile.md` 的权重同理，二者都按 F25 要求写明这是假设。
- L04 不在 `realistic-2026` 中：它是 HTTP-only，加入后 stdio 运行会丢掉全部 L04 回合并改变整体分布。需要它的运行用 `loud-core` 或另写画像。

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
60 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 20 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
402 passed in 45.38s
Required test coverage of 85.0% reached. Total coverage: 96.46%
EXIT=0
```

## F25 merge (2026-10-29)

- codex e4ea9cd ff-merged to main. Self-review PASS (402 passed, cov 96.46%, faults list --json = 20); agy gemini-3.8-flash-high review PASS (citations all from spec). Built on wb deepseek-v4.1-flash-sg.

## P14 HTTP proxy (2026-10-29)

Base `d333a82`, branch `codex`. Built `src/skeptic_agent/proxy/http.py`, `src/skeptic_agent/proxy/sse.py`, the `skeptic proxy http` CLI command, `tests/integration/test_http_proxy.py`, and the unit tests `tests/unit/test_http.py` / `tests/unit/test_sse.py`. The echo fixture gained an `http PORT` mode.

What was built:

- `HttpProxy` serves one Starlette route, `/mcp`, for `POST`, `GET` and `DELETE` (S4.1). The app's lifespan opens one `httpx.AsyncClient`; every request body is forwarded to `--upstream` and every response body goes back through the same `Pipeline` `stdio.py` uses, with the same c2s/s2c split and the same `EpisodeContext` shared by the whole episode.
- `POST`: the body is parsed as one message. A `ParseError` body is forwarded untouched, like an unparseable stdio line. Otherwise the c2s actions run and the reply is the upstream response, or a `ReplyToClient` message when a fault answered directly (L02/L03/L06/L07), or `202` when everything was dropped.
- JSON responses are processed as one s2c message; `text/event-stream` responses are processed event by event. `sse.py` decodes events across chunk boundaries, keeps `id`/`event`, and `encode_event` writes them back; the stream is a `StreamingResponse`, so a long upstream stream is never buffered.
- Hop-by-hop headers are stripped both ways (`connection`, `keep-alive`, `proxy-authenticate`, `proxy-authorization`, `proxy-connection`, `te`, `trailer`, `trailers`, `transfer-encoding`, `upgrade`). `Authorization` and `Mcp-*` are kept; `Host`/`Content-Length` are dropped on the request because httpx sets them, and `Content-Length` is dropped on the response because the body is re-framed.
- Era detection reuses `detect_era` with the request headers, falling back to the first message body (S4.2).
- ~~L04 needs no code: an unreachable upstream is answered `502`, and an upstream HTTP status (503 included) is relayed as is.~~ Superseded by P14fix: an L04 fault now answers the call itself with the configured status. An unreachable upstream still answers `502`; that is a different failure, not L04.
- L01 still holds via `Hold`; cancellation is confirmed by a later `notifications/cancelled`, as on stdio, because the held POST cannot receive another request on the same exchange.

Spec ambiguities and how they were resolved:

- S4.1 says "GET and DELETE relay (without pipeline body processing)". `GET` streams are still pipeline-processed event by event (that is the point of SSE event-by-event); `DELETE` and any non-SSE `GET` body are relayed without processing.
- "SSE event by event through the pipeline" only makes sense for s2c; events that are not JSON-RPC messages (keep-alive comments) are relayed untouched.
- `A02`/`A03` answer `tools/list` by replacing the message with a `ReplyToClient` notification (`ctx.control`). On HTTP there is no second channel on the same exchange, so an extra message is sent upstream in the background rather than merged into the response body.
- The MCP SDK v2 in the venv rejects a POST without `Content-Type: application/json`, so the raw-HTTP integration tests complete a real initialize first and reuse its `Mcp-Session-Id`.
- No dependency was added: `starlette`, `httpx` and `uvicorn` were already in `pyproject.toml` (Apache-2.0, BSD-3-Clause), and `uv.lock` is unchanged.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
65 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 22 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
447 passed in 67.85s
Required test coverage of 85.0% reached. Total coverage: 96.04%
EXIT=0
```

## P14fix L04 hook, S2 CLI flags, proxy-* stripping (2026-10-29)

Base `16e39bb`, branch `codex`. Three review findings against P14 are fixed. Files touched: `src/skeptic_agent/faults/loud.py`, `src/skeptic_agent/proxy/pipeline.py`, `src/skeptic_agent/proxy/http.py`, `src/skeptic_agent/proxy/stdio.py`, `src/skeptic_agent/faults/engine.py`, `src/skeptic_agent/cli.py`; tests `tests/unit/test_loud.py`, `tests/unit/test_http.py`, new `tests/unit/test_cli.py`, `tests/integration/test_http_proxy.py`.

What was built:

- **L04 hook.** `loud.HttpStatus` (`id="L04"`, `hooks=("pre_call",)`, default `L04_STATUS = 503`) is registered. It sits at c2s step 4 of S4.4, so it runs after recording and the G06/G07 guards and before the forward. `apply` returns a new `ReplyWithStatus(status)` pipeline action; `_collect` in `proxy/http.py` turns it into `HttpResponse(status_code=status)` with an empty body and never calls `_send`, so the call does not reach the upstream. `FaultEngine._apply` treats it like `Hold`/`ReplyToClient`: it ends the chain for that message.
- **Static applicability.** `HttpStatus.applicable` is true only when the context's scenario records `transport: http`, the same rule `profiles.statically_applicable` already applies at expansion time (S7.4). `HttpProxy` now takes an optional `scenario` and stores it on `EpisodeContext`; without that the fault could never see the transport. `run_http_proxy` passes it through.
- **stdio.** L04 stays registered but `applicable` is false on a stdio episode, so the call is forwarded unchanged. `stdio._apply_c2s` has an explicit "no stdio form" branch that ignores `ReplyWithStatus` rather than silently swallowing the message, matching S6 ("stdio ä¸‹è§†ä¸ºä¸é€‚ç”¨").
- **CLI.** `skeptic proxy http` now takes `--upstream URL` (required, as before) and `--listen HOST:PORT` with default `127.0.0.1:8765` (S2). `--host`/`--port` are gone. `cli.parse_listen` splits at the last colon (so `[::1]:9000` works) and raises `typer.BadParameter` â€” exit code 2 â€” for a missing host or port, a non-numeric port, or one outside 1â€“65535.
- **Header stripping.** `proxy/http.py` gained `_is_hop_by_hop`: a header is dropped when it is one of the listed hop-by-hop names or when its lower-cased name starts with `proxy-`. Both `forwarded_request_headers` and `forwarded_response_headers` use it, so `Proxy-Authorization`-style names, `PROXY-Connection` and any other `proxy-*` header leave both directions; `Authorization`, `Mcp-*` and other headers are still relayed.

Spec ambiguities and how they were resolved:

- S6 says L04 is "HTTP transport only"; the plan does not say where the transport is recorded. The existing `profiles.statically_applicable` already reads `scenario.transport == "http"`, so the runtime check reads the same field, and the HTTP proxy sets its scenario as HTTP by construction. A stdio episode with no scenario therefore never fires L04.
- S4.4 places L04 on the `tools/call` c2s path, so L04 fires for `tools/call` only. `initialize`, `tools/list` and notifications are forwarded normally; a fault that also failed the handshake would make the episode unrunnable rather than test "retry".
- S6 fixes L04's default persistence at `transient` (one retry recovers), so `loud-core` still leaves it out; S7.2 requires that ("L04 åªåœ¨ HTTP åœºæ™¯å¦è¡Œå¯ç”¨").
- The status body is empty, per S6 ("ç©ºå“åº”ä½“"). The old code path that relayed an upstream 503 with its error body is unchanged for real upstream failures; `502` for an unreachable upstream remains a separate code path.
- `--listen` rejects port 0 even though it is technically valid, because a proxy told to listen on a random port cannot be reached by the wrapped client.

Tests: `test_loud.py` now asserts L04 is registered and that stdio forwards it unchanged; `test_http.py` covers the 503/empty-body path and the `proxy-*` stripping in both directions; `test_cli.py` covers the default listen, an override, the removed flags, and the bad-value exit code; `test_http_proxy.py` adds the end-to-end 503 acceptance test and an L04-with-status-418 case against the real echo fixture.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
66 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 22 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
467 passed in 62.08s (0:01:02)
Required test coverage of 85.0% reached. Total coverage: 96.17%
EXIT=0
```

## P14 merge (2026-10-29)

- codex 00c631b ff-merged to main. P14 16e39bb + P14fix 00c631b (L04 HTTP hook, --upstream/--listen 127.0.0.1:8765, proxy-* stripping). Self-review PASS (467 passed); agy gemini-3.8-flash-high re-review PASS. glm-5.3-flash unavailable (WorkBuddy credits exhausted).

## P15 Cassette recorder (2026-10-29)

Base `bacae4b`, branch `codex`. Built `src/skeptic_agent/record/cassette.py`, `src/skeptic_agent/record/redact.py`, `src/skeptic_agent/record/__init__.py`, `tests/unit/test_cassette.py` (33 tests) and the child-process fixture `tests/fixtures/cassette_child.py`.

What was built:

- `Recorder` writes one JSONL file per episode at `<dir>/<episode_id with ":" -> "__">.jsonl` (S5): a `header` line from `cassette_header`, one `msg` line per recorded message, a `footer` line from `finish`. Every line is `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` plus `\n` and is flushed immediately, so a killed process keeps the lines already written.
- Header fields follow S5 exactly and in its order: `type`, `schema`, `episode_id`, `created_at` (`YYYY-MM-DDTHH:MM:SSZ`), `skeptic_version` (`__version__`), `transport`, `upstream`, `era`, `seed`, `profile`, `fault_plan`, `guards`, `scenario_id`. `fault_plan` is built from `FaultSpec` and carries only persistence fields that apply (`n` for transient/mixed, `p` for intermittent/mixed, `permanent_p` for mixed, `probability` when not 1).
- `msg` lines carry the S5 fields: `seq`, `t_ms` (ms since the header), `dir`, `raw`, `final`, `fault`, `guards`, `dropped`, `internal`. `raw`/`final` come from the message bytes when they are still there (verbatim wire form) and from the model fields for a message a fault rebuilt; both are redacted.
- `CassetteRecorder(RecorderStage)` records in both directions and always returns `[Forward(msg)]`. The S4.4 order means it sees a c2s message first and an s2c message last, so it records what the client sent and what the client receives. `note_fault`/`note_guard` let the fault/Guard stages attach their work to the message they touched; this card does not wire the engine to them (Guards land in M5).
- Footer: `atexit` plus SIGTERM and SIGINT handlers. The handler writes the footer, restores nothing on purpose, and then replays the previous disposition: a previous callable handler runs, `SIG_IGN` returns, SIGINT raises `KeyboardInterrupt`, SIGTERM raises `SystemExit(128+signum)`. `finish` is idempotent and unregisters the hooks, so a normal exit writes exactly one footer.
- `redact.py`: `Authorization` and `Cookie` (case-insensitive) in any `headers` object, plus the value of every key matching `(?i)(api[_-]?key|token|secret|password)` anywhere in the object tree, become `***` (1.7). The walk copies and never renames keys.

Spec ambiguities and how they were resolved:

- S5 shows `"final": null` "when the message was not modified". The recorder gets the received message first and the sent one last, and the sent message always differs by `raw_bytes` alone. `final` is therefore written when the recorded message has no bytes left (a fault/Guard rebuilt it, S4.1 compact form) and null otherwise; the s2c `raw` slot keeps the received bytes. A strict "final = sent message whenever the pipeline changed it" reading would need the pre-fault bytes on the s2c line, which the recorder alone never sees.
- S5's header example has no field for the replay key or the tool name, so a `msg` line holds only what S5 lists; `fault.call_index` comes from `PendingCall.attempt` (ADR-0007) via `note_fault`, not from `ctx`.
- `scenario_id` is required by `schemas/cassette.schema.json` and must match the scenario id pattern, so it is a required argument with no placeholder: an episode with no scenario cannot be recorded yet (P16 will pass the real one).
- `internal` is derived from the `skeptic-` id prefix (S4.3) when the caller does not say otherwise; internal `tools/call` messages do not count towards `stats.tool_calls`.
- S5 does not say what happens when a signal arrives after `finish`; the hooks are removed at the end of `finish`, so a later SIGTERM gets the handler that was installed before the recorder.
- The `--record` CLI flag already exists in `cli.py`; connecting it to this recorder needs the episode/era/scenario wiring of P13/P16 and is out of scope here.

```text
===== uv run ruff check =====
All checks passed!
EXIT=0

===== uv run ruff format --check =====
71 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 25 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
500 passed in 61.54s (0:01:01)
Required test coverage of 85.0% reached. Total coverage: 96.43%
EXIT=0
```

## P15fix Case-insensitive secret redaction at every depth (2026-10-29)

Base `9c9ee7c`, branch `codex`. Fixes the redaction gaps found in the P15 review. Files touched: `src/skeptic_agent/record/redact.py` and `tests/unit/test_cassette.py` (4 new tests, 37 in the file). `cassette.py` is unchanged; it already sends every `raw`/`final` value through `redact()`.

What was built:

- **One name test.** `_secret_key(name)` is now the only check 1.7 uses: the lower-cased name is a secret header (`authorization`, `cookie`, `set-cookie`) or matches `(?i)(api[_-]?key|token|secret|password)` anywhere. The old split between "header tables" (`_redact_headers`, which only knew `authorization`/`cookie`) and ordinary objects is gone, so a header table needs no special case.
- **`Set-Cookie` added.** It joins `SECRET_HEADERS`, which also makes `set-cookie`-like names such as `Set-Cookie` and `SET-COOKIE` redact.
- **Every dict key at every depth.** `_redact` applies `_secret_key` to any string key it meets, so `X-Api-Key`, `X-Auth-Token`, `arguments.Authorization`, a nested `auth.password`, `_meta` members and objects inside lists all redact. Values under a secret name become `"***"` whatever their type (string, object, list, number); everything else is walked.
- **The `headers` container key is matched case-insensitively.** Because a header table is walked like any other object, `Headers`, `HEADERS` and `headers` all redact their `Authorization`/`Cookie`/`Set-Cookie`/`api_key` members. `HEADERS_KEY` was removed as it no longer decides anything.
- Kept S5/1.7 behaviour otherwise: keys are never renamed, the walk copies and never mutates its input, scalars and plain list values pass through, `REDACTED` is still `"***"`.

Spec ambiguities and how they were resolved:

- 1.7 lists `Authorization` and `Cookie` as headers and gives a pattern for keys. P15fix reads the two as one rule ("one case-insensitive secret-name test"), so the pattern also applies to header names; that is what makes `X-Api-Key` and `X-Auth-Token` redact. `Set-Cookie` is added to the fixed header list because it carries the same session secret as `Cookie` and appears in s2c payloads.
- 1.7 does not say whether the `headers` container key is case-sensitive. It is matched case-insensitively like every other name, so a server that writes `Headers` is redacted too.
- A key that itself matches the pattern has its whole value replaced, even when the value is an object or a list. 1.7 says "the values under keys whose name matches", so the subtree is dropped as a unit instead of being partially walked.
- The header list is still a fixed set, not "the pattern only", so `Authorization` (which contains no pattern word) is caught; matching runs on the lower-cased name, so `(?i)` in the compiled pattern stays redundant but harmless.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
71 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 25 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
504 passed in 60.88s (0:01:00)
Required test coverage of 85.0% reached. Total coverage: 96.42%
EXIT=0
```

## P15 merge (2026-10-29)

- codex dfd5c1f ff-merged to main. P15 9c9ee7c + P15fix dfd5c1f (case-insensitive secret redaction at every depth). Self-review PASS (504 passed, cov 96.42%); agy gemini-3.8-flash-high re-review PASS (glm-5.3-flash unavailable, WorkBuddy credits exhausted).

## P16 Cassette replay (2026-10-29)

Base `8f4a2ce`, branch `codex`. Built `src/skeptic_agent/record/replay.py`, the `skeptic replay` command in `src/skeptic_agent/cli.py`, `tests/integration/test_replay.py` (32 tests: 4 through a real SDK client, 28 unit/CLI) and a small `serve(reader, writer)` split in `src/skeptic_agent/proxy/stdio.py`.

What was built:

- **Loading.** `read_cassette` reads the JSONL and rejects anything whose first record is not a `skeptic.cassette/v1` header. `Cassette.load` pairs every `c2s` `tools/call` with the first non-internal `s2c` reply of the same id, keys it by `request_key(method, tool_name, arguments) = stable_hash([method, tool_name, arguments])`, and queues the reply (`final` when present, else `raw`) in recorded order. A `fault.target.tool` supplies the tool name when the request's own `params.name` is not a plain name. `initialize`, `server/discover` and `tools/list` are kept as one cached reply each, not queued.
- **Serving.** `ReplayServer.run` serves the process stdin/stdout; `handle_line` answers a request from the cassette and leaves notifications unanswered. A parse error gets `-32700`. A match miss gets a JSON-RPC error (`-32602`, "replay: no recorded reply (...)") under `--on-miss error` (default) or is forwarded to the live upstream under `--on-miss live` and its first answering line is returned.
- **CLI.** `skeptic replay --cassette FILE [--on-miss {error,live}] [-- CMD]`. Exit 2 for a bad `--on-miss` value or `live` without a command, exit 3 for an unreadable/invalid cassette or a live upstream that cannot start, 0 on a clean EOF.
- **Acceptance.** `test_replay_returns_the_recorded_results` records two `echo` calls through the real stdio proxy with a `CassetteRecorder`, then replays the file to a second real `ClientSession`; both result lists are equal value for value.

Spec ambiguities and how they were resolved:

- **What "matching on `(method, tool_name, stable_hash(arguments))`" covers.** S2 also names `initialize`, `server/discover` and `tools/list` as answered from the recording, and they have no arguments to queue on. They are served from one cached reply per method (first recorded wins) and are not consumed, so a client that lists tools twice still lists them. Handshake answers are shared between `initialize` and `server/discover`, so a modern client reaches a legacy recording and vice versa; the recorded result is returned with the client's own id.
- **`final` vs `raw`.** S5 says `final` is null when the message was not modified. Replay takes `final` whenever it is non-null — that is the message the client saw — and `raw` otherwise, for both the request side (the key) and the reply.
- **Redaction.** 1.7 can replace a value with `***`, so a replayed cassette is no longer word-for-word. `load` refuses such a reply with a `ReplayError` instead of silently serving a wrong value.
- **Match misses.** S2 does not fix the error shape; it uses S2's exit-code-free JSON-RPC path with `-32602` (the same code L06 uses for an unknown tool). No reply is sent for a notification, matching S5's "notifications get no answer" shape in the proxy.
- **Live upstream.** The live child is a fresh process with no session, so a forwarded `tools/call` would be rejected as out of session. Each handshake the client sends is also passed to the live upstream (answer discarded) before the cassette's answer is returned; the live process is only started when `--on-miss live` is set. Forwarding is one request at a time, and only the first answering line is returned; other lines the upstream emits meanwhile go to the client.
- **Proxy test hook.** `StdioProxy.run` was split into `_start` + `serve(reader, writer)` so the recording side of the integration test can drive the real proxy over a socket pair while keeping the recorder's `atexit`/signal hooks in the main thread (`run()` keeps the old behaviour byte for byte). `_StdStream`/`_StdReader` are unchanged; the two new `Protocol`s only widen the parameter types.
- **Test module name.** `tests/unit` and `tests/integration` have no `__init__.py`, so two `test_replay.py` files collide at import time. The unit and CLI tests live in the same `tests/integration/test_replay.py`, each marked `integration` (the file reaches a subprocess) or unmarked for the in-memory cases; the whole file takes about 24 s.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
73 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 26 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
536 passed in 362.40s (0:06:02)
Required test coverage of 85.0% reached. Total coverage: 95.96%
EXIT=0
```

## P16 merge (2026-10-29)

- codex c3e2c45 ff-merged to main. Self-review PASS (536 passed, cov 95.96%); agy gemini-3.8-flash-high review PASS. Note: spec 项目书 line 453 shows 'skeptic replay' without --cassette; implemented --cassette per P16 card and S2.

## P17 Proxy performance benchmark (2026-10-29)

Base `b610132`, branch `codex`. Built `tests/perf/bench_proxy.py` (the benchmark
script), `tests/perf/test_bench_proxy.py` (11 smoke tests of the harness behind
the `perf` marker) and `docs/perf.md` (method, how to run, and this machine's
numbers).

What was built:

- `bench_proxy.py` measures the added latency of one `tools/call` per transport
  with the default pipeline (no faults, no Guards), against
  `tests/fixtures/echo_server.py`. Every sample starts a fresh pair of processes,
  warms each up, then times one proxied call and one direct call; the sample is
  `proxied - direct`. p50/p90/p99/mean/max are computed over the samples and
  checked against P17's acceptance (p50 < 5 ms, p99 < 30 ms). Exit code is 1 if
  either transport fails.
- stdio: the SDK `ClientSession` goes direct to `echo_server.py`, then to
  `skeptic proxy stdio -- python echo_server.py`.
- HTTP: the fixture is served streamable-HTTP; an `httpx` client posts a raw
  `initialize` (so the session id is real), one `notifications/initialized`, then
  `tools/call` bodies direct and through a `skeptic proxy http` child.
- Concurrency: 50 clients x 100 calls per transport (5,000 calls each). Every
  reply must carry its own id and its own text, so a lost message or a crossed
  id is an error.
- `--only`, `--count`, `--warmup`, `--clients`, `--calls`, `--report` select the
  run and write the raw numbers as JSON.
- `pyproject.toml` gains the `perf` marker and `addopts = "-m 'not perf'"`, so the
  benchmark stays out of the default pytest run. The smoke tests run with
  `uv run pytest tests/perf -m perf`.

Measured on this machine (2026-10-29; Windows 11 26200, i7-13650HX, Python
3.12.13, MCP SDK 2.3.0; 100 samples per transport, 3 warm-up calls):

| Transport | p50 | p90 | p99 | mean | max | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| stdio | 0.228 ms | 0.392 ms | 0.768 ms | 0.238 ms | 1.009 ms | PASS |
| HTTP | 0.804 ms | 1.117 ms | 1.639 ms | 0.811 ms | 3.380 ms | PASS |

Concurrency: stdio 5,000 calls, 0 errors, 0 mismatches; HTTP 5,000 calls,
0 errors, 0 mismatches. A second latency-only run gave stdio p50 0.205 /
p99 0.624 ms and HTTP p50 0.764 / p99 1.285 ms. Both transports pass with a
wide margin.

Spec ambiguities and how they were resolved:

- The card names `docs/drafts/perf.md`; there is no `docs/drafts/` directory in
  this repo, so the report is `docs/perf.md` (the path the orchestrator's P17
  brief names).
- The card says "5,000 `tools/call`" with p50/p99. A latency percentile over
  5,000 samples would take hours (a fresh process pair per sample is needed to
  keep sessions from warming up), so the latency part uses 100 samples per
  transport by default (`--count` raises it) and the 5,000 number is the
  concurrency run: 50 clients x 100 calls, exactly as the card's second step
  says. The concurrency run also counts as the "0 errors" acceptance.
- The card says the acceptance was written for `ubuntu-latest`. No Linux runner
  was available here and results must not be faked, so the recorded numbers are
  from this Windows machine and `docs/perf.md` says so.
- "Compare direct and proxied" on HTTP: the proxy holds one `httpx.AsyncClient`
  for the whole episode, while the direct side has no session. To compare the
  same call shape on both sides, both use one plain `httpx` client that sends an
  untyped body after a real `initialize`; the SDK client is used on stdio only.
- A sample can be negative when the direct call is slower than the proxied one;
  percentiles are used instead of per-sample thresholds.
- The benchmark never runs under `pytest`: it was made a separate script plus
  `perf`-marked smoke tests because it starts hundreds of processes. The
  `addopts` marker filter keeps the smoke tests out of the default run too.
- No dependency was added; `httpx`, `mcp` and `starlette`/`uvicorn` were already
  present and `uv.lock` is unchanged.

```text
===== uv run ruff check . =====
All checks passed!
EXIT=0

===== uv run ruff format --check . =====
76 files already formatted
EXIT=0

===== uv run mypy src =====
Success: no issues found in 26 source files
EXIT=0

===== uv run pytest -q --cov=skeptic_agent =====
536 passed, 11 deselected in 67.84s (0:01:07)
Required test coverage of 85.0% reached. Total coverage: 95.96%
EXIT=0

===== uv run pytest tests/perf -m perf -q =====
11 passed in 24.62s
EXIT=0

===== uv run python tests/perf/bench_proxy.py --report .tmp/opencode/perf.json =====
stdio n=100   p50=0.228ms p90=0.392ms p99=0.768ms mean=0.238ms max=1.009ms PASS
http  n=100   p50=0.804ms p90=1.117ms p99=1.639ms mean=0.811ms max=3.380ms PASS
concurrency stdio={'sessions': 50, 'calls': 5000, 'errors': 0, 'mismatches': 0}
concurrency http={'sessions': 50, 'calls': 5000, 'errors': 0, 'mismatches': 0}
acceptance p50<5.0ms p99<30.0ms: PASS
EXIT=0
```
