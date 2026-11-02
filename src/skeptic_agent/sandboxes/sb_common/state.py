"""The sandbox state dict and its optional state file (S9.1, S9.3).

Every sandbox keeps one in-memory ``dict``. A write tool mutates it and then
calls :meth:`SandboxState.save`, which rewrites ``SKEPTIC_STATE_FILE``
atomically (temp file then rename), so a reader never sees a half-written
file. The file is written once when the server starts, even for an all-read
sandbox, so the scenario's ``state_checks`` always have a file to read.

``updated_at`` comes from :mod:`skeptic_agent.sandboxes.sb_common.clock`, the
same frozen clock every tool reads (S9.3 shows it in the file).
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from skeptic_agent.sandboxes.sb_common import clock

STATE_FILE_ENV = "SKEPTIC_STATE_FILE"
"""The environment variable holding the state file path (S9.1)."""


class SandboxState:
    """The one mutable state dict of a sandbox, plus its state-file writer."""

    def __init__(self, data: dict[str, Any], state_file: Path | None = None) -> None:
        """Wrap the initial state.

        Args:
            data: The in-memory state. The sandbox mutates it in place.
            state_file: Where to write it after each write, or ``None`` to
                keep the state in memory only.
        """
        self.data = data
        self.state_file = state_file

    @classmethod
    def from_env(cls, data: dict[str, Any]) -> "SandboxState":
        """Build a state whose file is ``SKEPTIC_STATE_FILE``, when set.

        Args:
            data: The initial in-memory state.

        Returns:
            The state. It has no file when the variable is unset or empty.
        """
        return cls(data, state_file_from_env())

    def save(self) -> None:
        """Write the whole state atomically, stamping ``updated_at``.

        The timestamp is copied into a JSON-safe form first, so the in-memory
        state keeps its ``datetime`` and the file gets the S9.1 string. The
        write goes to a temp file beside the target and is then renamed, so a
        concurrent reader sees either the old file or the new one.
        """
        if self.state_file is None:
            return
        moment = clock.now()
        self.data["updated_at"] = moment
        payload = {**self.data, "updated_at": clock.format_iso(moment)}
        write_json_atomic(self.state_file, payload)


def state_file_from_env() -> Path | None:
    """Return the configured state file path.

    Returns:
        The path in ``SKEPTIC_STATE_FILE``, or ``None`` when it is unset or
        empty.
    """
    value = os.environ.get(STATE_FILE_ENV)
    return Path(value) if value else None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to ``path`` through a temp file and a rename.

    Args:
        path: The destination file.
        payload: The JSON object to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
