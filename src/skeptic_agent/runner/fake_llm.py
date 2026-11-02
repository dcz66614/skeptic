"""FakeLLM local mock model for tests and deterministic evaluations (S13.5, E40).

Emulates an OpenAI chat completion client without network calls, driven either
by scripted yaml definitions or scenario oracle introspection.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fake_scripts"


class FakeChatCompletions:
    """Mock `chat.completions` API on FakeLLM."""

    def __init__(self, fake_llm: FakeLLM) -> None:
        self._fake_llm = fake_llm

    async def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        """Create a mock chat completion matching the requested script."""
        del kwargs
        return await self._fake_llm.generate(model=model, messages=messages, tools=tools)


class FakeChat:
    """Mock `chat` namespace on FakeLLM."""

    def __init__(self, fake_llm: FakeLLM) -> None:
        self.completions = FakeChatCompletions(fake_llm)


class FakeLLM:
    """OpenAI-compatible local fake model driven by scripts or scenario oracles (S13.5).

    Supported default scripts:
        - ``oracle_follower``: Executes oracle steps in order and emits final_answer.
        - ``gullible``: Quotes the first number found in the first tool result.
        - ``honest``: Yields 'RETRIEVAL_STATUS: FAILED' on bad tool data.
        - ``looper``: Keeps calling the same tool repeatedly.
    """

    def __init__(
        self,
        script_name: str,
        *,
        scenario: Any = None,
        fixtures_dir: Path | None = None,
    ) -> None:
        """Initialize FakeLLM.

        Args:
            script_name: Name of the script (e.g. 'oracle_follower').
            scenario: Optional Scenario object for dynamic scripts.
            fixtures_dir: Directory containing YAML fixture scripts.
        """
        self.script_name = script_name
        self.scenario = scenario
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR
        self.chat = FakeChat(self)
        self.call_count = 0
        self.script_data = self._load_script()

    def _load_script(self) -> dict[str, Any] | None:
        script_file = self.fixtures_dir / f"{self.script_name}.yaml"
        if script_file.is_file():
            try:
                data = yaml.safe_load(script_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    def _resolve_tool_function_name(
        self,
        target_name: str,
        available_tools: list[dict[str, Any]] | None,
    ) -> str:
        """Resolve short tool name into the prefixed tool name in available_tools."""
        if not available_tools:
            return target_name

        for t in available_tools:
            func = t.get("function", {})
            name = func.get("name", "")
            if isinstance(name, str) and (name == target_name or name.endswith(f"__{target_name}")):
                return name
        return target_name

    async def generate(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Generate one mock ChatCompletion turn."""
        self.call_count += 1
        turn_index = self.call_count - 1

        # Check explicit fixture turns first
        if self.script_data and "turns" in self.script_data:
            turns = self.script_data["turns"]
            if turn_index < len(turns):
                turn = turns[turn_index]
                return self._build_turn_completion(turn, tools=tools, model=model)

        # Dynamic behavior based on script_name
        if self.script_name == "oracle_follower":
            return self._generate_oracle_follower(messages=messages, tools=tools, model=model)

        if self.script_name == "gullible":
            return self._generate_gullible(messages=messages, tools=tools, model=model)

        if self.script_name == "honest":
            return self._generate_honest(messages=messages, tools=tools, model=model)

        if self.script_name == "looper":
            return self._generate_looper(messages=messages, tools=tools, model=model)

        # Fallback completion
        return self._make_text_completion("I have completed the task.", model=model)

    def _build_turn_completion(
        self,
        turn: dict[str, Any],
        *,
        tools: list[dict[str, Any]] | None,
        model: str,
    ) -> ChatCompletion:
        """Build completion from static script turn data."""
        if "tool_calls" in turn:
            tool_calls: list[Any] = []
            for i, tc in enumerate(turn["tool_calls"]):
                raw_name = tc.get("name", "")
                resolved_name = self._resolve_tool_function_name(raw_name, tools)
                args = tc.get("arguments", {})
                args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                tool_calls.append(
                    ChatCompletionMessageToolCall(
                        id=f"call_{self.call_count}_{i}",
                        type="function",
                        function=Function(name=resolved_name, arguments=args_str),
                    )
                )
            msg = ChatCompletionMessage(
                role="assistant",
                content=None,
                tool_calls=tool_calls,
            )
            return ChatCompletion(
                id=f"fake-{self.call_count}",
                choices=[Choice(finish_reason="tool_calls", index=0, message=msg)],
                created=1234567890,
                model=model,
                object="chat.completion",
                usage=CompletionUsage(completion_tokens=20, prompt_tokens=50, total_tokens=70),
            )

        content = str(turn.get("content", ""))
        return self._make_text_completion(content, model=model)

    def _generate_oracle_follower(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
    ) -> ChatCompletion:
        """Execute oracle steps from scenario.oracle."""
        if not self.scenario or not getattr(self.scenario, "oracle", None):
            return self._make_text_completion("No oracle scenario available.", model=model)

        oracle = self.scenario.oracle
        steps = getattr(oracle, "steps", [])
        tool_results_count = sum(1 for m in messages if m.get("role") == "tool")

        if tool_results_count < len(steps):
            step = steps[tool_results_count]
            call_name = step.call
            resolved_name = self._resolve_tool_function_name(call_name, tools)
            args_str = json.dumps(step.args or {})
            tool_call = ChatCompletionMessageToolCall(
                id=f"call_oracle_{tool_results_count + 1}",
                type="function",
                function=Function(name=resolved_name, arguments=args_str),
            )
            msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
            return ChatCompletion(
                id=f"fake-oracle-{self.call_count}",
                choices=[Choice(finish_reason="tool_calls", index=0, message=msg)],
                created=1234567890,
                model=model,
                object="chat.completion",
                usage=CompletionUsage(completion_tokens=25, prompt_tokens=60, total_tokens=85),
            )

        # Oracle steps finished -> emit final answer
        final_answer = getattr(oracle, "final_answer", "")
        # Check if evidence_contract variant is active
        evidence_contract = any(
            "RETRIEVAL_STATUS:" in str(m.get("content", ""))
            for m in messages
            if m.get("role") == "system"
        )
        answer = f"RETRIEVAL_STATUS: OK\n{final_answer}" if evidence_contract else str(final_answer)

        return self._make_text_completion(answer, model=model)

    def _generate_gullible(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
    ) -> ChatCompletion:
        """Call primary tool once, then extract first number from result."""
        tool_results = [m for m in messages if m.get("role") == "tool"]
        if not tool_results:
            # First turn: call primary tool
            target_tool = "primary"
            if self.scenario and getattr(self.scenario, "fault_targets", None):
                primaries = getattr(self.scenario.fault_targets, "primary", [])
                if primaries:
                    target_tool = primaries[0]
            resolved_name = self._resolve_tool_function_name(target_tool, tools)
            tool_call = ChatCompletionMessageToolCall(
                id="call_gullible_1",
                type="function",
                function=Function(name=resolved_name, arguments="{}"),
            )
            msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
            return ChatCompletion(
                id=f"fake-gullible-{self.call_count}",
                choices=[Choice(finish_reason="tool_calls", index=0, message=msg)],
                created=1234567890,
                model=model,
                object="chat.completion",
                usage=CompletionUsage(completion_tokens=20, prompt_tokens=40, total_tokens=60),
            )

        # Read first number from first tool result
        content = str(tool_results[0].get("content", ""))
        nums = re.findall(r"[-+]?\d*\.?\d+", content)
        answer = nums[0] if nums else "0.0"
        return self._make_text_completion(answer, model=model)

    def _generate_honest(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
    ) -> ChatCompletion:
        """Check tool result and report RETRIEVAL_STATUS: FAILED on error or empty."""
        tool_results = [m for m in messages if m.get("role") == "tool"]
        if not tool_results:
            target_tool = "primary"
            if self.scenario and getattr(self.scenario, "fault_targets", None):
                primaries = getattr(self.scenario.fault_targets, "primary", [])
                if primaries:
                    target_tool = primaries[0]
            resolved_name = self._resolve_tool_function_name(target_tool, tools)
            tool_call = ChatCompletionMessageToolCall(
                id="call_honest_1",
                type="function",
                function=Function(name=resolved_name, arguments="{}"),
            )
            msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
            return ChatCompletion(
                id=f"fake-honest-{self.call_count}",
                choices=[Choice(finish_reason="tool_calls", index=0, message=msg)],
                created=1234567890,
                model=model,
                object="chat.completion",
                usage=CompletionUsage(completion_tokens=20, prompt_tokens=40, total_tokens=60),
            )

        content = str(tool_results[0].get("content", "")).lower()
        if "error" in content or "empty" in content or not content.strip():
            answer = "RETRIEVAL_STATUS: FAILED Data is missing or corrupted."
        else:
            answer = "RETRIEVAL_STATUS: OK Results retrieved successfully."
        return self._make_text_completion(answer, model=model)

    def _generate_looper(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str,
    ) -> ChatCompletion:
        """Repeat identical tool call every step."""
        del messages
        target_tool = "primary"
        if self.scenario and getattr(self.scenario, "fault_targets", None):
            primaries = getattr(self.scenario.fault_targets, "primary", [])
            if primaries:
                target_tool = primaries[0]
        resolved_name = self._resolve_tool_function_name(target_tool, tools)
        tool_call = ChatCompletionMessageToolCall(
            id=f"call_loop_{self.call_count}",
            type="function",
            function=Function(name=resolved_name, arguments='{"city": "Paris"}'),
        )
        msg = ChatCompletionMessage(role="assistant", content=None, tool_calls=[tool_call])
        return ChatCompletion(
            id=f"fake-looper-{self.call_count}",
            choices=[Choice(finish_reason="tool_calls", index=0, message=msg)],
            created=1234567890,
            model=model,
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=20, prompt_tokens=40, total_tokens=60),
        )

    def _make_text_completion(self, content: str, model: str) -> ChatCompletion:
        msg = ChatCompletionMessage(role="assistant", content=content)
        return ChatCompletion(
            id=f"fake-{self.call_count}",
            choices=[Choice(finish_reason="stop", index=0, message=msg)],
            created=1234567890,
            model=model,
            object="chat.completion",
            usage=CompletionUsage(completion_tokens=15, prompt_tokens=30, total_tokens=45),
        )
