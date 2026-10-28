"""Fault id to implementation mapping (S6).

F20 registers nothing; F21-F24 add the 20 concrete faults.
"""

from skeptic_agent.faults.base import Fault

REGISTRY: dict[str, type[Fault]] = {}
"""The concrete fault classes, keyed by S6 fault id."""

FAULT_IDS: tuple[str, ...] = (
    "L01",
    "L02",
    "L03",
    "L04",
    "L05",
    "L06",
    "L07",
    "S01",
    "S02",
    "S03",
    "S04",
    "S05",
    "S06",
    "S07",
    "S08",
    "S09",
    "S10",
    "A01",
    "A02",
    "A03",
)
"""Every fault id of S6, in catalogue order."""


def register(fault_cls: type[Fault]) -> type[Fault]:
    """Add a fault class to the registry under its ``id``.

    Args:
        fault_cls: The fault class.

    Returns:
        The same class, so this works as a decorator.
    """
    REGISTRY[fault_cls.id] = fault_cls
    return fault_cls


def get_fault(fault_id: str) -> type[Fault] | None:
    """Look up a fault class.

    Args:
        fault_id: The S6 fault id.

    Returns:
        The class, or ``None`` when no implementation is registered yet.
    """
    return REGISTRY.get(fault_id)
