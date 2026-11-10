# LangGraph

The LangGraph adapter id is `langgraph`. An agent spec looks like `langgraph:fake/oracle_follower` or `langgraph:openrouter/<vendor>/<model>`.

Install the extra before using it:

```text
uv sync --extra langgraph
```

The adapter builds `langchain_mcp_adapters.client.MultiServerMCPClient` and `langgraph.prebuilt.create_react_agent`. It leaves the framework prompt at the default (`prompt=None`) and does not add a Skeptic system prompt. Timeouts, the recursion limit, and the FakeLLM route are recorded in the [LangGraph adapter note](../adapters/langgraph.md).

A one-scenario run with FakeLLM:

```text
uv run skeptic run --scenario bench/scenarios/weather/weather.forecast.paris-max.001.yaml --agent langgraph:fake/oracle_follower --profile none --seeds 1 --max-cost-usd 0.1 --out runs/langgraph-quickstart
```

The reference agent (`reference:fake/...`) does not need this extra. Use that spec when you want the quickstart path from a default install. The [quickstart](../quickstart.md) uses it.
