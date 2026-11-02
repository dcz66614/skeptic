"""Reference Agent Adapter (S13.2, S13.3, E40)."""

from __future__ import annotations

from skeptic_agent.runner.adapters.base import AgentRunResult, EpisodeTask
from skeptic_agent.runner.reference_agent import ReferenceAgent


class ReferenceAdapter:
    """Adapter wrapping ReferenceAgent satisfying AgentAdapter protocol (S13.2)."""

    name: str = "reference"

    async def run(self, task: EpisodeTask) -> AgentRunResult:
        """Run the reference agent on the given task."""
        agent = ReferenceAgent()
        return await agent.run(task)
