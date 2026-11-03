"""Alias for injection_shield module (G07, S11)."""

from skeptic_agent.guards.injection_shield import (
    DEFAULT_SENSITIVE_TOOLS,
    INJECTION_SHIELD_BLOCK_TEXT,
    INJECTION_SHIELD_REMOVED_TEMPLATE,
    InjectionShield,
    extract_taint_entities,
    scan_and_clean_text,
    value_contains_taint,
)

__all__ = [
    "DEFAULT_SENSITIVE_TOOLS",
    "INJECTION_SHIELD_BLOCK_TEXT",
    "INJECTION_SHIELD_REMOVED_TEMPLATE",
    "InjectionShield",
    "extract_taint_entities",
    "scan_and_clean_text",
    "value_contains_taint",
]
