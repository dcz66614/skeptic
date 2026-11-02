"""Budget tracker and ledger accounting for Skeptic runs (1.8, E40).

Enforces cost caps during benchmark/eval runs and records usage into
the centralized ledger file.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MAX_COST_USD: float = 5.0
EXIT_BUDGET_EXCEEDED: int = 5
LEDGER_HEADER: list[str] = [
    "timestamp",
    "task_id",
    "agent_name",
    "run_id",
    "model",
    "episodes",
    "tokens_in",
    "tokens_out",
    "cost_usd",
]


class BudgetExceededError(Exception):
    """Raised when cumulative cost reaches or exceeds the configured limit (1.8)."""


def _default_max_cost() -> float:
    env_val = os.getenv("SKEPTIC_MAX_COST_USD")
    if env_val:
        try:
            return float(env_val)
        except ValueError:
            pass
    return DEFAULT_MAX_COST_USD


@dataclass
class BudgetTracker:
    """Tracks cumulative token usage and costs across dispatched episodes.

    Attributes:
        max_cost_usd: Maximum allowed cumulative cost in USD.
        spent_usd: Total spent so far in USD.
        tokens_in: Total prompt tokens consumed.
        tokens_out: Total completion tokens generated.
        episodes_completed: Number of episodes completed.
    """

    max_cost_usd: float = field(default_factory=_default_max_cost)
    spent_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    episodes_completed: int = 0

    def can_dispatch(self) -> bool:
        """Check whether another episode can be dispatched under the budget limit."""
        return self.spent_usd < self.max_cost_usd

    def check_can_dispatch(self) -> None:
        """Raise ``BudgetExceededError`` if cumulative spending reached the ceiling."""
        if not self.can_dispatch():
            raise BudgetExceededError(
                f"Cumulative cost ${self.spent_usd:.4f} reached or exceeded limit "
                f"${self.max_cost_usd:.4f} (exit code {EXIT_BUDGET_EXCEEDED})"
            )

    def record_spend(
        self,
        cost_usd: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Record usage and cost from a completed episode.

        Args:
            cost_usd: Cost of the episode in USD.
            tokens_in: Input tokens consumed.
            tokens_out: Output tokens produced.
        """
        self.spent_usd += max(0.0, cost_usd)
        self.tokens_in += max(0, tokens_in)
        self.tokens_out += max(0, tokens_out)
        self.episodes_completed += 1


def append_ledger_entry(
    ledger_path: Path | str,
    *,
    task_id: str,
    agent_name: str,
    run_id: str,
    model: str,
    episodes: int,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    timestamp: str | None = None,
) -> None:
    """Append one run accounting line to the ledger CSV (1.8).

    Format:
    ``timestamp,task_id,agent_name,run_id,model,episodes,tokens_in,tokens_out,cost_usd``

    Args:
        ledger_path: Path to ``bench/ledger.csv``.
        task_id: Current task ID (e.g. 'E40').
        agent_name: Adapter or agent spec name.
        run_id: Unique run ID.
        model: Model identifier.
        episodes: Number of episodes completed in this run.
        tokens_in: Total input tokens.
        tokens_out: Total output tokens.
        cost_usd: Total run cost in USD.
        timestamp: ISO UTC timestamp, or None to use current time.
    """
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = path.is_file() and path.stat().st_size > 0
    ts = timestamp or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    row: dict[str, Any] = {
        "timestamp": ts,
        "task_id": task_id,
        "agent_name": agent_name,
        "run_id": run_id,
        "model": model,
        "episodes": episodes,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": f"{cost_usd:.6f}",
    }

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_HEADER)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
