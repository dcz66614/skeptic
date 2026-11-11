"""Unit tests for L71 reduced-scope free run matrix, suites, and methodology.

Covers:
- Verification that official leaderboard-v1.yaml is unchanged (S16.2 $1300 ceiling, 24 configs).
- Validation and deterministic selection rules for core-v1-l71-reduced and core-v1-l71-hy3 suites.
- Validation, schema compliance, and expansion of reduced-free matrices.
- Registration and $0.0 pricing of experiment models.
- Episode counts determinism and CLI --count parity (892 and 168).
- Methodology documentation and budget pointer integrity.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import jsonschema
import pytest
import yaml

from skeptic_agent.runner.llm import get_model_pricing
from skeptic_agent.runner.matrix import (
    count_matrix_episodes,
    expand_matrix_configs,
    load_matrix,
    load_models,
)
from skeptic_agent.scenario.suites import load_suite, resolve_suite_scenarios

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = REPO_ROOT / "bench" / "leaderboard" / "models.yaml"
MODELS_SCHEMA = REPO_ROOT / "schemas" / "models.schema.json"
MATRIX_SCHEMA = REPO_ROOT / "schemas" / "matrix.schema.json"

OFFICIAL_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1.yaml"
REDUCED_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-free.yaml"
HY3_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-free-hy3.yaml"

CORE_V1_SUITE_FILE = REPO_ROOT / "bench" / "suites" / "core-v1.yaml"
REDUCED_SUITE_FILE = REPO_ROOT / "bench" / "suites" / "core-v1-l71-reduced.yaml"
HY3_SUITE_FILE = REPO_ROOT / "bench" / "suites" / "core-v1-l71-hy3.yaml"

L71_METHODOLOGY_FILE = REPO_ROOT / "docs" / "reports" / "leaderboard-l71-reduced.md"
BUDGET_REPORT_FILE = REPO_ROOT / "docs" / "reports" / "leaderboard-budget.md"


def test_official_leaderboard_v1_matrix_unchanged() -> None:
    """Official S16.2 matrix must remain unchanged until a future official H3 approval."""
    assert OFFICIAL_MATRIX_FILE.is_file()
    schema = json.loads(MATRIX_SCHEMA.read_text(encoding="utf-8"))
    raw_data = yaml.safe_load(OFFICIAL_MATRIX_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=raw_data, schema=schema)

    matrix = load_matrix(OFFICIAL_MATRIX_FILE)
    assert matrix.id == "leaderboard-v1"
    assert matrix.suite == "core-v1"
    assert matrix.profiles == ["loud-core", "silent-core", "adversarial-core", "cross-source"]
    assert matrix.seeds == [1, 2, 3]
    assert matrix.max_cost_usd == 1300.0

    expanded = expand_matrix_configs(matrix, models_path=MODELS_FILE)
    assert len(expanded) == 24
    ref_none = [c for c in expanded if c.agent.startswith("reference:") and c.guards == "none"]
    ref_rec = [
        c for c in expanded if c.agent.startswith("reference:") and c.guards == "recommended"
    ]
    frameworks = [c for c in expanded if not c.agent.startswith("reference:")]
    assert len(ref_none) == 8
    assert len(ref_rec) == 8
    assert len(frameworks) == 8

    total_episodes = count_matrix_episodes(matrix, models_path=MODELS_FILE)
    assert total_episodes == 231_768


def test_reduced_suites_structure_and_deterministic_selection() -> None:
    """Validate scenario counts, sandbox order, and deterministic subset rule for new suites."""
    assert REDUCED_SUITE_FILE.is_file()
    assert HY3_SUITE_FILE.is_file()

    core_v1 = load_suite(CORE_V1_SUITE_FILE)
    reduced = load_suite(REDUCED_SUITE_FILE)
    hy3 = load_suite(HY3_SUITE_FILE)

    assert reduced.id == "core-v1-l71-reduced"
    assert hy3.id == "core-v1-l71-hy3"

    assert len(reduced.scenarios) == 56
    assert len(hy3.scenarios) == 10

    # All scenarios must be drawn from core-v1
    core_scenarios_set = set(core_v1.scenarios)
    assert set(reduced.scenarios).issubset(core_scenarios_set)
    assert set(hy3.scenarios).issubset(core_scenarios_set)

    # hy3 must be a strict subset of reduced
    assert set(hy3.scenarios).issubset(set(reduced.scenarios))

    # Verify deterministic selection rule:
    # 1. Group core-v1 scenarios by sandbox directory in appearance order:
    by_sb: dict[str, list[str]] = defaultdict(list)
    for s in core_v1.scenarios:
        sb = s.split("/")[2]
        by_sb[sb].append(s)

    expected_sandboxes = [
        "calendar",
        "crm",
        "docs",
        "files",
        "fx",
        "mail",
        "orders",
        "sqlshop",
        "stocks",
        "weather",
    ]
    assert list(by_sb.keys()) == expected_sandboxes

    # First 6 sandboxes contribute first 6 scenarios, remaining 4 contribute first 5:
    expected_reduced: list[str] = []
    for sb in expected_sandboxes[:6]:
        expected_reduced.extend(by_sb[sb][:6])
    for sb in expected_sandboxes[6:]:
        expected_reduced.extend(by_sb[sb][:5])

    assert len(expected_reduced) == 56
    assert reduced.scenarios == expected_reduced

    # Hy3: exactly 1st scenario of each sandbox
    expected_hy3 = [by_sb[sb][0] for sb in expected_sandboxes]
    assert len(expected_hy3) == 10
    assert hy3.scenarios == expected_hy3

    # Ensure all scenarios resolve cleanly
    resolved_reduced = resolve_suite_scenarios(reduced)
    assert len(resolved_reduced) == 56

    resolved_hy3 = resolve_suite_scenarios(hy3)
    assert len(resolved_hy3) == 10


def test_reduced_matrices_validation_and_expansion() -> None:
    """Validate reduced matrices against matrix.schema.json and verify expanded configs."""
    schema = json.loads(MATRIX_SCHEMA.read_text(encoding="utf-8"))

    # 1. leaderboard-v1-reduced-free
    raw_red = yaml.safe_load(REDUCED_MATRIX_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=raw_red, schema=schema)

    matrix_red = load_matrix(REDUCED_MATRIX_FILE)
    assert matrix_red.id == "leaderboard-v1-reduced-free"
    assert matrix_red.suite == "core-v1-l71-reduced"
    assert matrix_red.profiles == ["silent-core"]
    assert matrix_red.seeds == [1]
    assert matrix_red.max_cost_usd == 5.0
    assert len(matrix_red.configs) == 2

    expanded_red = expand_matrix_configs(matrix_red, models_path=MODELS_FILE)
    assert len(expanded_red) == 2
    assert (
        expanded_red[0].agent == "reference:compat/our-free-model/deepseek-ai/deepseek-v4.1-flash"
    )
    assert expanded_red[0].guards == "none"
    assert expanded_red[0].prompt_variant == "plain"
    assert expanded_red[0].model == "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash"

    assert (
        expanded_red[1].agent == "reference:compat/our-free-model/deepseek-ai/deepseek-v4.1-flash"
    )
    assert expanded_red[1].guards == "recommended"
    assert expanded_red[1].prompt_variant == "plain"
    assert expanded_red[1].model == "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash"

    # 2. leaderboard-v1-reduced-free-hy3
    raw_hy3 = yaml.safe_load(HY3_MATRIX_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=raw_hy3, schema=schema)

    matrix_hy3 = load_matrix(HY3_MATRIX_FILE)
    assert matrix_hy3.id == "leaderboard-v1-reduced-free-hy3"
    assert matrix_hy3.suite == "core-v1-l71-hy3"
    assert matrix_hy3.profiles == ["silent-core"]
    assert matrix_hy3.seeds == [1]
    assert matrix_hy3.max_cost_usd == 5.0
    assert len(matrix_hy3.configs) == 2

    expanded_hy3 = expand_matrix_configs(matrix_hy3, models_path=MODELS_FILE)
    assert len(expanded_hy3) == 2
    assert expanded_hy3[0].agent == "reference:compat/hy3"
    assert expanded_hy3[0].guards == "none"
    assert expanded_hy3[0].prompt_variant == "plain"
    assert expanded_hy3[0].model == "compat/hy3"

    assert expanded_hy3[1].agent == "reference:compat/hy3"
    assert expanded_hy3[1].guards == "recommended"
    assert expanded_hy3[1].prompt_variant == "plain"
    assert expanded_hy3[1].model == "compat/hy3"


def test_experiment_models_registration_and_pricing() -> None:
    """Verify registration, notes, and $0.0 pricing for L71 experiment models."""
    models = load_models(MODELS_FILE)
    by_id = {m["id"]: m for m in models}

    free_dsh_id = "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash"
    assert free_dsh_id in by_id
    dsh = by_id[free_dsh_id]
    assert dsh["tier"] == "experiment"
    assert dsh["group"] == "open-weight"
    assert dsh["origin"] == "cn"
    assert dsh["supports_tools"] is True
    assert dsh["price_in_per_mtok"] == 0.0
    assert dsh["price_out_per_mtok"] == 0.0

    notes = dsh["notes"]
    assert "our-free-model" in notes
    assert "WorkBuddy" in notes
    assert "http://127.0.0.1:5390/v1" in notes
    assert "$0" in notes
    assert "not an OpenRouter slug" in notes or "not OpenRouter" in notes
    assert "deepseek-v4.1-flash" in notes
    assert "opencode" in notes

    # Confirm no opencode models were added. Paid flash-sg is an L71ds experiment.
    for m in models:
        mid = m["id"]
        assert not mid.startswith("opencode/"), f"Unauthorized opencode model found: {mid}"
        # L71ds registers compat/deepseek-v4.1-flash-sg separately;
        # that model is covered by tests/unit/test_leaderboard_l71_ds.py.

    # Check hy3 model
    assert "compat/hy3" in by_id
    hy3 = by_id["compat/hy3"]
    assert hy3["tier"] == "experiment"
    assert hy3["price_in_per_mtok"] == 0.0
    assert hy3["price_out_per_mtok"] == 0.0

    # Pricing resolution via get_model_pricing
    assert get_model_pricing(free_dsh_id, models_yaml=MODELS_FILE) == (0.0, 0.0)
    assert get_model_pricing("compat/hy3", models_yaml=MODELS_FILE) == (0.0, 0.0)


def test_reduced_matrix_episode_counts_deterministic() -> None:
    """Episode counts must be deterministic and match CLI --count command."""
    matrix_red = load_matrix(REDUCED_MATRIX_FILE)
    cnt_red = count_matrix_episodes(matrix_red, models_path=MODELS_FILE)
    assert cnt_red == 892

    matrix_hy3 = load_matrix(HY3_MATRIX_FILE)
    cnt_hy3 = count_matrix_episodes(matrix_hy3, models_path=MODELS_FILE)
    assert cnt_hy3 == 168

    # Verify CLI --count matches
    res_red = subprocess.run(
        [
            sys.executable,
            "-m",
            "skeptic_agent.cli",
            "bench",
            "run",
            "--matrix",
            str(REDUCED_MATRIX_FILE),
            "--count",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Total episodes: 892" in res_red.stdout

    res_hy3 = subprocess.run(
        [
            sys.executable,
            "-m",
            "skeptic_agent.cli",
            "bench",
            "run",
            "--matrix",
            str(HY3_MATRIX_FILE),
            "--count",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Total episodes: 168" in res_hy3.stdout


def test_methodology_note_and_budget_pointer_contents() -> None:
    """Verify docs/reports/leaderboard-l71-reduced.md and pointer in leaderboard-budget.md."""
    assert L71_METHODOLOGY_FILE.is_file()
    methodology_text = L71_METHODOLOGY_FILE.read_text(encoding="utf-8")

    assert "reduced-scope" in methodology_text.lower()
    assert "$0" in methodology_text
    assert "2026-11-10 21:16 Europe/London" in methodology_text
    assert "NOT the official S16.2 leaderboard" in methodology_text
    assert "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash" in methodology_text
    assert "compat/hy3" in methodology_text
    assert "silent-core" in methodology_text
    assert "core-v1-l71-reduced" in methodology_text
    assert "core-v1-l71-hy3" in methodology_text
    assert "892" in methodology_text
    assert "168" in methodology_text
    assert "5.0" in methodology_text
    assert "WorkBuddy" in methodology_text
    assert "127.0.0.1:5390" in methodology_text

    # Budget report pointer check
    assert BUDGET_REPORT_FILE.is_file()
    budget_text = BUDGET_REPORT_FILE.read_text(encoding="utf-8")
    assert "leaderboard-l71-reduced.md" in budget_text
    assert "L71" in budget_text
    assert "2026-11-10 21:16 Europe/London" in budget_text
