"""Runner adapters package (S13.2, E40)."""

from __future__ import annotations

from skeptic_agent.runner.adapters.base import (
    AgentAdapter,
    AgentRunResult,
    EpisodeTask,
    McpServerSpec,
    Usage,
)
from skeptic_agent.runner.adapters.langgraph import LangGraphAdapter
from skeptic_agent.runner.adapters.openai_agents import OpenAIAgentsAdapter
from skeptic_agent.runner.adapters.reference import ReferenceAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "reference": ReferenceAdapter,
    "openai-agents": OpenAIAgentsAdapter,
    "langgraph": LangGraphAdapter,
}


def get_adapter(name: str) -> AgentAdapter:
    """Retrieve an agent adapter by name (S13.1, S13.2).

    Args:
        name: The adapter name (e.g. 'reference').

    Returns:
        An instantiated AgentAdapter.

    Raises:
        ValueError: When the adapter name is not recognized.
    """
    cls = ADAPTERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown agent adapter: {name!r}. Available: {list(ADAPTERS.keys())}")
    return cls()


__all__ = [
    "ADAPTERS",
    "AgentAdapter",
    "AgentRunResult",
    "EpisodeTask",
    "LangGraphAdapter",
    "McpServerSpec",
    "OpenAIAgentsAdapter",
    "ReferenceAdapter",
    "Usage",
    "get_adapter",
]
