"""Unit tests for matrix definitions, runner utilities, compare, gate, and CLI (E48, S2, S16.2)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from skeptic_agent.cli import app
from skeptic_agent.runner.matrix import (
    build_config_doc,
    build_summary_doc,
    compare_runs,
    compute_worst_scenarios,
    count_matrix_episodes,
    expand_matrix_configs,
    gate_check,
    load_matrix,
    normalize_guards,
    validate_summary_doc,
)

runner = CliRunner()


@pytest.fixture
def sample_matrix_dict() -> dict[str, Any]:
    return {
        "schema": "skeptic.matrix/v1",
        "id": "test-matrix-v1",
        "suite": "smoke",
        "profiles": ["silent-core"],
        "seeds": [1, 2],
        "max_cost_usd": 10.0,
        "configs": [
            {
                "agent": "reference:${model}",
                "prompt_variant": "plain",
                "guards": "none",
                "models": "leaderboard",
            },
            {
                "agent": "reference:${model}",
                "prompt_variant": "evidence_contract",
                "guards": ["schema_guard", "loop_breaker"],
                "models": ["fake/oracle_follower"],
            },
        ],
    }


def test_load_matrix_success(tmp_path: Path, sample_matrix_dict: dict[str, Any]) -> None:
    yaml_path = tmp_path / "matrix.yaml"
    yaml_path.write_text(yaml.safe_dump(sample_matrix_dict), encoding="utf-8")

    matrix = load_matrix(yaml_path)
    assert matrix.id == "test-matrix-v1"
    assert matrix.suite == "smoke"
    assert matrix.profiles == ["silent-core"]
    assert matrix.seeds == [1, 2]
    assert matrix.max_cost_usd == 10.0
    assert len(matrix.configs) == 2
    assert matrix.configs[0].agent == "reference:${model}"
    assert matrix.configs[0].models == "leaderboard"
    assert matrix.configs[1].models == ["fake/oracle_follower"]

    # Test to_dict
    m_dict = matrix.to_dict()
    assert m_dict["id"] == "test-matrix-v1"
    assert len(m_dict["configs"]) == 2


def test_load_matrix_invalid_schema(tmp_path: Path) -> None:
    bad_dict = {
        "schema": "skeptic.matrix/v1",
        "id": "bad-matrix",
        # missing required 'suite', 'profiles', etc.
    }
    yaml_path = tmp_path / "bad.yaml"
    yaml_path.write_text(yaml.safe_dump(bad_dict), encoding="utf-8")

    import jsonschema

    with pytest.raises(jsonschema.ValidationError):
        load_matrix(yaml_path)


def test_expand_matrix_configs(sample_matrix_dict: dict[str, Any]) -> None:
    matrix = load_matrix(sample_matrix_dict)
    expanded = expand_matrix_configs(matrix)
    assert len(expanded) >= 2

    # Second config expands to fake/oracle_follower
    cfg2 = next(c for c in expanded if c.model == "fake/oracle_follower")
    assert cfg2.agent == "reference:fake/oracle_follower"
    assert cfg2.prompt_variant == "evidence_contract"
    assert cfg2.guards == ["schema_guard", "loop_breaker"]


def test_normalize_guards() -> None:
    assert normalize_guards("none") == []
    assert len(normalize_guards("all")) == 8
    assert "schema_guard" in normalize_guards("recommended")
    assert normalize_guards("schema_guard,loop_breaker") == ["schema_guard", "loop_breaker"]
    assert normalize_guards(["retry_guard"]) == ["retry_guard"]


def test_build_config_doc() -> None:
    doc = build_config_doc(
        project="test-proj",
        profile="silent-core",
        guards="none",
        budget_usd=12.5,
    )
    assert doc["schema"] == "skeptic.config/v1"
    assert doc["project"] == "test-proj"
    assert doc["profile"] == "silent-core"
    assert doc["guards"] == "none"
    assert doc["budget"]["max_cost_usd_per_run"] == 12.5


def test_compute_worst_scenarios() -> None:
    episodes = [
        {
            "scenario_id": "weather.forecast.paris-max.001",
            "fault": {"id": "S04"},
            "flags": {"triggered": True},
            "outcome": "SILENT_CORRUPTION",
            "cassette": "cassettes/c1.jsonl",
        },
        {
            "scenario_id": "weather.forecast.paris-max.001",
            "fault": {"id": "S04"},
            "flags": {"triggered": True},
            "outcome": "SUCCESS",
            "cassette": "cassettes/c1.jsonl",
        },
        {
            "scenario_id": "fx.rate.usd-eur.001",
            "fault": {"id": "S04"},
            "flags": {"triggered": True},
            "outcome": "SUCCESS",
            "cassette": "cassettes/c2.jsonl",
        },
    ]

    worst = compute_worst_scenarios(episodes)
    assert len(worst) == 2
    # Paris SafeRate is 1/2 = 0.5, fx SafeRate is 1/1 = 1.0
    assert worst[0]["scenario_id"] == "weather.forecast.paris-max.001"
    assert worst[0]["SafeRate"] == 0.5
    assert worst[0]["cassettes"] == ["cassettes/c1.jsonl"]
    assert worst[1]["scenario_id"] == "fx.rate.usd-eur.001"
    assert worst[1]["SafeRate"] == 1.0


def test_build_and_validate_summary_doc(tmp_path: Path) -> None:
    episodes = [
        {
            "episode_id": "20261102-120000-abcdef:weather.forecast.paris-max.001:clean:1",
            "scenario_id": "weather.forecast.paris-max.001",
            "sandbox": "sb_weather",
            "seed": 1,
            "outcome": "SUCCESS",
            "fault": None,
            "flags": {"triggered": False, "detected": False, "loop": False},
            "agent": {
                "adapter": "reference",
                "model": "fake/oracle_follower",
                "prompt_variant": "plain",
                "guards": [],
            },
            "usage": {"tokens_in": 100, "tokens_out": 50, "cost_usd": 0.001},
            "cassette": "cassettes/ep1.jsonl",
        },
        {
            "episode_id": "20261102-120000-abcdef:weather.forecast.paris-max.001:S04:1",
            "scenario_id": "weather.forecast.paris-max.001",
            "sandbox": "sb_weather",
            "seed": 1,
            "outcome": "SILENT_CORRUPTION",
            "fault": {"id": "S04", "class": "silent", "persistence": "permanent"},
            "flags": {"triggered": True, "detected": False, "loop": False},
            "agent": {
                "adapter": "reference",
                "model": "fake/oracle_follower",
                "prompt_variant": "plain",
                "guards": [],
            },
            "usage": {"tokens_in": 120, "tokens_out": 60, "cost_usd": 0.0012},
            "cassette": "cassettes/ep2.jsonl",
        },
    ]

    cfg = build_config_doc()
    summary = build_summary_doc(
        run_id="20261102-120000-abcdef",
        episodes=episodes,
        command="skeptic run --suite smoke",
        config=cfg,
    )

    # Validates without throwing ValidationError
    validate_summary_doc(summary)

    assert summary["run_id"] == "20261102-120000-abcdef"
    assert summary["schema"] == "skeptic.report/v1"
    assert len(summary["agents"]) == 1
    assert summary["by_fault"]["S04"]["SILENT_CORRUPTION"] == 1
    assert summary["by_sandbox"]["sb_weather"]["SUCCESS"] == 1
    assert summary["by_sandbox"]["sb_weather"]["SILENT_CORRUPTION"] == 1
    assert len(summary["worst_scenarios"]) == 1


def test_gate_check_pass_and_fail(tmp_path: Path) -> None:
    # Setup summary with SKS=75.0, FSR=0.05, ICR=0.00
    summary_doc = {
        "schema": "skeptic.report/v1",
        "run_id": "20261102-120000-abcdef",
        "config": {
            "gate": {"min_sks": 70.0, "max_fsr": 0.10, "max_icr": 0.00},
        },
        "agents": [
            {
                "adapter": "reference",
                "model": "fake/oracle_follower",
                "prompt_variant": "plain",
                "guards": [],
                "metrics": {
                    "SKS": {"estimate": 75.0},
                    "FSR": {"estimate": 0.05},
                    "ICR": {"estimate": 0.00},
                },
            }
        ],
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary_doc), encoding="utf-8")

    # Pass case
    passed, msg = gate_check(tmp_path)
    assert passed is True
    assert "PASSED" in msg

    # Fail SKS threshold
    passed_sks, msg_sks = gate_check(tmp_path, min_sks=80.0)
    assert passed_sks is False
    assert "SKS 75.00 < min_sks 80.00" in msg_sks

    # Fail FSR threshold
    passed_fsr, msg_fsr = gate_check(tmp_path, max_fsr=0.02)
    assert passed_fsr is False
    assert "FSR 0.0500 > max_fsr 0.0200" in msg_fsr

    # Fail ICR threshold
    passed_icr, msg_icr = gate_check(tmp_path, max_icr=-0.01)
    assert passed_icr is False
    assert "ICR" in msg_icr


def test_compare_runs_md_and_json(tmp_path: Path) -> None:
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir()
    dir_b.mkdir()

    ep_a = {
        "episode_id": "20261102-120000-aaaaaa:weather.forecast.paris-max.001:clean:1",
        "scenario_id": "weather.forecast.paris-max.001",
        "sandbox": "sb_weather",
        "seed": 1,
        "outcome": "SUCCESS",
        "fault": None,
        "flags": {"triggered": False},
        "usage": {"cost_usd": 0.001, "latency_s": 2.0},
    }
    ep_b = {
        "episode_id": "20261102-130000-bbbbbb:weather.forecast.paris-max.001:clean:1",
        "scenario_id": "weather.forecast.paris-max.001",
        "sandbox": "sb_weather",
        "seed": 1,
        "outcome": "SUCCESS",
        "fault": None,
        "flags": {"triggered": False},
        "usage": {"cost_usd": 0.0015, "latency_s": 1.5},
    }

    (dir_a / "results.jsonl").write_text(json.dumps(ep_a) + "\n", encoding="utf-8")
    (dir_b / "results.jsonl").write_text(json.dumps(ep_b) + "\n", encoding="utf-8")

    # Markdown format
    md_out = compare_runs(dir_a, dir_b, format="md")
    assert isinstance(md_out, str)
    assert "# Skeptic Run Comparison" in md_out
    assert "| **SKS** |" in md_out
    assert "| Cost |" in md_out

    # JSON format
    json_out = compare_runs(dir_a, dir_b, format="json")
    assert isinstance(json_out, dict)
    assert "metrics" in json_out
    assert "SKS" in json_out["metrics"]


def test_cli_gate_command(tmp_path: Path) -> None:
    summary_doc = {
        "schema": "skeptic.report/v1",
        "run_id": "20261102-120000-abcdef",
        "config": {
            "gate": {"min_sks": 70.0, "max_fsr": 0.10, "max_icr": 0.00},
        },
        "agents": [
            {
                "metrics": {
                    "SKS": {"estimate": 80.0},
                    "FSR": {"estimate": 0.02},
                    "ICR": {"estimate": 0.00},
                },
            }
        ],
    }
    (tmp_path / "summary.json").write_text(json.dumps(summary_doc), encoding="utf-8")

    # Passing gate check
    res_pass = runner.invoke(app, ["gate", str(tmp_path), "--min-sks", "75.0"])
    assert res_pass.exit_code == 0
    assert "Gate check PASSED" in res_pass.stdout

    # Failing gate check: exits with 10 (S2)
    res_fail = runner.invoke(app, ["gate", str(tmp_path), "--min-sks", "85.0"])
    assert res_fail.exit_code == 10


def test_cli_compare_command(tmp_path: Path) -> None:
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir()
    dir_b.mkdir()

    doc_a = {
        "agents": [
            {
                "metrics": {
                    "SKS": {"estimate": 70.0, "low": 60.0, "high": 80.0},
                    "SafeRate": {"estimate": 0.5, "low": 0.4, "high": 0.6},
                }
            }
        ]
    }
    doc_b = {
        "agents": [
            {
                "metrics": {
                    "SKS": {"estimate": 75.0, "low": 65.0, "high": 85.0},
                    "SafeRate": {"estimate": 0.6, "low": 0.5, "high": 0.7},
                }
            }
        ]
    }
    (dir_a / "summary.json").write_text(json.dumps(doc_a), encoding="utf-8")
    (dir_b / "summary.json").write_text(json.dumps(doc_b), encoding="utf-8")

    res = runner.invoke(app, ["compare", str(dir_a), str(dir_b), "--format", "json"])
    assert res.exit_code == 0
    parsed = json.loads(res.stdout)
    assert parsed["metrics"]["SKS"]["diff"] == 5.0


def test_guards_ab_matrix_file_and_episode_count() -> None:
    """guards-ab.yaml conforms to schema, expands configs, and counts episodes (G53a)."""
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "bench" / "matrix" / "guards-ab.yaml"
    assert matrix_path.is_file(), f"Missing matrix file at {matrix_path}"

    matrix = load_matrix(matrix_path)
    assert matrix.id == "guards-ab"
    assert matrix.suite == "guards-ab"
    assert matrix.profiles == ["silent-core", "loud-core", "adversarial-core"]
    assert matrix.seeds == [1]
    assert matrix.max_cost_usd <= 60.0
    assert len(matrix.configs) == 10

    # Expand matrix
    expanded = expand_matrix_configs(matrix)
    assert len(expanded) == 20
    models_used = {c.model for c in expanded}
    assert models_used == {"compat/deepseek-v4-pro", "compat/gpt-5.6-terra"}

    # Total episode count
    total_eps = count_matrix_episodes(matrix)
    print(f"Total episode count for guards-ab matrix: {total_eps}")
    assert total_eps == 19220


def test_guards_ab_suite_sampling() -> None:
    """bench/suites/guards-ab.yaml contains 60 scenarios sampled with seed 0 (G53a)."""
    from skeptic_agent.scenario.suites import load_suite

    suite_ab = load_suite("guards-ab")
    assert len(suite_ab.scenarios) == 60

    core_v1 = load_suite("core-v1")
    rng = random.Random(0)
    expected_sample = rng.sample(core_v1.scenarios, 60)
    assert suite_ab.scenarios == expected_sample


def test_cli_bench_run_dry_run_and_count() -> None:
    """skeptic bench run supports --dry-run and --count for matrix files (G53a)."""
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "bench" / "matrix" / "guards-ab.yaml"

    res_dry = runner.invoke(app, ["bench", "run", "--matrix", str(matrix_path), "--dry-run"])
    assert res_dry.exit_code == 0
    assert "guards-ab" in res_dry.stdout
    assert "20 expanded configs" in res_dry.stdout
    assert "19220" in res_dry.stdout

    res_count = runner.invoke(app, ["bench", "run", "--matrix", str(matrix_path), "--count"])
    assert res_count.exit_code == 0
    assert "Total episodes: 19220" in res_count.stdout


def test_guards_ab_free_matrix_file_and_episode_count() -> None:
    """guards-ab-free.yaml conforms to schema, expands configs, counts episodes (G53wrap)."""
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "bench" / "matrix" / "guards-ab-free.yaml"
    assert matrix_path.is_file(), f"Missing matrix file at {matrix_path}"

    matrix = load_matrix(matrix_path)
    assert matrix.id == "guards-ab-free"
    assert matrix.suite == "guards-ab-free"
    assert matrix.profiles == ["silent-core", "loud-core", "adversarial-core"]
    assert matrix.seeds == [1]
    assert len(matrix.configs) == 10

    # Expand matrix
    expanded = expand_matrix_configs(matrix)
    assert len(expanded) == 10
    models_used = {c.model for c in expanded}
    assert models_used == {"compat/hy3"}

    # Total episode count
    total_eps = count_matrix_episodes(matrix)
    assert total_eps == 4820


def test_guards_ab_free_suite() -> None:
    """bench/suites/guards-ab-free.yaml contains first 30 scenarios of guards-ab (G53wrap)."""
    from skeptic_agent.scenario.suites import load_suite

    suite_free = load_suite("guards-ab-free")
    assert len(suite_free.scenarios) == 30

    suite_ab = load_suite("guards-ab")
    assert suite_free.scenarios == suite_ab.scenarios[:30]


def test_cli_bench_run_dry_run_and_count_guards_ab_free() -> None:
    """skeptic bench run supports --dry-run and --count for guards-ab-free matrix (G53wrap)."""
    repo_root = Path(__file__).resolve().parents[2]
    matrix_path = repo_root / "bench" / "matrix" / "guards-ab-free.yaml"

    res_dry = runner.invoke(app, ["bench", "run", "--matrix", str(matrix_path), "--dry-run"])
    assert res_dry.exit_code == 0
    assert "guards-ab-free" in res_dry.stdout
    assert "10 expanded configs" in res_dry.stdout
    assert "4820" in res_dry.stdout

    res_count = runner.invoke(app, ["bench", "run", "--matrix", str(matrix_path), "--count"])
    assert res_count.exit_code == 0
    assert "Total episodes: 4820" in res_count.stdout
