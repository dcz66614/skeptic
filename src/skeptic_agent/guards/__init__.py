"""Guards framework and implementations (S11).

Importing this package registers all built-in Guard implementations.
"""

from skeptic_agent.guards import (
    drift,
    drift_lock,
    emptiness,
    evidence_contract,
    injection,
    injection_shield,
    loop_breaker,
    retry,
    retry_guard,
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
from skeptic_agent.guards.drift_lock import (
    DRIFT_LOCK_BLOCKED_TEXT,
    DriftLock,
)
from skeptic_agent.guards.emptiness import (
    EMPTINESS_GUARD_TEXT,
    EmptinessGuard,
)
from skeptic_agent.guards.evidence_contract import (
    EVIDENCE_CONTRACT_TEXT,
    EvidenceContract,
)
from skeptic_agent.guards.injection_shield import (
    INJECTION_SHIELD_BLOCK_TEXT,
    INJECTION_SHIELD_REMOVED_TEMPLATE,
    InjectionShield,
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
from skeptic_agent.guards.retry_guard import (
    RETRY_REGEX,
    RetryGuard,
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
    "DRIFT_LOCK_BLOCKED_TEXT",
    "EMPTINESS_GUARD_TEXT",
    "EVIDENCE_CONTRACT_TEXT",
    "INJECTION_SHIELD_BLOCK_TEXT",
    "INJECTION_SHIELD_REMOVED_TEMPLATE",
    "LOOP_BREAKER_TEXT_TEMPLATE",
    "PRESETS",
    "RETRY_REGEX",
    "S2C_CALL_GUARD_ORDER",
    "S2C_LIST_GUARD_ORDER",
    "SCHEMA_GUARD_TEXT_TEMPLATE",
    "STALENESS_GUARD_TEXT_TEMPLATE",
    "DriftLock",
    "EmptinessGuard",
    "EvidenceContract",
    "Guard",
    "GuardEngine",
    "GuardResult",
    "GuardSpec",
    "InjectionShield",
    "LoopBreaker",
    "RetryGuard",
    "SchemaGuard",
    "StalenessGuard",
    "build_guard_engine",
    "drift",
    "drift_lock",
    "emptiness",
    "evidence_contract",
    "get_guard",
    "injection",
    "injection_shield",
    "loop_breaker",
    "loudify",
    "register",
    "resolve_guards",
    "retry",
    "retry_guard",
    "schema_guard",
    "staleness",
]
