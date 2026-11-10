# 变更记录

仓库文件 `CHANGELOG.md` 的 `Unreleased` 一节：

- 增加中英双语文档站、文档工作流，以及用 FakeLLM 跑通的快速开始。
- 增加六个内置故障画像、`skeptic faults list` 命令，以及故障和画像的方法论文档。
- 增加故障引擎框架：调度、画像展开、JSONPath 辅助函数，以及在故障前置钩子之前分配的 call_index（ADR-0007）。
- 增加拦截管线，挂载点包括故障、防护和录制，以及带未完成调用和按工具调用计数的回合上下文。
- 从 HTTP 头或客户端第一条消息识别 MCP 协议时代（legacy、modern、unknown）。
- 增加 JSON-RPC 2.0 消息模型、按行分帧和规范化 JSON 哈希。
- 冻结 ADR 0001–0005，以及配置、卡带、画像、场景、结果、报告、findings、矩阵和模型的 Draft 2020-12 Schema。
- 搭建 `skeptic-agent` 包、CI 工作流和本地检查脚本。
- 从 `crewai` extra 去掉 AGPL 的 `crewai-tools`，保留 `crewai`，并加入 `mcpadapt`。
