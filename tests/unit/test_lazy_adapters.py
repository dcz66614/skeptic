"""Test that runner adapters and optional framework deps load lazily (E49fix).

Ensures that importing skeptic_agent.report or skeptic_agent.runner.matrix does not
eagerly import crewai, langgraph, agents, or pydantic_ai.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_report_and_matrix_without_optional_framework_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing skeptic_agent.report and runner.matrix must succeed with optional deps blocked."""
    # Clean up any previously cached imports of optional frameworks and skeptic adapters
    blocked_prefixes = (
        "crewai",
        "langgraph",
        "agents",
        "pydantic_ai",
        "fastmcp",
        "mcpadapt",
        "langchain",
    )
    for mod_name in list(sys.modules.keys()):
        if any(
            mod_name == prefix or mod_name.startswith(f"{prefix}.") for prefix in blocked_prefixes
        ):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)
        if mod_name.startswith("skeptic_agent.runner.adapters") or mod_name in (
            "skeptic_agent.report",
            "skeptic_agent.report.loader",
            "skeptic_agent.runner.matrix",
            "skeptic_agent.runner.episode",
        ):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    # Block optional frameworks in sys.modules
    for prefix in ["crewai", "langgraph", "agents", "pydantic_ai"]:
        monkeypatch.setitem(sys.modules, prefix, None)

    import skeptic_agent.report
    import skeptic_agent.runner.matrix
    from skeptic_agent.runner.adapters import ADAPTERS, get_adapter

    assert skeptic_agent.report is not None
    assert skeptic_agent.runner.matrix is not None

    # Core adapters work
    assert "reference" in ADAPTERS
    assert "command" in ADAPTERS
    assert get_adapter("reference").name == "reference"
    assert get_adapter("command").name == "command"

    # Optional framework adapters raise clear error naming the missing extra
    with pytest.raises(ImportError, match="crewai"):
        get_adapter("crewai")

    with pytest.raises(ImportError, match="langgraph"):
        get_adapter("langgraph")

    with pytest.raises(ImportError, match="openai-agents"):
        get_adapter("openai-agents")

    with pytest.raises(ImportError, match="pydantic-ai"):
        get_adapter("pydantic-ai")


def test_clean_subprocess_import_with_blocked_frameworks() -> None:
    """Verify in a clean Python process that report and matrix load without optional deps."""
    code = """
import sys
sys.modules['crewai'] = None
sys.modules['langgraph'] = None
sys.modules['agents'] = None
sys.modules['pydantic_ai'] = None

import skeptic_agent.report
import skeptic_agent.runner.matrix
from skeptic_agent.runner.adapters import get_adapter

# Reference and command should work
assert get_adapter('reference').name == 'reference'
assert get_adapter('command').name == 'command'

# Blocked adapters must name the missing extra
for name, extra in [
    ('crewai', 'crewai'),
    ('langgraph', 'langgraph'),
    ('openai-agents', 'openai-agents'),
    ('pydantic-ai', 'pydantic-ai'),
]:
    try:
        get_adapter(name)
        raise AssertionError(f"Expected ImportError for {name}")
    except ImportError as exc:
        assert extra in str(exc), f"Missing extra {extra} not in {exc}"
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, f"Subprocess failed:\n{result.stderr}\n{result.stdout}"
