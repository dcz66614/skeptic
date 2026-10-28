# ADR-0006: CrewAI 可选依赖不带 AGPL

- 状态：采纳
- 日期：2026-10-28
- 提出者：T00fix　裁决者：R1/R0

## 背景

计划书 1.2 把可选依赖 `[crewai]` 定为 `crewai` 与 `crewai-tools[mcp]`。`uv lock` 解到 `crewai-tools` 1.6.1。该版本硬依赖 `pymupdf`（锁里为 2.0）。PyMuPDF 以 AGPL 授权。计划书 1.4 禁止 GPL/AGPL 依赖，以保持与 Apache-2.0 兼容。1.2 与 1.4 冲突。

## 选项

### A. 保留 `crewai-tools[mcp]`

优点：与计划书 1.2、S13.4 原文一致，E44 可直接使用 `crewai-tools` 的 `MCPServerAdapter`。
缺点：`pymupdf` 进入 `uv.lock`，违反 1.4。

### B. 去掉 `crewai-tools`，改为 `crewai` + `mcpadapt`

优点：`pymupdf` 不再出现在锁文件中，1.4 得到遵守。`crewai-tools[mcp]` 接 MCP 所用的包就是 `mcpadapt`，extra 仍保留这条依赖。
缺点：E44 的 CrewAI 适配器不能调用 `crewai-tools` 的 `MCPServerAdapter`，须自行用 `mcpadapt` 接通 MCP。

## 决定

采纳 B。`[project.optional-dependencies] crewai` 保留 `crewai`，加入 `mcpadapt`，删除 `crewai-tools[mcp]`。

## 影响

- 计划书 1.2：`[crewai]` 从 `crewai`、`crewai-tools[mcp]` 改为 `crewai`、`mcpadapt`。
- 计划书 S13.4：CrewAI 一行（`crewai-tools` 的 `MCPServerAdapter` + 单个 Agent 和 Task）不再作为依赖前提。
- E44：CrewAI 适配器必须在没有 `crewai-tools.MCPServerAdapter` 的情况下连接 MCP。
