# ADR-0001: 总体架构与规格冻结

- 状态：采纳
- 日期：2026-10-28
- 提出者：T02　裁决者：R1

## 背景

Skeptic 是协议层 MCP 代理加评测套件。代理站在智能体和 MCP 服务器之间，按场景注入故障、记录 cassette、给结局打分，并可选地用 Guard 把静默失败显式化。T02 把第 4 部分冻结成 ADR 和 JSON Schema。冻结时有两处规格互相打架，按 0.6 的 D1/D3 在本 ADR 裁决。

(a) S1 的 `schemas/` 注释列出 8 个名字：config、cassette、profile、scenario、result、report、findings、matrix。T02 的交付要求 9 个，多出来的是 S16.1 的 `models`（`skeptic.models/v1`）。

(b) S1 把场景、套件和可恢复性缓存放在 `src/skeptic_agent/bench/`。0.2 的 D5 同样写这个路径。S37、S38 的交付和验收命令是仓库根的 `bench/scenarios/<sandbox>/*.yaml`。S39 写 `bench/suites/` 和 `bench/recoverability.json`。1.3 的 PR 体积排除项也是 `bench/scenarios/`。

## 选项（至少 2 个，各写优缺点）

### A. 包内场景，Schema 只写 S1 的 8 个

优点：目录树和 0.2 的 D5 与 S1 原文一致。
缺点：S37–S39 的命令、套件路径和 PR 排除项都对不上。200 个 YAML 会进入 wheel，而 S1 已经把不打包的评测数据放在仓库根 `bench/`。少写 `models` 则 S16.1 没有可校验的文件。

### B. 场景放在仓库根 `bench/`，Schema 写 9 个

优点：和 S37、S38、S39 的路径、S8.3 的 `bench/recoverability.json`、PR 排除项同一处。根 `bench/` 的注释已经是“不打包进 wheel”。`models.schema.json` 覆盖 S16.1。
缺点：S1 里的 `src/skeptic_agent/bench/` 和 0.2 的 D5 位置要改。计划书正文由 R0 更新，本 ADR 先生效。

## 决定

采纳 B。

场景语料不进 Python 包。路径固定为：

- `bench/scenarios/<sandbox>/*.yaml`
- `bench/suites/*.yaml`（smoke、core-v1、zh-v1）
- `bench/recoverability.json`

不创建 `src/skeptic_agent/bench/`。内置画像仍在 `src/skeptic_agent/data/profiles/`（S1 与 F25 一致）。根 `bench/` 继续放矩阵、榜单模型和账本。

Schema 共 9 个，Draft 2020-12，放在 `schemas/`：`config`、`cassette`、`profile`、`scenario`、`result`、`report`、`findings`、`matrix`、`models`。第 9 个是 `schemas/models.schema.json`，标识 `skeptic.models/v1`。

除下列开放对象外，所有对象 `additionalProperties: false`。开放对象不设 `additionalProperties: false`：`params`、JSON-RPC 的 `raw` 和 `final`、oracle 步骤的 `args`、`args_match`、服务器的 `env` 和 `headers`。`_meta` 出现在 JSON-RPC 消息内部，随 `raw` / `final` 开放，各文档顶层没有 `_meta` 字段。键集合有穷的映射（`alternates`、oracle `expect`、`recovery`、`servers`、`by_fault`、`by_sandbox`）用 `patternProperties` 加上 `additionalProperties: false`。

仓库其余布局按 S1：单包 `src/skeptic_agent/`，代理、录制、故障、Guard、场景、运行器、评分、报告、`setup/`、`mcpserver/`、`sandboxes/` 分目录。`action.yml`、`skills/`、`site/`、`paper/`、`examples/`、`tests/` 在仓库根。

协议按 S4 冻结：

- stdio 为 UTF-8，一行一条 JSON-RPC，以 `\n` 分帧。未修改的消息按原始字节写出。修改过的消息用 `json.dumps(msg, ensure_ascii=False, separators=(",", ":"))`。上游 stderr 原样转到代理 stderr。
- HTTP 代理暴露 `POST {listen}/mcp`，转发到 `--upstream`。去掉 hop-by-hop 头，其余头透传，包括 `Authorization`、`MCP-Protocol-Version`、`Mcp-Method`、`Mcp-Name`、`Mcp-Session-Id`。`application/json` 按消息走管线。`text/event-stream` 里每个 `data:` 的 JSON-RPC 走管线后按原顺序发出。`GET` 和 `DELETE` 原样转发。
- 时代识别按 S4.2：请求头 `mcp-protocol-version`（比较时不区分大小写）≥ `2026-07-28` 为 modern，否则 legacy；`initialize` 为 legacy；`server/discover` 为 modern `2026-07-28`；`params._meta` 里的 `io.modelcontextprotocol/protocolVersion` 为 modern；其余为 unknown。unknown 仍注入故障和防护，cassette 头记 `era: unknown`。版本字符串按字典序比较。
- 关联表的键是 `(direction, id)`。代理自己发出的请求 id 为 `"skeptic-<uuid4>"`，其响应不转发给客户端。`call_index` 从 1 起，计同一 episode 内某工具被转发到上游的尝试次数，Guard 重试计入。
- 管线顺序按 S4.4：c2s `tools/call` 为录制、G06、G07、故障前置（L04、L06、L07、S05、S10）、转发或直接回复或丢弃。s2c `tools/call` 响应为故障后置（L01、L02、L03、L05、S01–S04、S06–S09、A01）、G05、G02/G03/G04、G01、G07、录制最终消息、发给客户端。s2c `tools/list` 为故障（L06、L07、A02、A03）、G08、录制、发出。其他消息只录制并原样透传。
- 工具结果形状、`resultType` 不是 `"complete"` 时原样透传、静默故障保持 `isError` 缺省或 false、`structuredContent` 与首个 JSON 文本块的同步改写、显式化对象的统一形状，均按 S4.5。

文档里的 Guard 标识用 S11 的名字，不用 G 编号。对照：G01 `evidence_contract`，G02 `schema_guard`，G03 `staleness_guard`，G04 `emptiness_guard`，G05 `retry_guard`，G06 `loop_breaker`，G07 `injection_shield`，G08 `drift_lock`。预设名为 `none`、`all`、`recommended`。

## 影响（需要修改的规格条目、代码、文档）

- S1：`schemas/` 注释补上 `models`。删除 `src/skeptic_agent/bench/`。场景、套件、可恢复性缓存改到仓库根 `bench/`。
- 0.2 交付 D5 的位置从 `src/skeptic_agent/bench/` 改为 `bench/`。
- S37、S38、S39 的路径已经与本决定一致，不用改命令。
- R0 在计划书副本中更新上述两条。本 ADR 生效前，实现以本决定为准。
- 后续任务不得把场景 YAML 打进 wheel。
