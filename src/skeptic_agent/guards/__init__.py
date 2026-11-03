"""Guards framework and implementations (S11).

Importing this package registers all built-in Guard implementations.
"""

from skeptic_agent.guards import evidence_contract, loop_breaker  # noqa: F401
from skeptic_agent.guards.base import (
    C2S_GUARD_ORDER,
    S2C_CALL_GUARD_ORDER,
    S2C_LIST_GUARD_ORDER,
    Guard,
    GuardEngine,
    GuardResult,
    GuardSpec,
    build_guard_engine,
    get_guard,
    loudify,
    register,
)
from skeptic_agent.guards.evidence_contract import (
    EVIDENCE_CONTRACT_TEXT,
    EvidenceContract,
)
from skeptic_agent.guards.loop_breaker import (
    LOOP_BREAKER_TEXT_TEMPLATE,
    LoopBreaker,
)
from skeptic_agent.guards.presets import (
    ALL_GUARDS,
    PRESETS,
    resolve_guards,
)

__all__ = [
    "ALL_GUARDS",
    "C2S_GUARD_ORDER",
    "EVIDENCE_CONTRACT_TEXT",
    "LOOP_BREAKER_TEXT_TEMPLATE",
    "PRESETS",
    "S2C_CALL_GUARD_ORDER",
    "S2C_LIST_GUARD_ORDER",
    "EvidenceContract",
    "Guard",
    "GuardEngine",
    "GuardResult",
    "GuardSpec",
    "LoopBreaker",
    "build_guard_engine",
    "get_guard",
    "loudify",
    "register",
    "resolve_guards",
]
