# Skeptic v1.0.0 Release Checklist

Date: 2026-11-15
Release Milestone: R80 (Release Hardening) / Base: d879d4c / Branch: task/R80

## 1. Security & Hygiene
- [x] **Gitleaks Scan**: Full git history scanned (142 commits). Clean (0 leaks). Canary fixture token allowlisted via regex in `.gitleaks.toml` (`(?i)SKC-CANARY-[A-Za-z0-9_-]+`) and `.gitleaksignore`. Record: `docs/reports/r80-gitleaks.txt`.
- [x] **Dependency License Compliance**: Runtime dependencies scanned via `pip-licenses`. 0 GPL/AGPL dependencies. Record: `docs/reports/r80-license-scan.md`.
- [x] **Vulnerability Audit**: `pip-audit` run against clean venv runtime dependencies (`pip-audit 2.10.1`). 0 high/critical vulnerabilities. Record: `docs/reports/r80-pip-audit.md`.
- [x] **Security Policy**: `SECURITY.md` added with vulnerability disclosure policy and responsible-use terms. No fake public emails; GitHub private reporting routed to post-R81 repository creation.
- [x] **Legal & Community Policies**: `NOTICE` (Apache-2.0 and third-party notices), `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md` created.

## 2. Packaging & Path Resolution
- [x] **Wheel Package Data**: Hatchling wheel packaging configured via `tool.hatch.build.targets.wheel.force-include` to ship `schemas/*.json` as package data under `skeptic_agent/data/schemas/`, along with `recoverability.json` and fake LLM scripts.
- [x] **importlib.resources Resolution**: Replaced brittle `parents[3]` schema and resource paths across `validate.py`, `profiles.py`, `findings.py`, `episode.py`, `matrix.py`, `fake_llm.py`, `suites.py`, `oracle.py` with `importlib.resources` loaders and repo-checkout fallbacks.
- [x] **Packaging Unit Test**: `tests/unit/test_packaging_schema.py` verifying package data and schema resolution passes.

## 3. Platform Verification & Quickstart
- [x] **Windows Wheel Quickstart**: Fresh wheel built (`skeptic_agent-0.0.0-py3-none-any.whl`) and installed in clean virtual environment (`$TEMP\clean-skeptic-venv`). All 6 Quickstart commands (`--version`, `faults list`, `scenario validate`, `run`, `report`, `gate`) passed. Record: `docs/reports/r80-quickstart-windows.log`.
- [x] **Linux Wheel Quickstart**: Fresh wheel of a663957 built on the Linux box (CPython 3.12.15), installed in a clean venv with only the wheel. All 6 Quickstart commands passed (`--version` 0.0.0, `faults list` 20 faults, `scenario validate` PASS, FakeLLM `run` SKS 100.00 / 1 episode, `report` 6 files, `gate` PASSED). Earlier d879d4c run had failed on missing packaged schemas. Record: `docs/reports/r80-quickstart-linux.log` and `docs/reports/r80-quickstart-linux-notes.md`.
- [x] **macOS Wheel Quickstart**: WAIVED pending R1 approval (reason: no macOS hardware available in this execution environment).

## 4. Performance & Reliability
- [x] **P17 Performance Retest**: 5,000 samples/transport and 5,000 concurrent calls tested on Windows (`tests/perf/bench_proxy.py`). stdio p50=0.306 ms / p99=0.488 ms; HTTP p50=3.169 ms / p99=5.280 ms; 0 concurrency errors / mismatches. Acceptance passed. Documented in `docs/perf.md` and `docs/reports/r80-perf.json`.

## 5. Documentation & Site
- [x] **MkDocs Strict Build**: `uv run mkdocs build --strict` passed cleanly (English & Chinese locales).
- [x] **Link Verification**: Internal documentation links validated with 0 broken links.

## 6. Human Release Gates (Not for automated agent completion)
- [ ] **K58**: PyPI Trusted Publishing setup and credentials (human release gate).
- [ ] **R81**: GitHub repository creation, `v1.0.0` tagging, GitHub Release, and GitHub Marketplace Action publication (human release gate).
- [ ] **R83**: Publicity launch execution and community announcements (human release gate).
