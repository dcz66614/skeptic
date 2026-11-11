"""Unit tests for the L71ds WorkBuddy paid flash-sg reduced matrix."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.runner.llm import get_model_pricing
from skeptic_agent.runner.matrix import (
    count_matrix_episodes,
    expand_matrix_configs,
    load_matrix,
    load_models,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = REPO_ROOT / "bench" / "leaderboard" / "models.yaml"
FLASH_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-flash.yaml"
FREE_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-free.yaml"
HY3_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1-reduced-free-hy3.yaml"
OFFICIAL_MATRIX_FILE = REPO_ROOT / "bench" / "matrix" / "leaderboard-v1.yaml"
MATRIX_SCHEMA = REPO_ROOT / "schemas" / "matrix.schema.json"
DOCS_FILE = REPO_ROOT / "docs" / "reports" / "leaderboard-l71-reduced.md"
FLASH_ID = "compat/deepseek-v4.1-flash-sg"


def test_official_and_free_matrices_untouched_by_flash_variant() -> None:
    official = OFFICIAL_MATRIX_FILE.read_text(encoding="utf-8")
    assert "1300" in official
    assert FLASH_ID not in official
    free = yaml.safe_load(FREE_MATRIX_FILE.read_text(encoding="utf-8"))
    assert free["id"] == "leaderboard-v1-reduced-free"
    models: list[str] = []
    for cfg in free["configs"]:
        models.extend(cfg.get("models") or [])
    assert models == [
        "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash",
        "compat/our-free-model/deepseek-ai/deepseek-v4.1-flash",
    ]
    hy3 = yaml.safe_load(HY3_MATRIX_FILE.read_text(encoding="utf-8"))
    assert hy3["id"] == "leaderboard-v1-reduced-free-hy3"


def test_flash_matrix_validation_shape_and_count() -> None:
    assert FLASH_MATRIX_FILE.is_file()
    schema = json.loads(MATRIX_SCHEMA.read_text(encoding="utf-8"))
    data = yaml.safe_load(FLASH_MATRIX_FILE.read_text(encoding="utf-8"))
    jsonschema.validate(instance=data, schema=schema)
    matrix = load_matrix(FLASH_MATRIX_FILE)
    assert matrix.id == "leaderboard-v1-reduced-flash"
    assert matrix.suite == "core-v1-l71-reduced"
    assert list(matrix.profiles) == ["silent-core"] or matrix.profiles == ["silent-core"]
    assert list(matrix.seeds) == [1] or matrix.seeds == [1]
    expanded = expand_matrix_configs(matrix)
    assert len(expanded) == 2
    assert expanded[0].guards == "none"
    assert expanded[0].model == FLASH_ID
    assert expanded[0].agent == f"reference:{FLASH_ID}"
    assert expanded[1].guards == "recommended"
    assert expanded[1].model == FLASH_ID
    assert count_matrix_episodes(matrix, models_path=MODELS_FILE) == 892
    runner = CliRunner()
    res = runner.invoke(app, ["bench", "run", "--matrix", str(FLASH_MATRIX_FILE), "--count"])
    assert res.exit_code == 0
    assert "Total episodes: 892" in res.stdout
    text = FLASH_MATRIX_FILE.read_text(encoding="utf-8")
    assert "our-free-model" not in text
    assert "opencode/" not in text
    assert "openrouter/" not in text
    assert text.count("compat/deepseek-v4.1-flash-sg") == 2
    assert "compat/deepseek-v4.1-flash\n" not in text


def test_flash_model_registration_not_usd_credits() -> None:
    models = {m["id"]: m for m in load_models(MODELS_FILE)}
    assert FLASH_ID in models
    m = models[FLASH_ID]
    assert m["tier"] == "experiment"
    assert m["supports_tools"] is True
    notes = m["notes"]
    assert "WorkBuddy" in notes
    assert "not an OpenRouter slug" in notes or "not OpenRouter" in notes
    assert "127.0.0.1:5390" in notes
    assert "14.29" in notes
    assert "57.1" in notes
    assert float(m["price_in_per_mtok"]) == 0.0
    assert float(m["price_out_per_mtok"]) == 0.0
    assert get_model_pricing(FLASH_ID, models_yaml=MODELS_FILE) == (0.0, 0.0)


def test_docs_state_paid_flash_is_separate_reduced_scope() -> None:
    text = DOCS_FILE.read_text(encoding="utf-8")
    assert "leaderboard-v1-reduced-flash.yaml" in text
    assert FLASH_ID in text
    assert "S16.2" in text
    assert "free DSH" in text or "l71_free" in text
