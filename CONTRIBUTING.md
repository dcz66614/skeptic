# Contributing to Skeptic

Thank you for your interest in contributing to Skeptic!

## Principles

1. **Deterministic & Reproducible**: All scenario behaviors, fault injection catalogs, and benchmark evaluations must remain deterministic under fixed random seeds.
2. **Standard-Conforming**: Follow PEP 8 style, strict typing with `mypy`, and formatting enforced by `ruff`.
3. **No Secret Leaks**: Never commit real credentials, tokens, or API keys. Synthetic canary tokens must follow the `SKC-CANARY-*` naming convention.
4. **No Lock Churn**: Do not update or churn `uv.lock` unless adding a required dependency with explicit justification.

## Local Development Workflow

1. Clone or checkout the repository.
2. Sync the development environment:
   ```bash
   uv sync --all-extras
   ```
3. Run code formatting and linting:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```
4. Run strict type checking:
   ```bash
   uv run mypy src
   ```
5. Run unit and integration tests:
   ```bash
   uv run pytest -q
   ```
6. Build documentation:
   ```bash
   uv run mkdocs build --strict
   ```

## Pull Requests

- Keep changes focused and include relevant unit or integration tests.
- Ensure all CI checks (ruff, mypy, pytest) pass locally before submitting.
- Document any behavioral changes in docstrings or documentation.
