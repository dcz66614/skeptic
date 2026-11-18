# Changelog

## Unreleased / preview

- Preview release 0.1.0a1: early open-source preview on GitHub only, not v1.0.0, not on PyPI, no tag or GitHub Release. The official S16.2 leaderboard run has not been done and no official leaderboard results are claimed.
- Docs workflow: Pages deploy is gated on the repository variable `ENABLE_PAGES == 'true'` (not set; Pages is not enabled). `mkdocs build --strict` always runs.
- SECURITY.md points to GitHub private vulnerability reporting.
- Release hardening (R80): package schemas in wheel via hatch force-include, resolve resources via importlib.resources, allowlist synthetic test canaries in gitleaks, and verify clean-venv quickstart and performance.
- Add the reduced-scope L74 LaTeX technical report and PDF under paper/.
- Add the composite GitHub Action (`action.yml`) that runs a suite, publishes the report, and gates on SKS.
- Add the bilingual MkDocs site (English and Chinese), the docs workflow, and a quickstart that runs on FakeLLM.
- Add the leaderboard static site generator (`site/build.py`) and the S16.3 pages.
- Add the R82 launch drafts in `docs/launch/` and the README hero figures from the G53 `compat/hy3` runs.
- Add the six built-in fault profiles, the `skeptic faults list` command, and the fault and profile methodology docs.
- Add the fault engine framework: scheduling, profile expansion, JSONPath helpers, and call_index assigned before the fault pre-hook (ADR-0007).
- Add the interceptor pipeline with fault, guard and recorder mount points, and the per-episode context with pending calls and per-tool call counts.
- Detect the MCP protocol era (legacy, modern, unknown) from the HTTP header or the first client message.
- Add the JSON-RPC 2.0 message model, line framing, and canonical JSON hashing.
- Freeze ADRs 0001–0005 and Draft 2020-12 schemas for config, cassette, profile, scenario, result, report, findings, matrix, and models.
- Scaffold the `skeptic-agent` package, CI workflow, and local check scripts.
- Drop AGPL `crewai-tools` from the `crewai` extra; keep `crewai` and add `mcpadapt`.
