"""Unit tests for Leaderboard model selection, matrix expansion, and budget estimation.

Covers L70, S16.1, and S16.2.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from skeptic_agent.runner.matrix import (
    count_matrix_episodes,
    expand_matrix_configs,
    load_matrix,
    load_models,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = REPO_ROOT / "bench" / "leaderboard" / "models.yaml"
MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1.yaml"
BUDGET_REPORT_FILE = REPO_ROOT / "docs" / "reports" / "leaderboard-budget.md"
MODELS_SCHEMA = REPO_ROOT / "schemas" / "models.schema.json"
MATRIX_SCHEMA = REPO_ROOT / "schemas" / "matrix.schema.json"


def test_models_yaml_schema_validity() -> None:
    """models.yaml must strictly validate against skeptic.models/v1 schema."""
    assert MODELS_FILE.is_file(), f"models.yaml missing at {MODELS_FILE}"
    schema = json.loads(MODELS_SCHEMA.read_text(encoding="utf-8"))
    data = yaml.safe_load(MODELS_FILE.read_text(encoding="utf-8"))

    jsonschema.validate(instance=data, schema=schema)
    assert data["schema"] == "skeptic.models/v1"


def test_models_yaml_s16_1_model_selection_rules() -> None:
    """Validate that models.yaml strictly implements S16.1 model selection rules.

    Rules:
      - 3 closed-frontier (Anthropic, OpenAI, Google flagships)
      - 2 closed-small (latest compact/fast models)
      - 3 open-weight (at least 2 domestic/CN)
      - All 8 leaderboard models support tools and have OpenRouter IDs
      - 1 dev-tier model with total cost <= $1/Mtok
    """
    models = load_models(MODELS_FILE)
    leaderboard_models = [m for m in models if m.get("tier") == "leaderboard"]
    assert len(leaderboard_models) == 8, (
        f"Expected 8 leaderboard models, found {len(leaderboard_models)}"
    )

    # All leaderboard models must start with openrouter/ and support tools
    for m in leaderboard_models:
        assert m["id"].startswith("openrouter/"), f"Model ID must start with openrouter/: {m['id']}"
        assert m["supports_tools"] is True, f"Model must support tools: {m['id']}"
        assert len(m["notes"].strip()) > 0, f"Model must have selection notes: {m['id']}"
        assert m["price_in_per_mtok"] >= 0.0
        assert m["price_out_per_mtok"] >= 0.0

    # 1. 3 closed-frontier
    frontier = [m for m in leaderboard_models if m["group"] == "closed-frontier"]
    assert len(frontier) == 3, f"Expected 3 closed-frontier models, got {len(frontier)}"
    frontier_ids = {m["id"] for m in frontier}
    assert "openrouter/anthropic/claude-3.5-sonnet" in frontier_ids
    assert "openrouter/openai/gpt-4o" in frontier_ids
    assert "openrouter/google/gemini-pro-1.5" in frontier_ids

    # 2. 2 closed-small
    small = [m for m in leaderboard_models if m["group"] == "closed-small"]
    assert len(small) == 2, f"Expected 2 closed-small models, got {len(small)}"
    small_ids = {m["id"] for m in small}
    assert "openrouter/anthropic/claude-3.5-haiku" in small_ids
    assert "openrouter/google/gemini-flash-1.5" in small_ids

    # 3. 3 open-weight (at least 2 domestic / CN)
    open_weight = [m for m in leaderboard_models if m["group"] == "open-weight"]
    assert len(open_weight) == 3, f"Expected 3 open-weight models, got {len(open_weight)}"
    cn_models = [m for m in open_weight if m["origin"] == "cn"]
    assert len(cn_models) >= 2, f"Expected at least 2 CN open-weight models, got {len(cn_models)}"
    ow_ids = {m["id"] for m in open_weight}
    assert "openrouter/deepseek/deepseek-chat" in ow_ids
    assert "openrouter/qwen/qwen-2.5-72b-instruct" in ow_ids
    assert "openrouter/meta-llama/llama-3.3-70b-instruct" in ow_ids

    # 4. Exactly 1 dev-tier model per S16.1
    dev_models = [m for m in models if m.get("tier") == "dev"]
    assert len(dev_models) == 1, f"Expected exactly 1 tier: dev model, got {len(dev_models)}"
    dev = dev_models[0]
    assert dev["id"] == "openrouter/openai/gpt-4o-mini"
    assert dev["price_in_per_mtok"] + dev["price_out_per_mtok"] <= 1.0

    # 5. Non-leaderboard experiment-tier models isolated from S16.1 tiers
    experiment_models = [m for m in models if m.get("tier") == "experiment"]
    assert len(experiment_models) == 3, (
        f"Expected 3 experiment tier models, got {len(experiment_models)}"
    )
    exp_ids = {m["id"] for m in experiment_models}
    assert exp_ids == {"compat/deepseek-v4-pro", "compat/gpt-5.6-terra", "compat/hy3"}
    for m in experiment_models:
        assert m["id"].startswith("compat/"), f"Experiment model must start with compat/: {m['id']}"
        assert "128api" in m["notes"] or "WorkBuddy" in m["notes"], (
            f"Experiment model notes must document 128api or WorkBuddy: {m['id']}"
        )
        assert "not an OpenRouter slug" in m["notes"] or "not OpenRouter" in m["notes"], (
            f"Experiment model notes must clarify it is not an OpenRouter slug: {m['id']}"
        )


def test_leaderboard_v1_matrix_validation_and_expansion() -> None:
    """Validate leaderboard-v1 matrix against schema and verify 24 expanded configs (S16.2)."""
    assert MATRIX_FILE.is_file(), f"Matrix file missing at {MATRIX_FILE}"
    schema = json.loads(MATRIX_SCHEMA.read_text(encoding="utf-8"))
    data = yaml.safe_load(MATRIX_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)

    matrix = load_matrix(MATRIX_FILE)
    assert matrix.id == "leaderboard-v1"
    assert matrix.suite == "core-v1"
    assert matrix.seeds == [1, 2, 3]
    assert matrix.max_cost_usd == 1300.0
    assert matrix.profiles == ["loud-core", "silent-core", "adversarial-core", "cross-source"]

    # Expand configs
    expanded = expand_matrix_configs(matrix, models_path=MODELS_FILE)
    # 8 ref:none + 8 ref:recommended + 2*4 framework adapters = 24 configs
    assert len(expanded) == 24, f"Expected 24 expanded configs, got {len(expanded)}"

    # Check configuration groups
    ref_none = [c for c in expanded if c.agent.startswith("reference:") and c.guards == "none"]
    ref_rec = [
        c for c in expanded if c.agent.startswith("reference:") and c.guards == "recommended"
    ]
    openai_cfgs = [c for c in expanded if c.agent.startswith("openai-agents:")]
    langgraph_cfgs = [c for c in expanded if c.agent.startswith("langgraph:")]
    crewai_cfgs = [c for c in expanded if c.agent.startswith("crewai:")]
    pydantic_cfgs = [c for c in expanded if c.agent.startswith("pydantic-ai:")]

    assert len(ref_none) == 8
    assert len(ref_rec) == 8
    assert len(openai_cfgs) == 2
    assert len(langgraph_cfgs) == 2
    assert len(crewai_cfgs) == 2
    assert len(pydantic_cfgs) == 2


def test_leaderboard_matrix_episode_counts() -> None:
    """Verify exact episode counts for leaderboard-v1 matrix across profiles and seeds."""
    matrix = load_matrix(MATRIX_FILE)
    total_episodes = count_matrix_episodes(matrix, models_path=MODELS_FILE)

    # 24 configs * 3 seeds * 3219 episodes/seed = 231,768 episodes
    assert total_episodes == 231_768, f"Expected 231,768 total episodes, got {total_episodes}"


def test_leaderboard_budget_report_contents() -> None:
    """Verify that docs/reports/leaderboard-budget.md exists and covers all required contents."""
    assert BUDGET_REPORT_FILE.is_file(), f"Budget report missing at {BUDGET_REPORT_FILE}"
    content = BUDGET_REPORT_FILE.read_text(encoding="utf-8")

    # Verify all 3 tiers are documented
    assert "Tier 1: 完整方案" in content or "完整方案" in content
    assert "Tier 2: 节省方案" in content or "节省方案" in content
    assert "Tier 3: 最低方案" in content or "最低方案" in content

    # Verify budget caps (reconciled in L70fix2)
    assert "2,250.00" in content
    assert "1,520.00" in content
    assert "780.00" in content
    # S16.2 original ceiling discussed as insufficient at empirical token rates
    assert "1,300" in content
    assert "insufficient" in content.lower()

    # Verify reconciled base totals
    assert "2,135.10" in content
    assert "1,423.40" in content
    assert "717.67" in content

    # Verify reconciled smoke suite total
    assert "70.31" in content

    # Verify empirical token averages and unit costs
    assert "3,736" in content or "3736" in content
    assert "453" in content or "453.57" in content
    assert "0.018012" in content
    assert "0.013876" in content

    # Verify episode counts
    assert "231,768" in content
    assert "154,512" in content
    assert "77,904" in content

    # Verify model names
    assert "Claude 3.5 Sonnet" in content
    assert "GPT-4o" in content
    assert "Gemini 1.5 Pro" in content
    assert "Claude 3.5 Haiku" in content
    assert "Gemini 1.5 Flash" in content
    assert "DeepSeek V3" in content
    assert "Qwen 2.5 72B Instruct" in content
    assert "Llama 3.3 70B Instruct" in content

    # Verify compliance, experiment-tier split, and H3 approval section
    assert "Zero Paid Network Calls" in content or "zero paid" in content.lower()
    assert "experiment" in content.lower()
    assert "H3" in content
