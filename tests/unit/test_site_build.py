"""Leaderboard static site (L72, S16.3)."""

from __future__ import annotations

import importlib.util
import json
import random
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "bench" / "leaderboard" / "models.yaml"
HTTP_URL = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)""")


def _load() -> Any:
    path = REPO / "site" / "build.py"
    spec = importlib.util.spec_from_file_location("skeptic_site_build", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass can see the module while the class body runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def site_build() -> Any:
    return _load()


@pytest.fixture(scope="module")
def built(site_build: Any, tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("leaderboard")
    return site_build.build_site(
        out_dir=out,
        models_path=MODELS,
        generated_at="2026-11-10T00:00:00Z",
    )


def _summary(dest: Path) -> dict[str, Any]:
    return json.loads((dest / "data" / "summary.json").read_text(encoding="utf-8"))


def test_rank_board_merges_adjacent_overlapping_intervals(site_build: Any) -> None:
    """Adjacent SKS intervals share T-<place>. A gap starts a new place number."""
    tied = site_build.rank_board(
        [
            {"name": "b", "metrics": {"SKS": {"estimate": 80.0, "low": 74.0, "high": 85.0}}},
            {"name": "a", "metrics": {"SKS": {"estimate": 82.0, "low": 76.0, "high": 87.0}}},
            {"name": "c", "metrics": {"SKS": {"estimate": 60.0, "low": 55.0, "high": 65.0}}},
            {"name": "d", "metrics": {"SKS": {"estimate": 58.0, "low": 53.0, "high": 63.0}}},
        ]
    )
    assert [row["name"] for row in tied] == ["a", "b", "c", "d"]
    assert [row["rank_group"] for row in tied] == ["T-1", "T-1", "T-3", "T-3"]

    chain = site_build.rank_board(
        [
            {"name": "top", "metrics": {"SKS": {"estimate": 90.0, "low": 80.0, "high": 90.0}}},
            {"name": "mid", "metrics": {"SKS": {"estimate": 70.0, "low": 70.0, "high": 85.0}}},
            {"name": "low", "metrics": {"SKS": {"estimate": 50.0, "low": 50.0, "high": 72.0}}},
        ]
    )
    assert [row["rank_group"] for row in chain] == ["T-1", "T-1", "T-1"]

    separate = site_build.rank_board(
        [
            {"name": "first", "metrics": {"SKS": {"estimate": 90.0, "low": 88.0, "high": 92.0}}},
            {"name": "second", "metrics": {"SKS": {"estimate": 70.0, "low": 68.0, "high": 72.0}}},
        ]
    )
    assert [row["rank_group"] for row in separate] == ["1", "2"]


def test_placeholder_pages_rank_groups_and_guard_deltas(site_build: Any, built: Path) -> None:
    summary = _summary(built)
    configs = summary["configs"]
    assert summary["placeholder"] is True
    assert summary["schema"] == "skeptic.leaderboard/v1"
    assert [row["rank_group"] for row in configs] == [
        "T-1",
        "T-1",
        "T-3",
        "T-3",
        "T-3",
        "6",
        "T-7",
        "T-7",
    ]
    scores = [round(row["metrics"]["SKS"]["estimate"], 2) for row in configs]
    assert scores == [100.0, 100.0, 75.0, 75.0, 75.0, 70.0, 20.0, 20.0]
    bare = [{"id": row["id"], "metrics": row["metrics"]} for row in configs]
    again = {row["id"]: row["rank_group"] for row in site_build.rank_board(bare)}
    assert again == {row["id"]: row["rank_group"] for row in configs}

    index = (built / "index.html").read_text(encoding="utf-8")
    assert "<td>T-1</td>" in index
    assert "<td>T-3</td>" in index
    assert "<td>T-7</td>" in index
    assert "<td>6</td>" in index
    assert "These numbers are a smoke placeholder" in index

    deltas = {(row["model"], row["adapter"]): row for row in summary["guard_deltas"]}
    assert len(deltas) == 3
    terra = deltas[("compat/gpt-5.6-terra", "reference")]
    assert terra["delta_sks"]["estimate"] == pytest.approx(25.0)
    assert terra["delta_scr"]["estimate"] == pytest.approx(-1.0)
    assert terra["delta_fsr"]["estimate"] == pytest.approx(0.0)
    assert terra["delta_sks"]["low"] <= terra["delta_sks"]["estimate"] <= terra["delta_sks"]["high"]
    assert ("compat/hy3", "reference") not in deltas
    guards = (built / "guards.html").read_text(encoding="utf-8")
    assert "+25.00" in guards
    assert "-100.0 pp" in guards


def test_s16_pages_scroll_and_no_cdn(built: Path) -> None:
    assert (built / "index.html").is_file()
    assert (built / "guards.html").is_file()
    assert (built / "methodology.html").is_file()
    assert (built / "data" / "results.csv").is_file()
    assert (built / "data" / "summary.json").is_file()
    assert len(list((built / "fault").glob("*.html"))) == 20
    assert len(list((built / "config").glob("*.html"))) == 8
    zips = list((built / "data").glob("cassettes*.zip"))
    assert len(zips) == 1
    assert zips[0].stat().st_size <= 100 * 1024 * 1024
    with zipfile.ZipFile(zips[0]) as archive:
        names = archive.namelist()
        assert "PLACEHOLDER.txt" in names
        assert any(name.startswith("cassettes/") for name in names)

    pages = list(built.rglob("*.html"))
    assert pages
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert "\r" not in text
        assert 'name="viewport" content="width=device-width, initial-scale=1"' in text
        assert "overflow-x: auto" in text
        assert "overflow-x: hidden" in text
        assert "table-scroll" in text
        assert "<table" in text
        for url in HTTP_URL.findall(text):
            assert not url.startswith(("http://", "https://", "//")), url
        lowered = text.lower()
        for host in ("cdn.jsdelivr", "unpkg.com", "cdnjs.cloudflare", "fonts.googleapis"):
            assert host not in lowered

    method = (built / "methodology.html").read_text(encoding="utf-8")
    assert "0.30*RR" in method
    assert "0.15*(1 - SCR)" in method
    assert "leaderboard-request" in method
    assert "two weeks" in method
    assert "once a quarter" in method
    assert "GPT-4o mini" in method
    assert "seeds 1, 2, 3" in method

    csv_text = (built / "data" / "results.csv").read_text(encoding="utf-8")
    assert csv_text.count("\n") == 65
    assert csv_text.startswith("episode_id,")

    config = next((built / "config").glob("*.html"))
    config_text = config.read_text(encoding="utf-8")
    assert "Fault by outcome" in config_text
    assert "cassettes.zip" in config_text
    fault = (built / "fault" / "L01.html").read_text(encoding="utf-8")
    assert "SUCCESS" in fault
    assert (built / "fault" / "S01.html").is_file()


def test_results_jsonl_and_missing_cassettes(site_build: Any, tmp_path: Path) -> None:
    episode = dict(site_build.placeholder_episodes()[0])
    episode["cassette"] = "cassettes/missing.jsonl"
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps(episode) + "\n", encoding="utf-8", newline="\n")
    dest = site_build.build_site(
        out_dir=tmp_path / "out",
        models_path=MODELS,
        results_path=results,
        generated_at="2026-11-10T00:00:00Z",
        bootstrap_b=0,
    )
    summary = _summary(dest)
    assert summary["placeholder"] is False
    assert len(summary["configs"]) == 1
    index = (dest / "index.html").read_text(encoding="utf-8")
    assert "These numbers are a smoke placeholder" not in index
    zips = list((dest / "data").glob("cassettes*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as archive:
        assert "MISSING.txt" in archive.namelist()
        assert b"cassettes/missing.jsonl" in archive.read("MISSING.txt")

    cassette_dir = tmp_path / "tapes"
    cassette_dir.mkdir()
    (cassette_dir / "cassettes").mkdir()
    payload = b'{"hello":"tape"}\n'
    (cassette_dir / "cassettes" / "missing.jsonl").write_bytes(payload)
    dest_found = site_build.build_site(
        out_dir=tmp_path / "out-found",
        models_path=MODELS,
        results_path=results,
        cassettes_dir=cassette_dir,
        generated_at="2026-11-10T00:00:00Z",
        bootstrap_b=0,
    )
    found_zip = next((dest_found / "data").glob("cassettes*.zip"))
    with zipfile.ZipFile(found_zip) as archive:
        assert archive.read("cassettes/missing.jsonl") == payload
        assert "MISSING.txt" not in archive.namelist()


def test_unsafe_cassette_path_is_rejected(site_build: Any, tmp_path: Path) -> None:
    episode = dict(site_build.placeholder_episodes()[0])
    episode["cassette"] = "../secret.jsonl"
    with pytest.raises(ValueError, match="unsafe"):
        site_build.build_site(
            out_dir=tmp_path / "out",
            models_path=MODELS,
            episodes=[episode],
            generated_at="2026-11-10T00:00:00Z",
            bootstrap_b=0,
        )


def test_pack_archives_splits_volumes(site_build: Any, tmp_path: Path) -> None:
    rng = random.Random(0)
    entries = [(f"cassettes/part-{index}.bin", rng.randbytes(200)) for index in range(5)]
    pack = site_build.pack_archives(entries, tmp_path, max_bytes=350)
    assert len(pack.files) >= 2
    for name in pack.files:
        assert (tmp_path / name).stat().st_size <= 350
    single = site_build.pack_archives([("note.txt", b"hi\n")], tmp_path / "one", max_bytes=100_000)
    assert single.files == ("cassettes.zip",)


def test_bad_results_line_names_the_line(site_build: Any, tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    path.write_text("{}\nnot-json\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match=r"results\.jsonl:2"):
        site_build.load_results(path)
