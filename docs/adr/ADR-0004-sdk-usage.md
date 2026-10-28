# ADR-0004: MCP Python SDK 的用法

- 状态：采纳
- 日期：2026-10-28
- 提出者：T02　裁决者：R1

## 背景

S9.1 第 1 条要求沙箱使用官方 MCP Python SDK 的高层服务器 API。计划书提到 v1 的装饰器式 `FastMCP` 在 v2 可能改名，以已安装版本为准。S13.3 要求参考智能体使用 SDK v2 客户端，版本协商为 `auto`。S14.3 的 `skeptic mcp serve` 也用 SDK 实现。

`uv.lock` 锁定 `mcp` 2.3.0（要求 `>=2.0,<3`）。已安装包路径为 `.venv/Lib/site-packages/mcp`。包内没有单独的 README 文件；`mcp-2.3.0.dist-info/METADATA` 的文档地址是 `https://py.sdk.modelcontextprotocol.io/`。

实测：`import mcp.server.fastmcp` 抛出 `ModuleNotFoundError`，消息写明 FastMCP 已改名为 `MCPServer`，导入路径是 `mcp.server.mcpserver`。`mcp/server/fastmcp.py` 只有这段错误，没有可用 API。

## 选项（至少 2 个，各写优缺点）

### A. 使用已安装的 2.3.0 高层 API：`MCPServer` 与 `Client`

优点：和锁文件、S9.1、S13.3 的“以已安装版本为准”一致。`Client.mode` 的默认值就是 `"auto"`。stdio 与 Streamable HTTP 都由 `MCPServer.run` 提供。
缺点：计划书里写的 `FastMCP` 这个名字不能再导入。S30 和参考智能体必须按本 ADR 的名字写。

### B. 把依赖钉到 `mcp<2`，继续用 `FastMCP`

优点：和 v1 教程里的类名一致。
缺点：违反已锁定的 `mcp>=2.0,<3`，也违反 D4“不得降级”。`FastMCP` 在 2.3.0 里是故意失败的模块。

## 决定

采纳 A。沙箱和 `skeptic mcp serve` 使用高层服务器。参考智能体和测试客户端使用高层客户端。不降级 SDK。

服务器：

- 类：`mcp.server.mcpserver.MCPServer`。`mcp.server` 也导出 `MCPServer`。
- 注册工具的装饰器是 `MCPServer.tool`。同文件还有 `resource`、`prompt`、`add_tool`。`tool` 的参数包括 `name`、`description`、`annotations`、`structured_output`。必须写成 `@server.tool()`，不能写成 `@server.tool`。
- 启动：`run(transport="stdio")` 为默认。HTTP 为 `run(transport="streamable-http", host=..., port=...)`。异步入口是 `run_stdio_async` 和 `run_streamable_http_async`。`streamable_http_path` 默认 `"/mcp"`，与 S4 的 `POST {listen}/mcp` 一致。`run` 还接受 `"sse"`，沙箱的 `--http` 走 `streamable-http`，不走旧的 SSE 传输。
- 低层类 `mcp.server.lowlevel.Server` 仍在包里。沙箱和 `skeptic mcp serve` 不直接用它。

客户端：

- 类：`mcp.Client`，定义在 `mcp.client.client.Client`，由 `mcp` 和 `mcp.client` 导出。文档字符串称它为 high-level MCP client。
- 用法：`async with Client(server) as client`。`server` 可以是 URL 字符串、`StdioServerParameters`、Transport，或进程内的 `MCPServer`。
- `mode` 默认 `"auto"`：先探测 `server/discover`，旧服务器再回退到 initialize。这就是 S13.3 的自动协商。测试需要固定 2025 代时传 `mode="legacy"`。
- 工具调用用 `await client.call_tool(name, arguments)`。列工具用 `await client.list_tools()`。
- `mcp.ClientSession` 和 `mcp.stdio_client` 仍导出。参考智能体走 `Client`，不手写 session。

S30 的 `make_server` 返回 `MCPServer`。工具的 `inputSchema` 来自类型注解，`outputSchema` 来自返回值上的 Pydantic 模型或 TypedDict（`structured_output` 在返回类型可结构化时由 SDK 生成）。若 SDK 的默认文本块不是 `json.dumps(structured, ensure_ascii=False, sort_keys=True)`，在 `sb_common` 里包装，不改调用方的工具函数签名。

## 影响（需要修改的规格条目、代码、文档）

- S9.1、S13.3、S14.3 里的“FastMCP”按本 ADR 读成 `MCPServer`，客户端读成 `mcp.Client`。
- S30、P13 的 echo 夹具、E41 的参考智能体按上述导入路径实现。
- 依赖保持 `mcp>=2.0,<3`，锁文件版本 2.3.0。
