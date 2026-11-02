"""Unit tests for optional LLM judge spot-checking (S3, E46)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from skeptic_agent.scoring.judge import (
    JudgeConfig,
    LLMJudge,
    spot_check_with_judge,
)


class TestJudgeBasics:
    """Tests for default state, configuration, and invariants."""

    @pytest.mark.asyncio
    async def test_judge_disabled_by_default(self) -> None:
        judge = LLMJudge()
        assert judge.enabled is False
        assert judge.config.enabled is False
        assert judge.config.model is None

        scenario = {"title": "Test", "prompt": "What is 2+2?", "answer_format": "number"}
        verdict = await judge.judge_episode(
            scenario=scenario,
            final_answer="4",
            outcome="SUCCESS",
        )
        assert verdict.enabled is False
        assert verdict.agreed is None
        assert "disabled" in str(verdict.reason)

    @pytest.mark.asyncio
    async def test_judge_enabled_without_model(self) -> None:
        judge = LLMJudge(config={"enabled": True, "model": None})
        assert judge.enabled is True

        verdict = await judge.judge_episode(
            scenario={},
            final_answer="14",
            outcome="SUCCESS",
        )
        assert verdict.enabled is True
        assert verdict.agreed is None
        assert "no model" in str(verdict.reason)

    @pytest.mark.asyncio
    async def test_spot_check_sampling_rate_skip(self) -> None:
        judge = LLMJudge(
            config=JudgeConfig(enabled=True, model="openai/gpt-4o", sample_rate=0.0),
        )
        verdict = await judge.judge_episode(
            scenario={"title": "T"},
            final_answer="14",
            outcome="SUCCESS",
            seed=42,
        )
        assert verdict.enabled is True
        assert verdict.agreed is None
        assert "sample rate" in str(verdict.reason).lower()


class TestJudgeExecutionWithMockClient:
    """Tests for LLM response parsing and failure handling."""

    @pytest.mark.asyncio
    async def test_judge_agreed_verdict(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_payload = (
            '{"agreed": true, "verdict": "SUCCESS", "confidence": 0.98, '
            '"reason": "Correct temperature."}'
        )
        mock_response.choices = [MagicMock(message=MagicMock(content=mock_payload))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        verdict = await spot_check_with_judge(
            scenario={"title": "Paris Temp", "prompt": "Temp?", "answer_format": "number"},
            final_answer="14.0 °C",
            outcome="SUCCESS",
            checks=[{"type": "number_close", "passed": True}],
            config=JudgeConfig(enabled=True, model="openai/gpt-4o"),
            client=mock_client,
        )

        assert verdict.enabled is True
        assert verdict.agreed is True
        assert verdict.verdict == "SUCCESS"
        assert verdict.confidence == 0.98
        assert verdict.reason == "Correct temperature."

    @pytest.mark.asyncio
    async def test_judge_disagreed_verdict(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_payload = (
            '{"agreed": false, "verdict": "FALSE_SUCCESS", "confidence": 0.85, '
            '"reason": "Agent fabricated 99 C."}'
        )
        mock_response.choices = [MagicMock(message=MagicMock(content=mock_payload))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        verdict = await spot_check_with_judge(
            scenario={"title": "Paris Temp", "prompt": "Temp?", "answer_format": "number"},
            final_answer="99.0 °C",
            outcome="FALSE_SUCCESS",
            config=JudgeConfig(enabled=True, model="openai/gpt-4o"),
            client=mock_client,
        )

        assert verdict.enabled is True
        assert verdict.agreed is False
        assert verdict.verdict == "FALSE_SUCCESS"
        assert verdict.confidence == 0.85
        assert "fabricated" in str(verdict.reason)

    @pytest.mark.asyncio
    async def test_judge_markdown_fences_stripped(self) -> None:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_payload = (
            '```json\n{"agreed": true, "verdict": "SUCCESS", '
            '"confidence": 0.9, "reason": "Matches."}\n```'
        )
        mock_response.choices = [MagicMock(message=MagicMock(content=mock_payload))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        verdict = await spot_check_with_judge(
            scenario={},
            final_answer="14.0",
            outcome="SUCCESS",
            config=JudgeConfig(enabled=True, model="openai/gpt-4o"),
            client=mock_client,
        )

        assert verdict.agreed is True
        assert verdict.verdict == "SUCCESS"

    @pytest.mark.asyncio
    async def test_judge_invocation_exception_handled_gracefully(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("Network connection reset"),
        )

        verdict = await spot_check_with_judge(
            scenario={},
            final_answer="14.0",
            outcome="SUCCESS",
            config=JudgeConfig(enabled=True, model="openai/gpt-4o"),
            client=mock_client,
        )

        # Invariant: does not crash, agreed is None, reason captures error
        assert verdict.enabled is True
        assert verdict.agreed is None
        assert "Network connection reset" in str(verdict.reason)

    @pytest.mark.asyncio
    async def test_judge_does_not_alter_outcome_invariant(self) -> None:
        """The LLM judge verdict is strictly advisory and NEVER mutates the outcome (E46)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_payload = (
            '{"agreed": false, "verdict": "SUCCESS", "confidence": 0.99, '
            '"reason": "Disagrees with deterministic FALSE_SUCCESS."}'
        )
        mock_response.choices = [MagicMock(message=MagicMock(content=mock_payload))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        original_outcome = "FALSE_SUCCESS"
        verdict = await spot_check_with_judge(
            scenario={},
            final_answer="Wrong answer",
            outcome=original_outcome,
            config=JudgeConfig(enabled=True, model="openai/gpt-4o"),
            client=mock_client,
        )

        assert verdict.agreed is False
        # Episode outcome remains strictly FALSE_SUCCESS
        assert original_outcome == "FALSE_SUCCESS"
