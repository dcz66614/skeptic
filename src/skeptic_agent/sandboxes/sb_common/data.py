"""Reading committed sandbox data files (S9.1).

Sandboxes do not generate data at run time. Each sandbox's ``data/generate.py``
builds the JSON files once with the fixed seed ``20261101`` and they are
committed; a server only reads them. This module holds the one shared data
file, ``customers.json``, which sb_crm, sb_orders and sb_mail all use so that
customer ids agree across sandboxes (S9.1 item 9).
"""

import copy
import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
"""The committed data directory of ``sb_common``."""

CUSTOMERS_FILE = DATA_DIR / "customers.json"
"""The shared customer table (C-1001 to C-1040)."""


def load_json(path: Path) -> Any:
    """Read a committed JSON data file.

    Args:
        path: The file to read.

    Returns:
        The decoded JSON value.
    """
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_customers() -> list[dict[str, Any]]:
    """Return the shared customers, as fresh copies a sandbox may mutate.

    Returns:
        One dict per customer, in file order. Each entry has ``id``, ``name``,
        ``email``, ``tier``, ``city`` and ``created_at``.
    """
    return copy.deepcopy(load_json(CUSTOMERS_FILE))
