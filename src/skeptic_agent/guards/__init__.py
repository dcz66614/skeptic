"""Guards framework and implementations (S11).

Importing this package registers all built-in Guard implementations.
"""

from skeptic_agent.guards import (
    emptiness,
    evidence_contract,
    loop_breaker,
    schema_guard,
    staleness,
)
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
from skeptic_agent.guards.emptiness import (
    EMPTINESS_GUARD_TEXT,
    EmptinessGuard,
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
from skeptic_agent.guards.schema_guard import (
    SCHEMA_GUARD_TEXT_TEMPLATE,
    SchemaGuard,
)
from skeptic_agent.guards.staleness import (
    STALENESS_GUARD_TEXT_TEMPLATE,
    StalenessGuard,
)

__all__ = [
    "ALL_GUARDS",
    "C2S_GUARD_ORDER",
    "EMPTINESS_GUARD_TEXT",
    "EVIDENCE_CONTRACT_TEXT",
    "LOOP_BREAKER_TEXT_TEMPLATE",
    "PRESETS",
    "S2C_CALL_GUARD_ORDER",
    "S2C_LIST_GUARD_ORDER",
    "SCHEMA_GUARD_TEXT_TEMPLATE",
    "STALENESS_GUARD_TEXT_TEMPLATE",
    "EmptinessGuard",
    "EvidenceContract",
    "Guard",
    "GuardEngine",
    "GuardResult",
    "GuardSpec",
    "LoopBreaker",
    "SchemaGuard",
    "StalenessGuard",
    "build_guard_engine",
    "emptiness",
    "evidence_contract",
    "get_guard",
    "loop_breaker",
    "loudify",
    "register",
    "resolve_guards",
    "schema_guard",
    "staleness",
]
