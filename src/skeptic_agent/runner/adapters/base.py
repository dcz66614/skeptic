"""Adapter protocols and task specifications (S13.2, E40)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class McpServerSpec:
    """Specification for an MCP server wrapped by skeptic proxy (S13.2).

    Attributes:
        name: Logical server name (e.g. 'weather', 'mail').
        command: Already wrapped invocation command list.
        env: Environment variables for this server.
    """

    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EpisodeTask:
    """The task presented to an agent adapter for one episode (S13.2).

    Attributes:
        episode_id: Full episode identifier string.
        prompt: Task prompt concatenated with answer_format.
        servers: MCP servers available to the agent.
        model: Model specification string (S13.1).
        max_steps: Maximum turns allowed before stopping.
        timeout_s: Wall-clock timeout in seconds.
        prompt_variant: System prompt variant ('plain' or 'evidence_contract').
        workdir: Dedicated working directory for this episode.
        env: Base environment dictionary.
        scenario: Underlying scenario object, if loaded.
    """

    episode_id: str
    prompt: str
    servers: list[McpServerSpec]
    model: str
    max_steps: int
    timeout_s: int
    prompt_variant: Literal["plain", "evidence_contract"]
    workdir: Path
    env: dict[str, str]
    scenario: Any = None


@dataclass
class Usage:
    """Resource consumption recorded for an agent run (S13.2, S10.1).

    Attributes:
        tokens_in: Prompt tokens used.
        tokens_out: Completion tokens produced.
        cost_usd: Total monetary cost in USD.
        latency_s: Elapsed wall-clock time in seconds.
        steps: Total agent loop turns taken.
        tool_calls: Total MCP tool calls made.
    """

    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    steps: int = 0
    tool_calls: int = 0


@dataclass
class AgentRunResult:
    """Result returned by an agent adapter (S13.2).

    Attributes:
        final_answer: The final textual answer emitted by the agent.
        usage: Token counts and cost metrics.
        transcript: OpenAI-style message dictionary trace (best effort).
        steps: Number of steps completed.
        error: Infrastructure error description if failed, else None.
    """

    final_answer: str
    usage: Usage
    transcript: list[dict[str, Any]]
    steps: int
    error: str | None = None


class AgentAdapter(Protocol):
    """Protocol satisfied by all framework adapters (S13.2)."""

    name: str

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Execute the task and return the run result."""
        ...
