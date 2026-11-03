"""Setup module for client configuration discovery and proxy wrapping (S15, K54)."""

from skeptic_agent.setup.discover import (
    DiscoveredServer,
    discover,
    generate_config,
    get_discovery_candidates,
    parse_client_file,
)
from skeptic_agent.setup.wrap import undo_wrap, wrap_file

__all__ = [
    "DiscoveredServer",
    "discover",
    "generate_config",
    "get_discovery_candidates",
    "parse_client_file",
    "undo_wrap",
    "wrap_file",
]
