# 常见问题

## 什么是静默故障？

工具结果看起来仍然成功。`isError` 缺省或为 false，内容块的类型也不变，但数值被清空、改旧、放大，或者以别的方式错了。把这些值原样说出来、却没有察觉的智能体，就是 Skeptic 要抓住的情况。三类故障见[故障](concepts/faults.md)页。

## 没有 API 密钥怎么打分？

用 FakeLLM。[快速开始](quickstart.md) 用 `reference:fake/oracle_follower` 跑一个天气场景。另外三个本地脚本是 `fake/gullible`、`fake/honest` 和 `fake/looper`。

## 可以指向哪些服务器？

Skeptic 自带的沙箱，以及你写进 `skeptic.yaml`、由你自己运营的 MCP 服务器。它不是用来对别人的服务做故障注入的工具。对抗故障的载荷使用保留域名 `.example`。

## 同一个智能体两次运行结果不一样，怎么办？

真实模型本身有随机性。用多个种子比较，并阅读 SKS 的置信区间。区间重叠时，榜单上是同一个名次组。

## 退出码 10 是什么意思？

`skeptic gate` 拒绝了这次运行。Skeptic Score 低于 `--min-sks`，或谎报成功率高于 `--max-fsr`，或注入服从率高于 `--max-icr`。其余退出码在[命令行参考](reference/cli.md)。
