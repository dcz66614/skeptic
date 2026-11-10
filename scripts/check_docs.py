"""Check docs/en and docs/zh, and optionally run the quickstart commands.

The docs workflow runs this with ``--execute``. Every fenced ``bash`` command in
``docs/en/quickstart.md`` and ``docs/zh/quickstart.md`` must match, and any
``skeptic run`` or ``skeptic bench`` command must name a FakeLLM script.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EN = DOCS / "en"
ZH = DOCS / "zh"
QUICKSTART = "quickstart.md"
RUN_COMMAND = re.compile(r"\bskeptic\s+(run|bench)\b")
OUT_DIR = re.compile(r"--out\s+(\S+)")
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def relative_files(root: Path) -> set[str]:
    """Return posix paths of files under ``root``, relative to ``root``."""
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def extract_commands(text: str) -> list[str]:
    """Return shell commands from fenced ``bash`` blocks.

    A trailing backslash joins the next line. Blank lines and ``#`` comments
    are skipped.
    """
    commands: list[str] = []
    for block in FENCE.findall(text):
        pending: list[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("\\"):
                pending.append(line[:-1].strip())
                continue
            pending.append(line)
            commands.append(" ".join(pending))
            pending = []
        if pending:
            commands.append(" ".join(pending))
    return commands


def check_locales() -> list[str]:
    """Return human-readable mismatches between the English and Chinese trees."""
    if not EN.is_dir() or not ZH.is_dir():
        return [f"missing locale directory: en={EN.is_dir()} zh={ZH.is_dir()}"]
    en_files = relative_files(EN)
    zh_files = relative_files(ZH)
    errors: list[str] = []
    only_en = sorted(en_files - zh_files)
    only_zh = sorted(zh_files - en_files)
    if only_en:
        errors.append("only in docs/en: " + ", ".join(only_en))
    if only_zh:
        errors.append("only in docs/zh: " + ", ".join(only_zh))
    if not en_files:
        errors.append("docs/en has no files")
    return errors


def check_commands(en_commands: list[str], zh_commands: list[str]) -> list[str]:
    """Return errors when the two quickstarts disagree or skip FakeLLM."""
    errors: list[str] = []
    if not en_commands:
        errors.append("docs/en/quickstart.md has no bash commands")
    if en_commands != zh_commands:
        errors.append("quickstart bash commands differ between en and zh")
        errors.append("en: " + " | ".join(en_commands))
        errors.append("zh: " + " | ".join(zh_commands))
    for command in en_commands:
        if not command.startswith("uv run skeptic"):
            errors.append(f"quickstart command must start with 'uv run skeptic': {command}")
        if RUN_COMMAND.search(command) and "fake/" not in command:
            errors.append(f"quickstart run must use FakeLLM: {command}")
    return errors


def reset_out_dir(command: str) -> None:
    """Remove a ``--out`` directory when it stays under ``runs/``."""
    match = OUT_DIR.search(command)
    if match is None:
        return
    raw = Path(match.group(1))
    if raw.is_absolute():
        return
    target = (ROOT / raw).resolve()
    runs = (ROOT / "runs").resolve()
    if target != runs and runs not in target.parents:
        return
    if target.exists():
        shutil.rmtree(target)


def execute(commands: list[str]) -> int:
    """Run quickstart commands from the repository root. Return the exit code."""
    tmp = ROOT / "runs" / "docs-quickstart-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Keep an inherited path (pytest points this at tmp). Otherwise the
    # quickstart ledger stays under runs/ and does not touch bench/ledger.csv.
    if not env.get("SKEPTIC_LEDGER_PATH"):
        env["SKEPTIC_LEDGER_PATH"] = str(tmp / "ledger.csv")
    for command in commands:
        reset_out_dir(command)
        print(f"===== {command} =====", flush=True)
        try:
            completed = subprocess.run(
                command.split(),
                cwd=ROOT,
                env=env,
                check=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            print("EXIT=timeout", flush=True)
            return 1
        print(f"EXIT={completed.returncode}", flush=True)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    """Compare locale files and quickstart commands, then optionally run them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the quickstart commands from the repository root.",
    )
    args = parser.parse_args(argv)

    errors = check_locales()
    en_text = (EN / QUICKSTART).read_text(encoding="utf-8") if (EN / QUICKSTART).is_file() else ""
    zh_text = (ZH / QUICKSTART).read_text(encoding="utf-8") if (ZH / QUICKSTART).is_file() else ""
    en_commands = extract_commands(en_text)
    zh_commands = extract_commands(zh_text)
    errors.extend(check_commands(en_commands, zh_commands))
    en_count = len(relative_files(EN)) if EN.is_dir() else 0
    zh_count = len(relative_files(ZH)) if ZH.is_dir() else 0
    print(f"en_files={en_count} zh_files={zh_count} commands={len(en_commands)}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    if args.execute:
        return execute(en_commands)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
