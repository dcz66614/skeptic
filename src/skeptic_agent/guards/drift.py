"""Alias for drift_lock module (G08, S11)."""

from skeptic_agent.guards.drift_lock import (
    DRIFT_LOCK_BLOCKED_TEXT,
    DriftLock,
    canonical_tool_hash,
)

__all__ = [
    "DRIFT_LOCK_BLOCKED_TEXT",
    "DriftLock",
    "canonical_tool_hash",
]
