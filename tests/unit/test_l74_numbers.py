"""Unit tests for L74 reduced-scope flash leaderboard numbers and report.

Validates:
- Deterministic extraction in paper/numbers.json matching generate_numbers()
- Exact episode counts (446 per config, 892 total) and zero errors
- Provenance model id compat/deepseek-v4.1-flash-sg and matrix metadata
- Markdown report honest disclaimers ("not S16.2", no "S16.2 leaderboard result")
- Token accounting deduplication and credit upper bound estimate
- All numeric figures in markdown appear in paper/numbers.json
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
NUMBERS_FILE = REPO_ROOT / "paper" / "numbers.json"
REPORT_FILE = REPO_ROOT / "docs" / "reports" / "leaderboard-l74-reduced-flash.md"
SCRIPT_FILE = REPO_ROOT / "paper" / "make_numbers.py"
MODEL_ID = "compat/deepseek-v4.1-flash-sg"


def _load_generate_numbers() -> Any:
    spec = importlib.util.spec_from_file_location("make_numbers", SCRIPT_FILE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.generate_numbers


def test_numbers_json_matches_regenerated() -> None:
    """paper/numbers.json must match live regeneration from paper/data exactly."""
    assert NUMBERS_FILE.is_file(), f"numbers.json missing at {NUMBERS_FILE}"
    raw_bytes = NUMBERS_FILE.read_bytes()
    assert b"\r" not in raw_bytes, "numbers.json must use LF line endings"

    file_data = json.loads(raw_bytes.decode("utf-8"))
    generate_numbers_fn = _load_generate_numbers()
    regenerated_data = generate_numbers_fn(REPO_ROOT)
    assert file_data == regenerated_data


def test_episodes_and_error_counts() -> None:
    """Assert 446 episodes per config, 892 total, and 0 errors."""
    data = json.loads(NUMBERS_FILE.read_text(encoding="utf-8"))

    none_cfg = data["configs"]["none"]
    rec_cfg = data["configs"]["recommended"]
    totals = data["totals"]

    assert none_cfg["episodes"] == 446
    assert rec_cfg["episodes"] == 446
    assert totals["episodes"] == 892

    assert none_cfg["errors"] == 0
    assert rec_cfg["errors"] == 0
    assert totals["errors"] == 0


def test_provenance_metadata() -> None:
    """Assert provenance model ID, matrix ID, suite, seed, and disclaimer note."""
    data = json.loads(NUMBERS_FILE.read_text(encoding="utf-8"))
    prov = data["provenance"]

    assert prov["model_id"] == MODEL_ID
    assert prov["matrix_id"] == "leaderboard-v1-reduced-flash"
    assert prov["suite"] == "core-v1-l71-reduced"
    assert prov["seed"] == 1
    assert prov["profile"] == "silent-core"
    assert prov["git_sha"] == "8624def"
    assert "reduced scope; not S16.2" in prov["note"]
    assert prov["scenarios"] == 56


def test_report_content_honesty_and_negative_assertions() -> None:
    """Assert report contains 'not S16.2' and does NOT contain 'S16.2 leaderboard result'."""
    assert REPORT_FILE.is_file(), f"Report file missing at {REPORT_FILE}"
    content = REPORT_FILE.read_text(encoding="utf-8")

    assert "not S16.2" in content
    assert "S16.2 leaderboard result" not in content
    assert "not the free DSH run" in content
    assert "full LaTeX tech report L74 deferred" in content


def test_all_numbers_in_md_appear_in_numbers_json() -> None:
    """Every number in the markdown report must appear in paper/numbers.json."""
    md_text = REPORT_FILE.read_text(encoding="utf-8")
    json_text = NUMBERS_FILE.read_text(encoding="utf-8")

    tokens = re.findall(r"[-+]?\b\d+(?:\.\d+)?%?\b", md_text)
    assert len(tokens) > 0

    missing: list[str] = []
    for tok in set(tokens):
        clean_tok = tok.lstrip("+-").rstrip("%")
        if tok not in json_text and clean_tok not in json_text:
            missing.append(tok)

    assert not missing, f"Numbers in markdown missing from numbers.json: {missing}"


def test_token_totals_and_credit_estimate() -> None:
    """Verify deduplicated token accounting and credit estimate."""
    data = json.loads(NUMBERS_FILE.read_text(encoding="utf-8"))
    tokens = data["tokens"]

    assert len(tokens["by_run"]) == 2
    none_run = tokens["by_run"]["20261111-202444-07a2ff"]
    rec_run = tokens["by_run"]["20261111-204118-1d7e2e"]

    assert none_run["tokens_in"] == 1729518
    assert none_run["tokens_out"] == 161712
    assert none_run["tokens_total"] == 1891230
    assert none_run["cost_usd"] == 0.0

    assert rec_run["tokens_in"] == 1754548
    assert rec_run["tokens_out"] == 159631
    assert rec_run["tokens_total"] == 1914179
    assert rec_run["cost_usd"] == 0.0

    tot = tokens["total"]
    assert tot["tokens_in"] == 3484066
    assert tot["tokens_out"] == 321343
    assert tot["tokens_total"] == 3805409
    assert tot["cost_usd"] == 0.0

    assert tot["estimated_credits_from_tokens"] < 150.0
