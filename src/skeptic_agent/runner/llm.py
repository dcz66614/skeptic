"""LLM provider routing, pricing, and client factory (S13.1, S13.3, S16.1, E40)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI

from skeptic_agent.runner.fake_llm import FakeLLM

MODELS_YAML_PATH = Path(__file__).resolve().parents[3] / "bench" / "leaderboard" / "models.yaml"

DEFAULT_PRICE_IN_PER_MTOK: float = 0.50
DEFAULT_PRICE_OUT_PER_MTOK: float = 1.50


@dataclass(frozen=True)
class ModelConfig:
    """Resolved model client configuration (S13.1).

    Attributes:
        provider: Provider identifier ('openrouter', 'openai', 'compat', 'fake').
        model_name: Name or path to pass to provider API.
        base_url: Custom API endpoint, or None for standard provider default.
        api_key: Authentication token.
        is_fake: Whether this is a local FakeLLM script model.
    """

    provider: str
    model_name: str
    base_url: str | None = None
    api_key: str | None = None
    is_fake: bool = False


def parse_agent_spec(spec: str) -> tuple[str, str]:
    """Parse an agent specification string into (adapter, model) (S13.1).

    Format: ``<adapter>:<model>``

    Examples:
        - ``reference:openrouter/anthropic/claude-3.5-sonnet``
        - ``reference:fake/oracle_follower``
        - ``openai-agents:openai/gpt-4o``
        - ``command:codex``

    Args:
        spec: The agent specification string.

    Returns:
        (adapter, model) tuple.
    """
    if ":" in spec:
        adapter, model = spec.split(":", 1)
        return adapter.strip(), model.strip()
    return spec.strip(), "fake/oracle_follower"


def resolve_model(model_spec: str) -> ModelConfig:
    """Resolve a model specification string to provider credentials and URLs (S13.1).

    Specs:
        - ``openrouter/<vendor>/<model>``: uses https://openrouter.ai/api/v1 + OPENROUTER_API_KEY
        - ``openai/<model>``: uses standard OpenAI API + OPENAI_API_KEY
        - ``compat/<model>``: uses SKEPTIC_COMPAT_BASE_URL + SKEPTIC_COMPAT_API_KEY
        - ``fake/<script>``: local FakeLLM mock

    Args:
        model_spec: Model specification string.

    Returns:
        Resolved ModelConfig.
    """
    spec = model_spec.strip()

    if spec.startswith("fake/"):
        script = spec.removeprefix("fake/")
        return ModelConfig(
            provider="fake",
            model_name=script,
            base_url=None,
            api_key=None,
            is_fake=True,
        )

    if spec.startswith("openrouter/"):
        target_model = spec.removeprefix("openrouter/")
        return ModelConfig(
            provider="openrouter",
            model_name=target_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            is_fake=False,
        )

    if spec.startswith("openai/"):
        target_model = spec.removeprefix("openai/")
        return ModelConfig(
            provider="openai",
            model_name=target_model,
            base_url=None,
            api_key=os.getenv("OPENAI_API_KEY", ""),
            is_fake=False,
        )

    if spec.startswith("compat/"):
        target_model = spec.removeprefix("compat/")
        return ModelConfig(
            provider="compat",
            model_name=target_model,
            base_url=os.getenv("SKEPTIC_COMPAT_BASE_URL", ""),
            api_key=os.getenv("SKEPTIC_COMPAT_API_KEY", ""),
            is_fake=False,
        )

    # Bare model name defaults to openai
    return ModelConfig(
        provider="openai",
        model_name=spec,
        base_url=None,
        api_key=os.getenv("OPENAI_API_KEY", ""),
        is_fake=False,
    )


def create_llm_client(model_spec: str, *, scenario: Any = None) -> Any:
    """Create an OpenAI-compatible client for the given model specification (S13.1, S13.3).

    Args:
        model_spec: Specification string (e.g. 'fake/oracle_follower' or 'openai/gpt-4o').
        scenario: Optional scenario passed to FakeLLM.

    Returns:
        An ``AsyncOpenAI`` client or a ``FakeLLM`` instance.
    """
    config = resolve_model(model_spec)
    if config.is_fake:
        return FakeLLM(config.model_name, scenario=scenario)

    return AsyncOpenAI(base_url=config.base_url, api_key=config.api_key or "sk-dummy")


def get_model_pricing(
    model_spec: str,
    models_yaml: Path | None = None,
) -> tuple[float, float]:
    """Look up pricing in models.yaml or return defaults (S16.1).

    Args:
        model_spec: Model spec string.
        models_yaml: Optional path to models.yaml.

    Returns:
        (price_in_per_mtok, price_out_per_mtok) in USD.
    """
    if model_spec.startswith("fake/"):
        return 0.0, 0.0

    path = models_yaml or MODELS_YAML_PATH
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "models" in data:
                for entry in data["models"]:
                    if entry.get("id") == model_spec:
                        pin = float(entry.get("price_in_per_mtok", DEFAULT_PRICE_IN_PER_MTOK))
                        pout = float(entry.get("price_out_per_mtok", DEFAULT_PRICE_OUT_PER_MTOK))
                        return pin, pout
        except Exception:
            pass

    return DEFAULT_PRICE_IN_PER_MTOK, DEFAULT_PRICE_OUT_PER_MTOK


def calculate_cost(
    model_spec: str,
    tokens_in: int,
    tokens_out: int,
    *,
    reported_cost: float | None = None,
    models_yaml: Path | None = None,
) -> float:
    """Calculate monetary cost for an LLM invocation (S13.3).

    Prioritizes reported cost from API response (e.g. OpenRouter usage.cost);
    otherwise computes tokens / 1M * price.

    Args:
        model_spec: Model specification.
        tokens_in: Prompt tokens count.
        tokens_out: Completion tokens count.
        reported_cost: Cost reported directly by provider, if any.
        models_yaml: Optional path to models.yaml.

    Returns:
        Cost in USD.
    """
    if model_spec.startswith("fake/"):
        return 0.0

    if reported_cost is not None and reported_cost >= 0.0:
        return reported_cost

    price_in, price_out = get_model_pricing(model_spec, models_yaml=models_yaml)
    cost = (tokens_in * price_in + tokens_out * price_out) / 1_000_000.0
    return round(cost, 6)
