"""Alias module re-exporting G03 StalenessGuard (S11)."""

from skeptic_agent.guards.staleness import (
    STALENESS_GUARD_TEXT_TEMPLATE,
    StalenessGuard,
)

__all__ = [
    "STALENESS_GUARD_TEXT_TEMPLATE",
    "StalenessGuard",
]
