# Schemas

JSON Schema Draft 2020-12, one file per document in `schemas/`. The `schema` field inside a document is the short id. The schema file's `$id` is the URN.

| File | Document `schema` | `$id` | What it is |
|---|---|---|---|
| `config.schema.json` | `skeptic.config/v1` | `urn:skeptic:schema:config:v1` | `skeptic.yaml` |
| `cassette.schema.json` | `skeptic.cassette/v1` | `urn:skeptic:schema:cassette:v1` | One recorded episode, JSONL |
| `profile.schema.json` | `skeptic.profile/v1` | `urn:skeptic:schema:profile:v1` | Fault profile |
| `scenario.schema.json` | `skeptic.scenario/v1` | `urn:skeptic:schema:scenario:v1` | One evaluation scenario |
| `result.schema.json` | `skeptic.result/v1` | `urn:skeptic:schema:result:v1` | One episode result line in `results.jsonl` |
| `report.schema.json` | `skeptic.report/v1` | `urn:skeptic:schema:report:v1` | Run summary and report |
| `findings.schema.json` | `skeptic.findings/v1` | `urn:skeptic:schema:findings:v1` | Reliability-audit findings |
| `matrix.schema.json` | `skeptic.matrix/v1` | `urn:skeptic:schema:matrix:v1` | Benchmark matrix |
| `models.schema.json` | `skeptic.models/v1` | `urn:skeptic:schema:models:v1` | Leaderboard model list |

`skeptic scenario validate` checks scenario files against `scenario.schema.json` and the semantic rules. `skeptic report` writes `report.json` as `skeptic.report/v1`. The field-by-field config example is on the [configuration](config.md) page. The fault profile fields are in the [fault notes](../methodology/faults.md).
