"""Scratch directory for episode and oracle work files (CI313)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["TMP_ENV", "resolve_tmp_dir"]

TMP_ENV = "SKEPTIC_TMP"
"""The environment variable that names the scratch root."""


def resolve_tmp_dir() -> Path:
    """Return the scratch root for per-episode work directories.

    The root is ``$SKEPTIC_TMP`` when that variable is set and not blank,
    otherwise ``<system temp dir>/skeptic``. It never depends on the current
    working directory, so a run started from a project checkout does not fill
    the checkout with ``ep_*`` directories.

    Returns:
        The scratch root. The directory is not created here.
    """
    override = os.environ.get(TMP_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / "skeptic"
