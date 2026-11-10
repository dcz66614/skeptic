"""Unit tests for D61 example repositories (01-claude-code, 02-langgraph, 03-github-action)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"
CONFIG_SCHEMA_PATH = REPO_ROOT / "schemas" / "config.schema.json"


def _lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def test_examples_directory_structure() -> None:
    """Verify that all three D61 example directories exist with README and runnable scripts."""
    for dirname in ("01-claude-code", "02-langgraph", "03-github-action"):
        example_path = EXAMPLES_DIR / dirname
        assert example_path.is_dir(), f"Missing example directory: {example_path}"
        assert (example_path / "README.md").is_file(), f"Missing README.md in {dirname}"
        assert (example_path / "run.py").is_file(), f"Missing run.py in {dirname}"


def test_01_claude_code_configuration_assets() -> None:
    """Verify Claude Code example configuration before/after files and proxy args format."""
    c1_dir = EXAMPLES_DIR / "01-claude-code"
    before_file = c1_dir / ".mcp.json.before"
    after_file = c1_dir / ".mcp.json.after"
    mcp_file = c1_dir / ".mcp.json"

    assert before_file.is_file(), "Missing .mcp.json.before"
    assert after_file.is_file(), "Missing .mcp.json.after"
    assert mcp_file.is_file(), "Missing .mcp.json"

    before_data = json.loads(before_file.read_text(encoding="utf-8"))
    after_data = json.loads(after_file.read_text(encoding="utf-8"))

    assert "mcpServers" in before_data
    assert "mcpServers" in after_data

    # Check that after wrap routes through skeptic proxy stdio
    for _srv_name, entry in after_data["mcpServers"].items():
        assert entry["command"] == "skeptic"
        args = entry["args"]
        assert args[0] == "proxy"
        assert args[1] == "stdio"
        assert "--profile" in args
        assert "--guards" in args
        assert "--record" in args
        assert "--" in args
        # Upstream command preserved after --
        sep_idx = args.index("--")
        assert args[sep_idx + 1] == "python"


def test_02_langgraph_assets_and_workflow() -> None:
    """Verify LangGraph example config, schema, and workflow sync."""
    lg_dir = EXAMPLES_DIR / "02-langgraph"
    assert (lg_dir / "agent.py").is_file()
    assert (lg_dir / "skeptic.yaml").is_file()
    assert (lg_dir / "workflow.yml").is_file()

    # Validate skeptic.yaml against config.schema.json
    config_data = yaml.safe_load((lg_dir / "skeptic.yaml").read_text(encoding="utf-8"))
    config_schema = json.loads(CONFIG_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=config_data, schema=config_schema)

    # Verify workflow.yml sync with .github/workflows/example-langgraph.yml
    ci_workflow = REPO_ROOT / ".github" / "workflows" / "example-langgraph.yml"
    assert ci_workflow.is_file(), "Missing .github/workflows/example-langgraph.yml"
    assert _lf(lg_dir / "workflow.yml") == _lf(ci_workflow)


def test_03_github_action_assets() -> None:
    """Verify GitHub Action example assets."""
    ga_dir = EXAMPLES_DIR / "03-github-action"
    assert (ga_dir / "workflow.yml").is_file()
    assert (ga_dir / "README.md").is_file()
    assert (ga_dir / "run.py").is_file()

    # Verify README documents run.py
    readme_text = (ga_dir / "README.md").read_text(encoding="utf-8")
    assert "run.py" in readme_text
