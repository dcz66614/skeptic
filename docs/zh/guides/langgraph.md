# LangGraph

LangGraph 适配器的 id 是 `langgraph`。智能体规格形如 `langgraph:fake/oracle_follower` 或 `langgraph:openrouter/<厂商>/<模型>`。

使用前先安装 extra：

```text
uv sync --extra langgraph
```

适配器构建 `langchain_mcp_adapters.client.MultiServerMCPClient` 和 `langgraph.prebuilt.create_react_agent`。框架提示词保持默认（`prompt=None`），不另加 Skeptic 的系统提示词。超时、递归上限和 FakeLLM 路由记在 [LangGraph 适配器说明](../adapters/langgraph.md)。

用 FakeLLM 跑一个场景：

```text
uv run skeptic run --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml --agent langgraph:fake/oracle_follower --profile none --seeds 1 --max-cost-usd 0.1 --out runs/langgraph-quickstart
```

参考智能体（`reference:fake/...`）不需要这个 extra。默认安装下走快速开始时用这个规格。[快速开始](../quickstart.md) 用的就是它。
