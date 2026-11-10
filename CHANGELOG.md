# Changelog

## Unreleased

- Add the composite GitHub Action (`action.yml`) that runs a suite, publishes the report, and gates on SKS.
- Add the bilingual MkDocs site (English and Chinese), the docs workflow, and a quickstart that runs on FakeLLM.
- Add the six built-in fault profiles, the `skeptic faults list` command, and the fault and profile methodology docs.
- Add the fault engine framework: scheduling, profile expansion, JSONPath helpers, and call_index assigned before the fault pre-hook (ADR-0007).
- Add the interceptor pipeline with fault, guard and recorder mount points, and the per-episode context with pending calls and per-tool call counts.
- Detect the MCP protocol era (legacy, modern, unknown) from the HTTP header or the first client message.
- Add the JSON-RPC 2.0 message model, line framing, and canonical JSON hashing.
- Freeze ADRs 0001–0005 and Draft 2020-12 schemas for config, cassette, profile, scenario, result, report, findings, matrix, and models.
- Scaffold the `skeptic-agent` package, CI workflow, and local check scripts.
- Drop AGPL `crewai-tools` from the `crewai` extra; keep `crewai` and add `mcpadapt`.
