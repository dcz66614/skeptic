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
=============================== tests coverage ================================
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
=============================== tests coverage ================================
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
=============================== tests coverage ================================
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
=============================== tests coverage ================================
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
=============================== tests coverage ================================
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