# CrewAI 适配器（`crewai`）

本文记录 CrewAI 适配器（`crewai`）的配置、版本、默认提示词和超时，对应 S13.2、S13.4、E44 和 ADR-0006。

## 1. 框架版本

- **包**：
  - `crewai`：`1.6.1`（锁在 `uv.lock`）
  - `mcpadapt`：`0.1.20`（锁在 `uv.lock`，按 ADR-0006）
- **导入**：
  - `from crewai import Agent, Task, Crew`
  - `from mcpadapt.core import MCPAdapt`
  - `from mcpadapt.crewai_adapter import CrewAIAdapter`
- **适配器 id**：`crewai`（`crewai:<模型>`）
- **接入结构**：
  - MCP 客户端：`MCPAdapt` 加 `CrewAIAdapter`。按 ADR-0006，不使用 `crewai-tools[mcp]`，也不使用 `pymupdf`。
  - 智能体与任务：`Agent(role="Assistant", goal="Complete the user's task", backstory="You are a helpful assistant.", llm=llm, tools=tools, max_iter=task.max_steps, verbose=False)`，以及 `Task(description=task.prompt, expected_output="Final answer to the user's task.", agent=agent)`。
  - 循环：`Crew(agents=[agent], tasks=[task_obj], verbose=False)`，用 `crew.kickoff()` 执行。

## 2. 默认系统提示词

按 S13.4，适配器使用框架默认构造、默认系统提示词和默认错误处理。

CrewAI 1.6.1 用角色扮演组件和 ReAct 片段（`crewai.utilities.prompts.Prompts`）拼系统提示词：

```python
system_template: str | None = None
prompt_template: str | None = None
response_template: str | None = None
use_system_prompt: bool = True
```

默认提示词规定 ReAct 循环（`Thought`、`Action`、`Action Input`、`Observation`、`Final Answer`）。适配器保持三个 template 为 `None`，不改框架默认的 ReAct 提示词。

## 3. 超时与生命周期

- **MCP 会话超时**：`client_session_timeout_seconds = 20.0`，加在 `MCPAdapt` 上，对应 S13.3 的单次工具 20 秒超时。
- **回合上限**：`max_iter = task.max_steps`。超出时，若 `iterations >= task.max_steps` 或 `steps > task.max_steps`，适配器返回空的 `final_answer`，结局为 `NO_ANSWER`。
- **墙钟超时**：由 `runner.episode.run_episode` 用 `asyncio.wait_for` 执行。
- **服务器生命周期**：`with MCPAdapt(...) as mcp_tools:`。结束或失败时 `MCPAdapt.close()` 停掉 stdio 子进程和辅助线程。
- **遥测**：用环境变量关掉交互式追踪和后台遥测：`OTEL_SDK_DISABLED=true`、`CREWAI_DISABLE_TELEMETRY=true`、`CREWAI_DISABLE_TRACKING=true`、`CREWAI_TESTING=true`。

## 4. 模型路由与计价

- `openrouter/<厂商>/<模型>`：`https://openrouter.ai/api/v1`，经 `OpenAICompletion`，使用 `OPENROUTER_API_KEY`。
- `openai/<模型>`：经 `OpenAICompletion`，使用 `OPENAI_API_KEY`。
- `compat/<模型>`：`SKEPTIC_COMPAT_BASE_URL` 和 `SKEPTIC_COMPAT_API_KEY`。
- `fake/<脚本>`：本地 FakeLLM，经 `SkepticCrewAILLM`，不访问网络。
