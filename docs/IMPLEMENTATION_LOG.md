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

