# Schema

JSON Schema Draft 2020-12，`schemas/` 里每种文档一个文件。文档内部的 `schema` 字段是短 id。Schema 文件的 `$id` 是 URN。

| 文件 | 文档里的 `schema` | `$id` | 是什么 |
|---|---|---|---|
| `config.schema.json` | `skeptic.config/v1` | `urn:skeptic:schema:config:v1` | `skeptic.yaml` |
| `cassette.schema.json` | `skeptic.cassette/v1` | `urn:skeptic:schema:cassette:v1` | 一个录制好的回合，JSONL |
| `profile.schema.json` | `skeptic.profile/v1` | `urn:skeptic:schema:profile:v1` | 故障画像 |
| `scenario.schema.json` | `skeptic.scenario/v1` | `urn:skeptic:schema:scenario:v1` | 一个评测场景 |
| `result.schema.json` | `skeptic.result/v1` | `urn:skeptic:schema:result:v1` | `results.jsonl` 里的一行回合结果 |
| `report.schema.json` | `skeptic.report/v1` | `urn:skeptic:schema:report:v1` | 运行汇总和报告 |
| `findings.schema.json` | `skeptic.findings/v1` | `urn:skeptic:schema:findings:v1` | 可靠性审计的发现 |
| `matrix.schema.json` | `skeptic.matrix/v1` | `urn:skeptic:schema:matrix:v1` | 评测矩阵 |
| `models.schema.json` | `skeptic.models/v1` | `urn:skeptic:schema:models:v1` | 榜单模型清单 |

`skeptic scenario validate` 用 `scenario.schema.json` 和语义规则检查场景文件。`skeptic report` 写出的 `report.json` 是 `skeptic.report/v1`。配置字段的例子在[配置](config.md)页。故障画像的字段在[故障说明](../methodology/faults.md)。
