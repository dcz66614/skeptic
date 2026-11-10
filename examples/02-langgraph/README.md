# Minimal LangGraph Agent with Skeptic Testing

This example demonstrates how to evaluate the tool-layer reliability of a minimal [LangGraph](https://github.com/langchain-ai/langgraph) agent using **Skeptic** and FakeLLM.

---

## 1. Overview

LangGraph agents typically execute a **ReAct** (Reason + Act) loop:
1. The language model issues one or more tool calls based on user input.
2. The agent executes the tools and passes the returned output back to the model.
3. The model reviews the tool outputs and generates a final response.

**The Reliability Problem**:
In production, tools may experience transient failures, silent data corruption (e.g. inverted dates, unit mismatches), schema violations, or rate limits. Without rigorous fault testing, agents frequently trust corrupted data as fact, hallucinate, or loop endlessly.

Skeptic tests LangGraph agents by sitting between the agent and upstream tools, injecting faults according to standardized profiles, and scoring resilience (SKS, FSR, ICR).

---

## 2. Workspace Files

- **`agent.py`**: Minimal LangGraph ReAct agent constructed via `create_react_agent`. Supports offline execution with FakeLLM as well as live OpenAI endpoints.
- **`skeptic.yaml`**: Skeptic configuration specifying the weather sandbox (`sb_weather`), recording directory, and quality gate thresholds (min SKS 70, max FSR 10%).
- **`run.py`**: Runnable test script demonstrating the complete Skeptic evaluation workflow.
- **`workflow.yml`**: GitHub Actions workflow running the example in CI.

---

## 3. Running the Agent Standalone

You can run `agent.py` directly to see the agent execute offline using FakeLLM (no API keys required):

```bash
uv run python examples/02-langgraph/agent.py
```

Output:
```text
======================================================================
Minimal LangGraph ReAct Agent (Offline FakeLLM Mode)
======================================================================

User Prompt: What is the maximum temperature in Paris today? Answer with just the number.

Agent Execution Trace:
  [1] HUMAN: What is the maximum temperature in Paris today? Answer with just the number.
  [2] AI Tool Calls: [{'name': 'sb_weather__get_forecast', 'args': {'city': 'Paris', 'date': '2026-11-02'}, 'id': 'call_oracle_1', 'type': 'tool_call'}]
  [3] TOOL: 14.5
  [4] AI: 14.5

Final Answer: 14.5
======================================================================
```

---

## 4. Running the Skeptic Evaluation Suite

The included `run.py` script executes 5 evaluation phases:

1. **Direct Agent Execution**: Verifies that the LangGraph agent runs and completes a multi-turn ReAct cycle.
2. **Clean Baseline Run**: Evaluates `weather.forecast.paris-max.001` with `profile: none` using `skeptic run`. Asserts that the agent achieves `SUCCESS` with SKS = 100.
3. **Fault Injection Run**: Injects the `silent-core` fault profile to test how the agent behaves under corrupted tool outputs.
4. **Report Generation**: Runs `skeptic report` to compile Markdown (`report.md`), HTML, and SARIF summaries.
5. **Quality Gate Enforcement**: Runs `skeptic gate` with a passing threshold (`--min-sks 70`, exit code 0) and verifies failure on an unreachable threshold (`--min-sks 101`, exit code 10).

```bash
uv run python examples/02-langgraph/run.py
```

---

## 5. Running via Skeptic CLI

You can also run the evaluation directly through the `skeptic` CLI using the `langgraph` adapter:

```bash
# Clean baseline evaluation
skeptic run \
  --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml \
  --agent langgraph:fake/oracle_follower \
  --profile none \
  --out runs/langgraph-clean

# Fault evaluation under silent data corruption
skeptic run \
  --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml \
  --agent langgraph:fake/oracle_follower \
  --profile silent-core \
  --out runs/langgraph-fault

# Generate human-readable reports
skeptic report runs/langgraph-clean

# Quality gate check
skeptic gate runs/langgraph-clean --min-sks 70
```

---

## 6. 示例说明

本示例展示了最小 LangGraph ReAct 智能体在 Skeptic 混沌测试下的验证流程：

1. **最小智能体实现** (`agent.py`)：使用 `langgraph.prebuilt.create_react_agent` 构建最小 ReAct 图，内置天气工具并支持 FakeLLM 离线运行。
2. **Skeptic 适配器对接**：Skeptic 内置的 `langgraph` 框架适配器（S13.4, E43）通过 `langchain-mcp-adapters` 原生对接 stdio MCP 沙箱，无需修改智能体源码。
3. **完整评测生命周期** (`run.py`)：
   - 离线 FakeLLM 执行验证。
   - `none` 画像基线跑通（SKS = 100，结局 `SUCCESS`）。
   - `silent-core` 静默故障注入与录制。
   - 自动生成报告（Markdown / HTML / SARIF）。
   - 质量门禁断言（阈值 70 通过返回 0，阈值 101 失败返回 10）。
