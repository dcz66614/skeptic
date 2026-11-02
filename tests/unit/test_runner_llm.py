"""Unit tests for runner LLM helpers and FakeLLM scripts (S13, E40)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skeptic_agent.runner.fake_llm import FakeLLM
from skeptic_agent.runner.llm import (
    calculate_cost,
    get_model_pricing,
    parse_agent_spec,
    resolve_model,
)

pytestmark = pytest.mark.unit


def test_parse_agent_spec() -> None:
    """Agent spec format parses <adapter>:<model> correctly."""
    assert parse_agent_spec("reference:openai/gpt-4o") == ("reference", "openai/gpt-4o")
    assert parse_agent_spec("langgraph:fake/honest") == ("langgraph", "fake/honest")
    assert parse_agent_spec("reference") == ("reference", "fake/oracle_follower")


def test_resolve_model_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Models from different providers resolve to correct URLs and keys."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("SKEPTIC_COMPAT_BASE_URL", "http://compat.local/v1")
    monkeypatch.setenv("SKEPTIC_COMPAT_API_KEY", "compat-key")

    cfg_or = resolve_model("openrouter/deepseek/deepseek-chat")
    assert cfg_or.provider == "openrouter"
    assert cfg_or.base_url == "https://openrouter.ai/api/v1"
    assert cfg_or.api_key == "or-key"
    assert cfg_or.model_name == "deepseek/deepseek-chat"

    cfg_oa = resolve_model("openai/gpt-4o-mini")
    assert cfg_oa.provider == "openai"
    assert cfg_oa.api_key == "oa-key"
    assert cfg_oa.model_name == "gpt-4o-mini"

    cfg_compat = resolve_model("compat/local-qwen")
    assert cfg_compat.provider == "compat"
    assert cfg_compat.base_url == "http://compat.local/v1"
    assert cfg_compat.api_key == "compat-key"
    assert cfg_compat.model_name == "local-qwen"

    cfg_bare = resolve_model("gpt-3.5-turbo")
    assert cfg_bare.provider == "openai"


def test_pricing_and_cost(tmp_path: Path) -> None:
    """Cost calculation uses models.yaml pricing or defaults (S16.1, S13.3)."""
    yaml_file = tmp_path / "models.yaml"
    models_content = {
        "schema": "skeptic.models/v1",
        "models": [
            {
                "id": "openrouter/custom/model",
                "price_in_per_mtok": 1.0,
                "price_out_per_mtok": 2.0,
            }
        ],
    }
    yaml_file.write_text(yaml.safe_dump(models_content), encoding="utf-8")

    pin, pout = get_model_pricing("openrouter/custom/model", models_yaml=yaml_file)
    assert pin == 1.0
    assert pout == 2.0

    cost = calculate_cost("openrouter/custom/model", 1_000_000, 1_000_000, models_yaml=yaml_file)
    assert cost == 3.0

    # Reported cost overrides formula
    assert calculate_cost("openrouter/custom/model", 100, 100, reported_cost=0.0123) == 0.0123


@pytest.mark.asyncio
async def test_fake_llm_scripts() -> None:
    """FakeLLM scripts (gullible, honest, looper) execute turns properly."""
    # Gullible turn 1
    gullible = FakeLLM("gullible")
    res1 = await gullible.generate(
        model="fake/gullible", messages=[{"role": "user", "content": "hi"}]
    )
    assert res1.choices[0].message.tool_calls is not None

    # Gullible turn 2 with tool response containing a number
    res2 = await gullible.generate(
        model="fake/gullible",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "The max temp was 28.5 degrees."},
        ],
    )
    assert res2.choices[0].message.content == "28.5"

    # Honest script on corrupted response
    honest = FakeLLM("honest")
    res_honest = await honest.generate(
        model="fake/honest",
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "ERROR: upstream timeout"},
        ],
    )
    assert "RETRIEVAL_STATUS: FAILED" in (res_honest.choices[0].message.content or "")

    # Looper script
    looper = FakeLLM("looper")
    res_loop = await looper.generate(model="fake/looper", messages=[])
    assert res_loop.choices[0].message.tool_calls is not None
