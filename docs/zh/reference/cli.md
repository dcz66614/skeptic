# 命令行

入口是 `skeptic`（`skeptic_agent.cli:app`）。全局参数：`--version`，打印包版本后以退出码 0 结束。

`run` 使用的智能体规格是 `<适配器>:<模型>`。

| 适配器 | 模型 |
|---|---|
| `reference` | `openrouter/<厂商>/<模型>`、`openai/<模型>`、`compat/<模型>` 或 `fake/<脚本>` |
| `openai-agents`、`langgraph`、`crewai`、`pydantic-ai` | 同上；各自需要安装对应 extra |
| `command` | `command:<预设>`，预设选择 `agents.<预设>.cmd` |

测试用的 FakeLLM 脚本：`fake/oracle_follower`、`fake/gullible`、`fake/honest`、`fake/looper`。它们不访问网络。

## 命令

| 命令 | 作用 |
|---|---|
| `skeptic init` | 发现 MCP 客户端配置并写出 `skeptic.yaml` |
| `skeptic wrap FILE` | 让选中的服务器经过 `skeptic proxy`，或从备份恢复 |
| `skeptic proxy stdio` | 放在上游命令前面的 stdio 代理 |
| `skeptic proxy http` | Streamable HTTP 代理 |
| `skeptic replay` | 把卡带当作 stdio 服务器重放 |
| `skeptic faults list` | 打印故障目录 |
| `skeptic sandbox run NAME` | 启动内置沙箱 |
| `skeptic scenario validate PATHS` | Schema 和语义检查 |
| `skeptic scenario oracle PATHS` | 运行脚本化 Oracle |
| `skeptic run` | 展开回合、执行、写出 `results.jsonl` 和 `summary.json` |
| `skeptic bench run` | 按矩阵文件批量运行 |
| `skeptic report RUN_DIR` | 写出六种报告 |
| `skeptic compare RUN_A RUN_B` | 指标差值和置信区间 |
| `skeptic gate RUN_DIR` | 门槛检查 |
| `skeptic mcp serve` | MCP 服务模式 |

### `skeptic init`

`--path DIR`（默认 `.`）、`--yes`（覆盖 `skeptic.yaml`）、`--dry-run`、`--json`。`--dry-run --json` 只打印发现结果，不写文件。没有发现服务器时退出码为 1。文件已存在又没有 `--yes` 时退出码为 2。

### `skeptic wrap FILE`

`--server NAME`（可重复）或 `--all`，`--profile ID`（默认 `silent-core`），`--guards LIST`，`--undo`。第一次包装前，原文件复制为 `FILE.skeptic.bak`。`--undo` 从该备份逐字节恢复，然后删除备份。必须传入 `--all` 或至少一个 `--server`。

### `skeptic proxy stdio`

`skeptic proxy stdio [选项] -- COMMAND [ARGS...]`。选项：`--config FILE`、`--profile ID或路径`、`--guards LIST或预设`、`--record DIR`、`--seed INT`（默认 0）、`--episode-id STR`、`--scenario FILE`、`--state-file PATH`。`--` 后面的命令必填。

### `skeptic proxy http`

`--upstream URL` 必填。`--listen HOST:PORT` 默认 `127.0.0.1:8765`。其余代理选项与 stdio 相同。

### `skeptic replay`

`--cassette FILE`，`--on-miss error|live`。`live` 必须在 `--` 后面带上游命令。

### `skeptic faults list`

`--class loud|silent|adversarial`，`--json`。未知类别的退出码为 2。

### `skeptic sandbox run NAME`

默认传输是 stdio。`--` 后面的参数传给沙箱，包括 `--http HOST:PORT` 和 `--state-file PATH`。名字是内置沙箱：`weather`、`fx`、`stocks`、`crm`、`orders`、`calendar`、`docs`、`sqlshop`、`mail`、`files`。

### `skeptic scenario validate PATHS`

`--json`。全部通过时退出码 0，校验失败时 3，找不到场景文件时 2。

### `skeptic scenario oracle PATHS`

`--faults none|all|ID,ID`，`--write-recoverability FILE`，`--seed INT`（默认 0）。干净 Oracle 失败时退出码为 1。

### `skeptic run`

`--suite NAME` 或可重复的 `--scenario PATH`。`--agent SPEC`（默认 `reference:fake/oracle_follower`）。`--profile ID`（默认 `silent-core`）。`--guards LIST或预设`（默认 `none`）。`--prompt-variant plain|evidence_contract`（默认 `plain`）。`--seeds 1,2,3`（默认 `1`）。`--concurrency N`（默认 4）。`--max-cost-usd F`。`--out DIR`（默认 `runs/<run_id>`）。`--resume`。`--ledger PATH`。

run id 形如 `20261105-142233-a1b2c3`（UTC 时间戳加 6 位十六进制）。达到预算上限时停止新回合，退出码为 5。已经完成的结果会保留。

### `skeptic bench run`

`--matrix FILE`、`--resume`、`--max-cost-usd F`、`--concurrency N`、`--out DIR`、`--ledger PATH`、`--dry-run`、`--count`。`--count` 打印回合总数后退出。`--dry-run` 打印展开后的配置和同一个总数。

### `skeptic report RUN_DIR`

`--format html,md,json,junit,sarif,badge`（这就是默认值；可以传子集或 `all`）。`--out DIR` 默认就是运行目录。文件：`report.html`、`report.md`、`report.json`、`junit.xml`、`skeptic.sarif`、`badge.svg`。

### `skeptic compare RUN_A RUN_B`

`--format md|json`（默认 `md`）。

### `skeptic gate RUN_DIR`

`--min-sks F`、`--max-fsr F`、`--max-icr F`。省略某个参数时，使用该次运行配置里的值（文件没写时是 `min_sks` 70、`max_fsr` 0.10、`max_icr` 0.00）。失败时退出码为 10。

### `skeptic mcp serve`

`--transport stdio|streamable-http|sse`（默认 `stdio`），`--host`（默认 `127.0.0.1`），`--port`（默认 `8765`）。工具：`list_faults`、`list_suites`、`run_suite`、`get_report`、`explain_episode`。`run_suite` 要求 `max_cost_usd`，大于 10 会拒绝。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 未分类错误 |
| 2 | 用法错误 |
| 3 | 配置或 Schema 无效 |
| 4 | 上游进程启动失败 |
| 5 | 达到预算上限 |
| 10 | 门禁未通过 |

[配置参考](config.md) 是 `init` 写出的文件。[快速开始](../quickstart.md) 把 FakeLLM 路径从头跑到尾。
