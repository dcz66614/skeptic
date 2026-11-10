# Skeptic（较真）

对工具层做混沌测试，抓住相信坏数据的智能体。

Skeptic 是 MCP 工具调用的代理和评测。它记录流量，注入显式故障、静默故障和对抗故障，给智能体对结果的处理打分，也可以用防护改写工具输出。

包名是 `skeptic-agent`。命令是 `skeptic`。

## 从这里开始

- [快速开始](quickstart.md) 用 FakeLLM 跑一个场景。
- [概念](concepts/faults.md) 说明故障、防护和 Skeptic Score。
- [指南](guides/claude-code.md) 接入 Claude Code、Codex、Cursor、LangGraph 和 CI。
- [参考](reference/cli.md) 是命令行、配置文件、Schema、故障目录和防护。
- [方法论](methodology/faults.md) 记录故障目录、现实画像和防护对照实验。
- [榜单](leaderboard.md) 链接到智能体较真榜。
- [常见问题](faq.md)
- [变更记录](changelog.md)
