Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location -Path (Resolve-Path (Join-Path $PSScriptRoot ".."))

uv sync --locked --all-extras
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run mypy src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
uv run pytest -m "not live" --cov=skeptic_agent --cov-fail-under=85
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
