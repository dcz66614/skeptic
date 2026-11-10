# 故障

Skeptic 每个回合注入一种故障。故障画像决定跑哪些。干净画像 `none` 不注入，用作基线。

三类：

- **显式故障**（`L01`–`L07`）。客户端看到错误、超时、工具消失或参数结构被改。失败是看得见的。
- **静默故障**（`S01`–`S10`）。`isError` 缺省或为 false，内容块的类型不变。数据被清空、截断、改旧、放大、换单位、遮蔽、弄坏格式，或者写操作报了成功却什么都没改。
- **对抗故障**（`A01`–`A03`）。一句固定的测试指令被放进工具输出或工具描述。只有智能体去执行工具数据里夹带的指令时，它才起作用。载荷只用保留域名 `.example` 和虚构的 canary 文件。

故障无法施加时（没有日期可移、没有数字可缩放）记为不适用，不进入任何指标的分母。

[故障目录](../reference/faults.md) 列出每个 id、默认持续方式和正确智能体应有的行为。参数级算法和文献对应在[故障说明](../methodology/faults.md)。内置画像，包括按权重抽样的 `realistic-2026`，写在那些说明和[现实画像](../methodology/realistic-profile.md)页上。

```text
skeptic faults list
skeptic faults list --class silent
skeptic run --profile silent-core ...
```
