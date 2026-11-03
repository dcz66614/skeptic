"""Runner adapters package (S13.2, E40, E42, E43, E44, E45, E49fix)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, cast

from skeptic_agent.runner.adapters.base import (
    AgentAdapter,
    AgentRunResult,
    EpisodeTask,
    McpServerSpec,
    Usage,
)
from skeptic_agent.runner.adapters.command import CommandAdapter
from skeptic_agent.runner.adapters.reference import ReferenceAdapter


def _load_reference() -> type[AgentAdapter]:
    return ReferenceAdapter


def _load_command() -> type[AgentAdapter]:
    return CommandAdapter


def _load_crewai() -> type[AgentAdapter]:
    from skeptic_agent.runner.adapters.crewai import CrewAIAdapter

    return CrewAIAdapter


def _load_langgraph() -> type[AgentAdapter]:
    from skeptic_agent.runner.adapters.langgraph import LangGraphAdapter

    return LangGraphAdapter


def _load_openai_agents() -> type[AgentAdapter]:
    from skeptic_agent.runner.adapters.openai_agents import OpenAIAgentsAdapter

    return OpenAIAgentsAdapter


def _load_pydantic_ai() -> type[AgentAdapter]:
    from skeptic_agent.runner.adapters.pydantic_ai import PydanticAIAdapter

    return PydanticAIAdapter


_ADAPTER_LOADERS: dict[str, Callable[[], type[AgentAdapter]]] = {
    "reference": _load_reference,
    "openai-agents": _load_openai_agents,
    "langgraph": _load_langgraph,
    "crewai": _load_crewai,
    "pydantic-ai": _load_pydantic_ai,
    "command": _load_command,
}


class _LazyAdapterRegistry(dict[str, type[AgentAdapter]]):
    """Lazy dictionary of agent adapters delaying imports until requested (E49fix)."""

    def __init__(self, loaders: Mapping[str, Callable[[], type[AgentAdapter]]]) -> None:
        self._loaders = dict(loaders)
        super().__init__({k: cast(type[AgentAdapter], None) for k in self._loaders})

    def __getitem__(self, key: str) -> type[AgentAdapter]:
        if key not in self._loaders:
            raise KeyError(key)
        cached = super().get(key)
        if cached is not None:
            return cached
        cls = self._loaders[key]()
        super().__setitem__(key, cls)
        return cls

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._loaders:
            return default
        try:
            return self[key]
        except KeyError:
            return default

    def __iter__(self) -> Iterator[str]:
        return iter(self._loaders)

    def __len__(self) -> int:
        return len(self._loaders)

    def __contains__(self, key: object) -> bool:
        return key in self._loaders

    def keys(self) -> Any:
        return self._loaders.keys()

    def values(self) -> Any:
        return [self[k] for k in self._loaders]

    def items(self) -> Any:
        return [(k, self[k]) for k in self._loaders]


ADAPTERS: dict[str, type[AgentAdapter]] = _LazyAdapterRegistry(_ADAPTER_LOADERS)


def get_adapter(name: str) -> AgentAdapter:
    """Retrieve an agent adapter by name (S13.1, S13.2).

    Args:
        name: The adapter name (e.g. 'reference', 'crewai', 'pydantic-ai', 'command').

    Returns:
        An instantiated AgentAdapter.

    Raises:
        ValueError: When the adapter name is not recognized.
        ImportError: When the optional framework dependency is not installed.
    """
    if name not in _ADAPTER_LOADERS:
        raise ValueError(
            f"Unknown agent adapter: {name!r}. Available: {list(_ADAPTER_LOADERS.keys())}"
        )
    cls = ADAPTERS[name]
    return cls()


def __getattr__(name: str) -> Any:
    """Support lazy module-level attribute access for adapter classes (E49fix)."""
    if name == "CrewAIAdapter":
        return _load_crewai()
    if name == "LangGraphAdapter":
        return _load_langgraph()
    if name == "OpenAIAgentsAdapter":
        return _load_openai_agents()
    if name == "PydanticAIAdapter":
        return _load_pydantic_ai()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ADAPTERS",
    "AgentAdapter",
    "AgentRunResult",
    "CommandAdapter",
    "CrewAIAdapter",
    "EpisodeTask",
    "LangGraphAdapter",
    "McpServerSpec",
    "OpenAIAgentsAdapter",
    "PydanticAIAdapter",
    "ReferenceAdapter",
    "Usage",
    "get_adapter",
]
