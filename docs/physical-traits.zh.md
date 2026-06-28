# DeepSeek 物理特性矩阵

> ❓ **"物理特性"是什么意思？**  
> 💡 不是指芯片或服务器硬件，而是指 DeepSeek V4 模型作为一个"黑箱"所表现出的行为特征——比如它支持流式输出、它有 thinking（推理）模式、它会返回缓存 Token 统计数据等等。这个运行时列出了它**实际验证过**的特性，没验证的不算数。

---

## 支持的特性矩阵

❓ **我怎么知道运行时支持 DeepSeek 的哪些能力？**  
💡 看下表。每一行都是一个真实验证过的模型行为：

| 特性 | 运行时支持方式 | 证据来源 |
| --- | --- | --- |
| ✅ **OpenAI 兼容端点** | `RuntimeSettings` 默认指向 `https://api.deepseek.com`，`DeepSeekClient` 调用 `/chat/completions` | 官方文档 + 线上冒烟测试 |
| ✅ **V4 模型 ID** | 默认模型 `deepseek-v4-flash`，可改为 `deepseek-v4-pro` | 配置与诊断 |
| ✅ **Thinking（推理）模式** | Agent 循环自动发送 `thinking: {"type": "enabled"}`，线上冒烟已验证 | 请求证据记录了该字段 |
| ✅ **推理努力程度（reasoning effort）** | 线上冒烟使用 `DEEPSEEK_REASONING_EFFORT` 或 `high` | 请求证据记录了该字段 |
| ✅ **推理内容字段（reasoning_content）** | 响应证据**只记录字段是否存在、其哈希和字节数**，不记原始文本 | `response_evidence()` + 线上冒烟泄密检查 |
| ✅ **函数工具调用** | 运行时接收 DeepSeek 的函数调用并执行 `tool` 角色结果 | 单元测试 + Agent 循环 |
| ✅ **流式分块（streaming chunks）** | `chat_stream()` 解析 SSE 事件、delta 字段、终止原因、工具名、推理内容存在性 | Stream 证据 |
| ✅ **前缀/缓存 Token** | 诊断和可观测性解析 `prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`、`cache_hit_tokens`、`cache_miss_tokens`、`prompt_tokens_details.cached_tokens` | 可观测性测试 |
| ✅ **用量经济性** | 可观测性计算成功率、首次完成率、Token 总量、预估费用、每次成功成本 | 可观测性测试 |
| ✅ **脱敏发布证据** | CLI 和冒烟脚本默认写入指纹和结构证据 | 发布门禁审计 |
| ✅ **本地工作区安全** | 沙箱、权限策略、diff 预览、回滚、会话恢复作为运行时原语提供 | 安全测试 |

---

## 为什么这些细节重要？

❓ **其他框架不也支持 DeepSeek 吗？这有什么特别的？**  
💡 大多数提供商封装器（provider wrapper）只负责三件事：建连接、解析回复、可选的缓存统计。但一个**本地 Agent 运行时**需要更多：

1. **必须暴露推理模式决策**——开不开 thinking 直接改变质量、成本、延迟
2. **必须把 `reasoning_content` 挡在公开证据之外**——但还得能证明"这个字段存在"
3. **必须保工具循环语义**——本地的副作用（写文件、读代码）依赖于正确的调用顺序
4. **必须在同一个证据流里展示缓存和成本**——成功/失败的判断和钱的问题不能分开看
5. **必须提供沙箱和回滚原语**——因为本地 Agent 会真的动你的文件

🎯 一句话总结：**这个运行时不是"调一下 API 就完事"的封装器，而是为 Agent 安全、可控、可审计地运行而设计的底层内核。**

---

## 官方 API 参考

- [DeepSeek API 快速开始](https://api-docs.deepseek.com/)
- [创建聊天补全](https://api-docs.deepseek.com/api/create-chat-completion)

---

## 相关引用

- **Paper B1 — ReAct (ICLR 2023)**：工具循环语义（思考→行动→观察）正是 ReAct 范式的核心。这个运行时对函数工具调用的完整支持，本质上是 ReAct 在 DeepSeek 上的工程实现。
- **Paper A2 — AIOS (COLM 2025)**：AIOS 提出了 LLM 操作系统的概念，强调 LLM 调用需要和系统安全原语（沙箱、权限、文件回滚）深度集成——这正是本特性矩阵中"本地工作区安全"一栏的设计来源。
- **Paper A3 / A4**：关于 LLM 行为验证和特性覆盖的 systematic study，为本运行时"只列出已验证特性"的保守策略提供了方法论依据。
- **Paper C1**：关于 LLM 缓存机制和成本优化的研究，直接对应矩阵中的"前缀/缓存 Token"和"用量经济性"两行。
- **Paper B3 / B7**：关于流式处理和实时 Agent 行为的研究，为流式分块证据提供了理论基础。
