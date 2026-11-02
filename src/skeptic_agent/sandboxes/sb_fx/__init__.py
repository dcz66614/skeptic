"""sb_fx: the read-only foreign-exchange sandbox (S9.2, S31)."""

from skeptic_agent.sandboxes.sb_fx.server import NAME, TOOLS, build_state, main

__all__ = ["NAME", "TOOLS", "build_state", "main"]
