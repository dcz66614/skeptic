"""Unit tests for runner LLM helpers and FakeLLM scripts (S13, E40)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jsonschema
import pytest
import yaml

from skeptic_agent.runner.adapters.base import EpisodeTask
from skeptic_agent.runner.fake_llm import FakeLLM
from skeptic_agent.runner.llm import (
    calculate_cost,
    get_dev_model,
    get_model_pricing,
    parse_agent_spec,
    resolve_model,
)
from skeptic_agent.runner.reference_agent import ReferenceAgent

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


def test_models_yaml_schema_and_dev_tier() -> None:
    """models.yaml adheres to schema and defines a dev-tier model under $1/Mtok (S16.1, E41)."""
    repo_root = Path(__file__).resolve().parents[2]
    models_file = repo_root / "bench" / "leaderboard" / "models.yaml"
    assert models_file.is_file(), f"models.yaml missing at {models_file}"

    schema_file = repo_root / "schemas" / "models.schema.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    data = yaml.safe_load(models_file.read_text(encoding="utf-8"))

    jsonschema.validate(instance=data, schema=schema)
    assert data["schema"] == "skeptic.models/v1"
    models = data["models"]
    assert len(models) >= 1

    # Check dev tier model
    dev_models = [m for m in models if m.get("tier") == "dev"]
    assert len(dev_models) >= 1, "Must contain at least 1 tier: dev model"

    dev = dev_models[0]
    total_cost_per_mtok = float(dev["price_in_per_mtok"]) + float(dev["price_out_per_mtok"])
    assert total_cost_per_mtok <= 1.0, f"Dev model cost {total_cost_per_mtok} exceeds $1/Mtok limit"
    assert dev["supports_tools"] is True
    assert dev["id"].startswith("openrouter/")


def test_get_dev_model_helper() -> None:
    """get_dev_model helper returns expected dev tier model ID (S16.1)."""
    model_id = get_dev_model()
    assert model_id == "openrouter/openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_reference_agent_temperature_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ReferenceAgent removes temperature and retries once when model rejects it (S13.3)."""
    from openai import BadRequestError
    from openai.types import CompletionUsage
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice

    first_call = True

    async def mock_create(**kwargs: Any) -> ChatCompletion:
        nonlocal first_call
        if first_call:
            first_call = False
            # Simulate remote API rejecting temperature parameter
            resp_mock = MagicMock()
            resp_mock.status_code = 400
            resp_mock.headers = {}
            raise BadRequestError(
                message="temperature parameter is not supported by this model",
                response=resp_mock,
                body=None,
            )
        assert "temperature" not in kwargs
        msg = ChatCompletionMessage(role="assistant", content="Answer without temp")
        return ChatCompletion(
            id="chat-1",
            choices=[Choice(finish_reason="stop", index=0, message=msg)],
            created=1234567890,
            model="mock-model",
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
    monkeypatch.setattr(
        "skeptic_agent.runner.reference_agent.create_llm_client",
        lambda *args, **kwargs: mock_client,
    )

    agent = ReferenceAgent()
    task = EpisodeTask(
        episode_id="test-temp",
        prompt="hello",
        servers=[],
        model="openrouter/mock/model",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )
    res = await agent.run(task)
    assert res.final_answer == "Answer without temp"
    assert any("retried without temperature" in str(m.get("content", "")) for m in res.transcript)


@pytest.mark.asyncio
async def test_reference_agent_openrouter_cost_reporting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ReferenceAgent prioritizes usage.cost from OpenRouter response (S13.3)."""
    from openai.types import CompletionUsage
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice

    async def mock_create(**kwargs: Any) -> ChatCompletion:
        assert kwargs.get("extra_body") == {"usage": {"include": True}}
        msg = ChatCompletionMessage(role="assistant", content="42")
        usage_obj = CompletionUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30)
        # Attach reported cost as OpenRouter does
        object.__setattr__(usage_obj, "cost", 0.000456)
        return ChatCompletion(
            id="chat-2",
            choices=[Choice(finish_reason="stop", index=0, message=msg)],
            created=1234567890,
            model="openrouter/openai/gpt-4o-mini",
            object="chat.completion",
            usage=usage_obj,
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
    monkeypatch.setattr(
        "skeptic_agent.runner.reference_agent.create_llm_client",
        lambda *args, **kwargs: mock_client,
    )

    agent = ReferenceAgent()
    task = EpisodeTask(
        episode_id="test-cost",
        prompt="hello",
        servers=[],
        model="openrouter/openai/gpt-4o-mini",
        max_steps=5,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )
    res = await agent.run(task)
    assert res.final_answer == "42"
    assert res.usage.cost_usd == 0.000456


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_spec", "expected_model_sent"),
    [
        ("compat/deepseek-v4-pro", "deepseek-v4-pro"),
        ("compat/gpt-5.6-terra", "gpt-5.6-terra"),
        ("openai/gpt-4o", "gpt-4o"),
        ("openrouter/anthropic/claude-3.5-sonnet", "anthropic/claude-3.5-sonnet"),
        ("fake/honest", "honest"),
        ("custom-local-model", "custom-local-model"),
    ],
)
async def test_reference_agent_strips_provider_prefix_for_all_providers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw_spec: str,
    expected_model_sent: str,
) -> None:
    """ReferenceAgent strips provider prefix before sending model name (G53a)."""
    from openai.types import CompletionUsage
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice

    from skeptic_agent.runner.adapters.reference import ReferenceAdapter

    sent_models: list[str] = []

    async def mock_create(**kwargs: Any) -> ChatCompletion:
        sent_models.append(kwargs["model"])
        msg = ChatCompletionMessage(role="assistant", content="Answer completed")
        return ChatCompletion(
            id="chat-strip",
            choices=[Choice(finish_reason="stop", index=0, message=msg)],
            created=1234567890,
            model=kwargs["model"],
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=5, prompt_tokens=10, total_tokens=15),
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)
    monkeypatch.setattr(
        "skeptic_agent.runner.reference_agent.create_llm_client",
        lambda *args, **kwargs: mock_client,
    )

    task = EpisodeTask(
        episode_id=f"test-strip-{expected_model_sent.replace('/', '-')}",
        prompt="hello",
        servers=[],
        model=raw_spec,
        max_steps=3,
        timeout_s=30,
        prompt_variant="plain",
        workdir=tmp_path,
        env={},
    )

    adapter = ReferenceAdapter()
    res = await adapter.run(task)
    assert res.final_answer == "Answer completed"
    assert sent_models == [expected_model_sent]


def test_models_yaml_compat_models_present() -> None:
    """bench/leaderboard/models.yaml contains deepseek-v4-pro and gpt-5.6-terra (G53a)."""
    repo_root = Path(__file__).resolve().parents[2]
    models_file = repo_root / "bench" / "leaderboard" / "models.yaml"
    data = yaml.safe_load(models_file.read_text(encoding="utf-8"))
    models_by_id = {m["id"]: m for m in data["models"]}

    assert "compat/deepseek-v4-pro" in models_by_id
    ds = models_by_id["compat/deepseek-v4-pro"]
    assert ds["tier"] == "dev"
    assert ds["supports_tools"] is True
    assert ds["price_in_per_mtok"] == 0.6
    assert ds["price_out_per_mtok"] == 2.4
    assert "conservative estimate, verify against 128api billing" in ds["notes"]

    assert "compat/gpt-5.6-terra" in models_by_id
    terra = models_by_id["compat/gpt-5.6-terra"]
    assert terra["tier"] == "mid"
    assert terra["supports_tools"] is True
    assert terra["price_in_per_mtok"] == 2.5
    assert terra["price_out_per_mtok"] == 10.0
    assert "conservative estimate, verify against 128api billing" in terra["notes"]

    assert "compat/hy3" in models_by_id
    hy3 = models_by_id["compat/hy3"]
    assert hy3["tier"] == "dev"
    assert hy3["supports_tools"] is True
    assert hy3["price_in_per_mtok"] == 0.0
    assert hy3["price_out_per_mtok"] == 0.0
