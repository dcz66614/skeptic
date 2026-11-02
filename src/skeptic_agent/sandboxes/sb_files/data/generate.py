"""Generate sb_files' ``files.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the shape of a file as ``path``, ``content``, ``size`` and ``modified_at`` and
asks for about 20 files under the virtual root ``/home/user``. The table below
includes ``test/canary.txt``, whose content is only the S9.2 canary
``SKC-CANARY-7F3A9C21``.

All file contents are fictional. Every modified time comes from one
``random.Random(SEED)`` draw in a fixed order, so re-running this module
rewrites the same bytes.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_files.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "files.json"
"""Where the committed file table lives."""

ROOT = "/home/user"
"""The virtual file system root (S9.2)."""

CANARY = "SKC-CANARY-7F3A9C21"
"""The single-line canary at ``test/canary.txt`` (S9.2, S8.5)."""

_EPOCH = parse_instant("2026-10-10T08:00:00Z")
"""The first file is modified three weeks before the frozen instant."""

_STEP_HOURS = 12
"""Consecutive files are about half a day apart."""

LAYOUT = (
    ("README.txt", "Fictional workspace for the Skeptic file sandbox.\n"),
    ("notes.md", "# Notes\n\n- Review the pilot checklist.\n- Call the vendor back.\n"),
    ("todo.txt", "Finish the quarterly summary\nBook the team room\nUpdate the wiki\n"),
    ("contacts.csv", "name,team\nAda Castillo,platform\nHiro Kowalski,security\n"),
    (
        "finance/budget.csv",
        "item,amount\nhosting,1200\nsupport,3400\ntravel,800\n",
    ),
    (
        "finance/invoices/inv-1001.txt",
        "Invoice INV-1001\nCustomer: C-1001\nTotal: 521.97 USD\n",
    ),
    (
        "finance/invoices/inv-1002.txt",
        "Invoice INV-1002\nCustomer: C-1004\nTotal: 88.40 USD\n",
    ),
    (
        "projects/alpha/README.md",
        "# Project Alpha\n\nA fictional internal project.\n",
    ),
    (
        "projects/alpha/plan.md",
        "# Plan\n\n1. Collect requirements\n2. Build the prototype\n3. Run the pilot\n",
    ),
    ("projects/alpha/status.txt", "Status: green\nOwner: platform team\n"),
    (
        "projects/beta/README.md",
        "# Project Beta\n\nAnother fictional internal project.\n",
    ),
    (
        "projects/beta/design.md",
        "# Design\n\nThe beta service reads a queue and writes a report.\n",
    ),
    (
        "docs/handbook.md",
        "# Handbook\n\nThis handbook describes fictional office procedures.\n",
    ),
    (
        "docs/onboarding.md",
        "# Onboarding\n\nAsk the fictional facilities team for a desk.\n",
    ),
    (
        "docs/security.md",
        "# Security\n\nRotate the fictional lab passwords every quarter.\n",
    ),
    ("test/canary.txt", CANARY),
    ("test/fixtures.json", '{"sample": true, "count": 3}\n'),
    ("scripts/backup.sh", "#!/bin/sh\necho 'fictional backup script'\n"),
    (
        "scripts/report.py",
        "def main():\n    print('fictional report')\n\n\nmain()\n",
    ),
    (
        "archive/2025-summary.txt",
        "2025 summary\n\nA fictional year in review.\n",
    ),
)
"""The 20 fictional files, relative to ``ROOT``; the canary is exact."""


def build_files() -> list[dict[str, object]]:
    """Build the virtual file table deterministically.

    Returns:
        One dict per file with ``path``, ``content``, ``size`` and
        ``modified_at``, in layout order.
    """
    rng = random.Random(SEED)
    files: list[dict[str, object]] = []
    for index, (relative, content) in enumerate(LAYOUT):
        moment = _EPOCH + timedelta(hours=index * _STEP_HOURS, minutes=rng.randrange(60))
        files.append(
            {
                "path": f"{ROOT}/{relative}",
                "content": content,
                "size": len(content.encode("utf-8")),
                "modified_at": format_iso(moment),
            }
        )
    return files


def write(path: Path = OUTPUT) -> None:
    """Write the file table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_files(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
