"""Unit tests for L74 LaTeX tech report macros in paper/numbers.tex.

Validates:
- paper/numbers.tex exists, uses LF line endings (no \\r), and is not empty.
- Parses \\newcommand{\\LxxName}{value} macros.
- Matches paper/numbers.json for provenance, episode counts, error counts,
  metric estimates and formatted CIs, outcomes, tokens, and credit bounds.
- Asserts both configs have SKS partial true.
- Does NOT import paper/make_figures.py (no matplotlib dependency).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
NUMBERS_JSON = REPO_ROOT / "paper" / "numbers.json"
NUMBERS_TEX = REPO_ROOT / "paper" / "numbers.tex"


def _parse_latex_macros(path: Path) -> dict[str, str]:
    """Parse \\newcommand{\\Lxx...}{...} definitions from a LaTeX file."""
    pattern = re.compile(r"^\\newcommand\{\\([A-Za-z0-9_]+)\}\{(.*)\}$")
    macros: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("%") or line in (r"\makeatletter", r"\makeatother"):
            continue
        match = pattern.match(line)
        if match:
            macros[match.group(1)] = match.group(2)
    return macros


@pytest.fixture(scope="module")
def numbers_data() -> dict[str, Any]:
    assert NUMBERS_JSON.is_file(), f"numbers.json missing at {NUMBERS_JSON}"
    return json.loads(NUMBERS_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tex_macros() -> dict[str, str]:
    assert NUMBERS_TEX.is_file(), f"numbers.tex missing at {NUMBERS_TEX}"
    return _parse_latex_macros(NUMBERS_TEX)


def test_numbers_tex_file_integrity() -> None:
    """paper/numbers.tex must exist, have LF endings (no \\r), and be non-empty."""
    assert NUMBERS_TEX.is_file(), f"numbers.tex missing at {NUMBERS_TEX}"
    raw_bytes = NUMBERS_TEX.read_bytes()
    assert len(raw_bytes) > 0, "numbers.tex must not be empty"
    assert b"\r" not in raw_bytes, "numbers.tex must use LF line endings (no \\r)"

    macros = _parse_latex_macros(NUMBERS_TEX)
    assert len(macros) >= 200, f"Expected at least 200 macros, got {len(macros)}"


def test_provenance_macros(tex_macros: dict[str, str], numbers_data: dict[str, Any]) -> None:
    """Assert provenance macros match numbers.json."""
    prov = numbers_data["provenance"]

    assert tex_macros["LxxProvGitSha"] == prov["git_sha"]
    assert tex_macros["LxxProvMatrix"] == prov["matrix_id"]
    assert tex_macros["LxxProvModel"] == prov["model_id"]
    assert tex_macros["LxxProvSuite"] == prov["suite"]
    assert tex_macros["LxxProvSeed"] == str(prov["seed"])
    assert "reduced scope; not S16.2" in tex_macros["LxxProvNote"]
    assert tex_macros["LxxProvNote"] == prov["note"]
    assert tex_macros["LxxNoneRunId"] == prov["run_ids"]["none"]
    assert tex_macros["LxxRecRunId"] == prov["run_ids"]["recommended"]


def test_episode_and_error_counts(tex_macros: dict[str, str], numbers_data: dict[str, Any]) -> None:
    """Assert episode counts (446/446/892) and error counts (0/0/0)."""
    assert tex_macros["LxxNoneEpisodes"] == "446"
    assert tex_macros["LxxRecEpisodes"] == "446"
    assert tex_macros["LxxTotalEpisodes"] == "892"

    assert tex_macros["LxxNoneEpisodes"] == str(numbers_data["configs"]["none"]["episodes"])
    assert tex_macros["LxxRecEpisodes"] == str(numbers_data["configs"]["recommended"]["episodes"])
    assert tex_macros["LxxTotalEpisodes"] == str(numbers_data["totals"]["episodes"])

    assert tex_macros["LxxNoneErrors"] == "0"
    assert tex_macros["LxxRecErrors"] == "0"
    assert tex_macros["LxxTotalErrors"] == "0"

    assert tex_macros["LxxNoneErrors"] == str(numbers_data["configs"]["none"]["errors"])
    assert tex_macros["LxxRecErrors"] == str(numbers_data["configs"]["recommended"]["errors"])
    assert tex_macros["LxxTotalErrors"] == str(numbers_data["totals"]["errors"])


def test_metrics_rounded_and_formatted(
    tex_macros: dict[str, str], numbers_data: dict[str, Any]
) -> None:
    """Assert SKS/FSR/SCR/SafeRate/DetectRate estimates and formatted strings."""
    rnd = numbers_data["rounded"]["configs"]
    fmt = numbers_data["formatted"]["configs"]

    for prefix, cfg_name in (("None", "none"), ("Rec", "recommended")):
        for metric in ("SKS", "FSR", "SCR", "SafeRate", "DetectRate"):
            expected_est = str(rnd[cfg_name][metric]["estimate"])
            expected_low = str(rnd[cfg_name][metric]["low"])
            expected_high = str(rnd[cfg_name][metric]["high"])
            expected_fmt = fmt[cfg_name][metric].replace("%", r"\%")

            assert tex_macros[f"Lxx{prefix}{metric}Est"] == expected_est
            assert tex_macros[f"Lxx{prefix}{metric}Low"] == expected_low
            assert tex_macros[f"Lxx{prefix}{metric}High"] == expected_high
            assert tex_macros[f"Lxx{prefix}{metric}Fmt"] == expected_fmt


def test_sks_partial_flags(tex_macros: dict[str, str], numbers_data: dict[str, Any]) -> None:
    """Assert both configs have SKS partial true."""
    assert tex_macros["LxxNoneSKSPartial"] == "true"
    assert tex_macros["LxxRecSKSPartial"] == "true"

    assert numbers_data["configs"]["none"]["metrics"]["SKS"]["partial"] is True
    assert numbers_data["configs"]["recommended"]["metrics"]["SKS"]["partial"] is True


def test_outcome_counts(tex_macros: dict[str, str], numbers_data: dict[str, Any]) -> None:
    """Assert outcome counts match per configuration."""
    for prefix, cfg_name in (("None", "none"), ("Rec", "recommended")):
        outcomes = numbers_data["configs"][cfg_name]["outcomes"]
        for oc in (
            "SUCCESS",
            "HONEST_FAILURE",
            "FALSE_SUCCESS",
            "SILENT_CORRUPTION",
            "INJECTED",
            "NO_ANSWER",
        ):
            oc_tag = oc.replace("_", "")
            macro_key = f"Lxx{prefix}Out{oc_tag}"
            assert tex_macros[macro_key] == str(outcomes.get(oc, 0))


def test_token_totals_and_credit_accounting(
    tex_macros: dict[str, str], numbers_data: dict[str, Any]
) -> None:
    """Assert token counts and upper-bound credit accounting."""
    tokens = numbers_data["tokens"]
    prov = numbers_data["provenance"]
    rnd = numbers_data["rounded"]
    fmt = numbers_data["formatted"]

    none_tok = tokens["by_run"][prov["run_ids"]["none"]]
    rec_tok = tokens["by_run"][prov["run_ids"]["recommended"]]
    tot_tok = tokens["total"]

    assert tex_macros["LxxNoneTokIn"] == str(none_tok["tokens_in"])
    assert tex_macros["LxxNoneTokOut"] == str(none_tok["tokens_out"])
    assert tex_macros["LxxNoneTokTotal"] == str(none_tok["tokens_total"])

    assert tex_macros["LxxRecTokIn"] == str(rec_tok["tokens_in"])
    assert tex_macros["LxxRecTokOut"] == str(rec_tok["tokens_out"])
    assert tex_macros["LxxRecTokTotal"] == str(rec_tok["tokens_total"])

    assert tex_macros["LxxTotalTokIn"] == str(tot_tok["tokens_in"])
    assert tex_macros["LxxTotalTokOut"] == str(tot_tok["tokens_out"])
    assert tex_macros["LxxTotalTokTotal"] == str(tot_tok["tokens_total"])

    # Credits match rounded and formatted numbers
    assert tex_macros["LxxNoneCredits"] == str(rnd["credits"]["none"])
    assert tex_macros["LxxRecCredits"] == str(rnd["credits"]["recommended"])
    assert tex_macros["LxxTotalCredits"] == str(rnd["credits"]["total"])

    assert tex_macros["LxxNoneCreditsFmt"] == fmt["credits"]["none"]
    assert tex_macros["LxxRecCreditsFmt"] == fmt["credits"]["recommended"]
    assert tex_macros["LxxTotalCreditsFmt"] == fmt["credits"]["total"]

    # Credits are explicitly labelled as an upper-bound estimate, not a measured bill
    assert "UPPER BOUND ESTIMATE" in tex_macros["LxxCreditNotes"]
    assert "bills credits that the relay does not report" in tex_macros["LxxCostUsdNote"]
    assert tex_macros["LxxTotalCostUsd"] == "0.0"
    assert tex_macros["LxxNoneCostUsd"] == "0.0"
    assert tex_macros["LxxRecCostUsd"] == "0.0"
