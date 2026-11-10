# 防护

防护是代理在工具调用或工具列表上执行的一步。它可以把坏结果变成显式错误，重试一次大声失败的读操作，拦住完全相同的重复调用，去掉像指令的文本，或在工具定义首次出现之后把它锁住。

八个防护，`G01`–`G08`。[防护参考](../reference/guards.md) 引用每个防护返回的原文。它们绕着故障钩子按固定顺序执行：死循环熔断和污点阻断发生在调用转发之前；Schema、过期和空值检查发生在返回途中，在重试之后。

三个预设：

| 预设 | 防护 |
|---|---|
| `none` | 不启用 |
| `all` | G01–G08 |
| `recommended` | G02–G08（`schema_guard`、`staleness_guard`、`emptiness_guard`、`retry_guard`、`loop_breaker`、`injection_shield`、`drift_lock`） |

`recommended` 不含 G01（`evidence_contract`），因为这个防护会在工具结果末尾追加文本。[防护对照](../methodology/guards-ab.md) 记录了把这组预设保留为暂定的消融：在已执行的运行里，没有单个防护达到入选规则，置信区间互相重叠。

传入预设名，或用逗号分开的名字：

```text
skeptic run --guards recommended ...
skeptic run --guards schema_guard,emptiness_guard ...
skeptic proxy stdio --guards recommended -- python -m skeptic_agent.sandboxes.sb_weather
```
