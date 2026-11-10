"""Checks for the R82 launch content pack."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
LAUNCH = ROOT / "docs" / "launch"

REQUIRED = (
    "hn-show.md",
    "x-thread.md",
    "reddit-localllama.md",
    "blog-en.md",
    "zhihu.md",
    "juejin.md",
    "wechat.md",
    "demo.tape",
    "demo.gif",
)

HYPE = (
    "revolutionary",
    "game-changing",
    "game changer",
    "unprecedented",
    "shocking",
    "must-read",
    "颠覆",
    "震惊",
    "神器",
    "必备",
    "史上最",
    "炸裂",
    "吊打",
    "碾压",
)

RUN_ID = re.compile(r"20\d{6}-\d{6}-[0-9a-f]{6}")
PCT = re.compile(r"\d+\.\d+%")


def test_launch_files_exist() -> None:
    """Every file named on the R82 card is present."""
    for name in REQUIRED:
        assert (LAUNCH / name).is_file(), name


def test_show_hn_title_length() -> None:
    """The Show HN title stays within the 80-character card limit."""
    text = (LAUNCH / "hn-show.md").read_text(encoding="utf-8")
    titles = [line for line in text.splitlines() if line.startswith("Show HN:")]
    assert len(titles) == 1
    assert len(titles[0]) <= 80


def test_x_thread_has_eight_to_ten_posts() -> None:
    """The thread is 8 to 10 numbered posts, each short enough to paste."""
    lines = [
        line
        for line in (LAUNCH / "x-thread.md").read_text(encoding="utf-8").splitlines()
        if re.match(r"\d+/ ", line)
    ]
    assert 8 <= len(lines) <= 10
    numbers = [int(line.split("/", 1)[0]) for line in lines]
    assert numbers == list(range(1, len(lines) + 1))
    for line in lines:
        assert len(line) <= 280


def test_readme_hero() -> None:
    """The README hero has the gif, the install command, and three cited figures."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/launch/demo.gif" in text
    assert "uv sync" in text
    assert "uv run skeptic --version" in text
    assert "8.54%" in text
    assert "7.29%" in text
    assert "93.19" in text
    assert "20261103-155316-3e96a4" in text
    assert "20261103-162358-6c18bb" in text
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    assert "docs/launch/demo.gif" in chinese
    assert "uv sync" in chinese
    assert "8.54%" in chinese
    assert "20261103-155316-3e96a4" in chinese


def test_decimal_percents_cite_a_run_id() -> None:
    """A measured percentage shares a paragraph with a run id."""
    paths = list(LAUNCH.glob("*.md"))
    paths.extend([ROOT / "README.md", ROOT / "README.zh-CN.md"])
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for para in re.split(r"\n\s*\n", text):
            if PCT.search(para):
                assert RUN_ID.search(para), f"{path.name}: {para[:120]}"


def test_blog_and_wechat_length() -> None:
    """The English post is about 1,500 words and the WeChat post about 2,500 字."""
    blog = (LAUNCH / "blog-en.md").read_text(encoding="utf-8")
    prose = re.sub(r"```.*?```", " ", blog, flags=re.S)
    words = re.findall(r"[A-Za-z0-9']+", prose)
    assert 1400 <= len(words) <= 1650
    wechat = (LAUNCH / "wechat.md").read_text(encoding="utf-8")
    cjk = re.findall(r"[\u4e00-\u9fff]", wechat)
    assert 2300 <= len(cjk) <= 2800


def test_headings_avoid_hype() -> None:
    """Titles stay descriptive."""
    paths = list(LAUNCH.glob("*.md"))
    paths.extend([ROOT / "README.md", ROOT / "README.zh-CN.md"])
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("#"):
                continue
            lowered = line.casefold()
            for word in HYPE:
                assert word.casefold() not in lowered, f"{path.name}: {line}"


def test_tape_sleep_budget() -> None:
    """The VHS script targets the committed gif and stays under 30 seconds of Sleep."""
    text = (LAUNCH / "demo.tape").read_text(encoding="utf-8")
    assert "Output docs/launch/demo.gif" in text
    assert "uv run skeptic --version" in text
    assert "uv run skeptic faults list --class silent" in text
    assert "guards-ab-free.yaml --count" in text
    total_s = 0.0
    for match in re.finditer(r"^Sleep (\d+)(ms|s)$", text, re.M):
        amount = int(match.group(1))
        total_s += amount / 1000 if match.group(2) == "ms" else amount
    assert total_s < 30


def test_gif_duration_under_30_seconds() -> None:
    """The committed GIF plays for more than a flash and under 30 seconds."""
    data = (LAUNCH / "demo.gif").read_bytes()
    assert data[:6] in {b"GIF87a", b"GIF89a"}
    total_cs = 0
    frames = 0
    index = 0
    marker = b"\x21\xf9\x04"
    while True:
        found = data.find(marker, index)
        if found < 0 or found + 6 >= len(data):
            break
        delay = data[found + 4] + (data[found + 5] << 8)
        total_cs += delay
        frames += 1
        index = found + 6
    assert frames >= 5
    assert 3 <= total_cs / 100 < 30


def test_sks_ci_bounds_do_not_use_percent() -> None:
    """SKS is a 0-100 score; confidence interval bounds must not carry % signs."""
    paths = list(LAUNCH.glob("*.md"))
    paths.extend([ROOT / "README.md", ROOT / "README.zh-CN.md"])
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "SKS" in line:
                for match in re.finditer(
                    r"(?:CI|区间)\s*([0-9\.]+)\s*(?:to|到|\u2013|-)\s*([0-9\.]+)(%?)",
                    line,
                ):
                    msg = f"{path.name}: SKS CI bound has % in '{line.strip()}'"
                    assert not match.group(3), msg
