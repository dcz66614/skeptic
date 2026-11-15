# pip-audit Report - R80 Release Hardening

Date: 2026-11-15
Host: Windows x86_64
Python: CPython 3.12.13
Environment: Clean virtualenv with only `skeptic_agent-0.0.0-py3-none-any.whl` installed (default runtime dependencies, 49 packages)

## Audit Command
```powershell
uvx pip-audit --path "$TEMP\clean-skeptic-venv\Lib\site-packages" --desc on
```

## Results
```
No known vulnerabilities found
Name          Skip Reason
------------- ----------------------------------------------------------------------------
skeptic-agent Dependency not found on PyPI and could not be audited: skeptic-agent (0.0.0)
```

No high or critical vulnerabilities found in default runtime dependencies.
