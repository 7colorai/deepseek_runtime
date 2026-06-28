# DeepSeek Runtime API 参考（v0.1.1a1）

> ❓ **这是谁看的文档？**  
> 💡 这份文档列出了 DeepSeek Runtime 对外公开的全部 API。凡是在这里找不到的，都是内部实现——你不应该依赖它们，它们也可能随时变化。

本指南面向两种读者：
- **应用开发者**：想知道怎么调用这个运行时
- **平台 PM / 技术决策者**：想理解每个 API 的能力边界和安全隐含

让我们从头讲起。

---

## 一、配置从哪来？—— `RuntimeSettings.from_env()`

❓ **为什么不用配置文件？**  
💡 因为 API Key 不应该出现在任何文件中。`from_env()` 从环境变量读取 DeepSeek 的配置，零配置启动。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | **必填** | 只有运行时知道它，从不写入日志 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 兼容 OpenAI 格式的基础地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 如果需要更强推理，换 `deepseek-v4-pro` |
| `DEEPSEEK_TIMEOUT` | `120` | 单位：秒 |
| `DEEPSEEK_MAX_TOKENS` | `512` | 请求本身不指定长度时的保底值 |

🔑 **核心思路**：把"谁调用、用哪个模型、多久超时"这些决策从代码里剥离出来放到环境变量中，这是 12-Factor App 的经典做法。

---

## 二、和 DeepSeek 对话——客户端 API

### `DeepSeekClient.chat(payload)`

❓ **这是做什么的？**  
💡 向 DeepSeek 发送一条聊天请求（`POST /chat/completions`），返回一个结构化的结果。

客户端会自动补全 `model` 和 `max_tokens`，你不需要每次都写。

返回的 `ProviderResult` 包含：

| 字段 | 含义 |
| --- | --- |
| `status` | HTTP 状态码；如果网络不通则为 `0` |
| `elapsed_ms` | 这次请求花了多少毫秒 |
| `body` | 解析后的 JSON 响应体。可能含原始内容，不要直接记日志 |
| `request_fingerprint` | 请求体的 sha256 指纹——用于取证核对 |
| `usage` | Token 用量（如果提供商返回了的话） |
| `request_id` | 提供商返回的请求 ID |
| `error` / `error_class` | 脱敏后的错误摘要 |

### `DeepSeekClient.chat_stream(payload)`

❓ **流式（streaming）和普通有什么区别？**  
💡 普通是一次性等全部结果；流式是一边生成一边推给你，实时感更强。这个方法在请求里加了 `stream: true`，返回的是流的结构证据——事件数量、首包延迟、delta 字段、终止原因、是否有推理内容、调用了哪些工具。

### `DeepSeekClient.models()`

简单调用 `GET /models`，返回当前可用的模型列表。

---

## 三、跑一个完整的 Agent 循环——`DeepSeekRuntime.run()`

这是整个运行时的核心。

```python
result = runtime.run(messages, workspace, tools=None)
```

❓ **它到底干了什么？**  
💡 它在运行一个有边界的 Agent 循环（bounded agent loop）：

1. 把消息发给 DeepSeek（thinking 模式已开启）
2. 记录请求/响应的结构证据（不记录原始文本）
3. 解析 DeepSeek 返回的函数调用
4. 在本地的 `tools` 字典里找到对应的函数执行
5. 把工具执行结果追加回消息，继续循环——直到拿到最终回复、提供商报错、返回格式异常、或达到最大步数

`tools` 是一个字典：函数名 → `Callable[[dict], str]`

返回的 `RuntimeResult` 有三个重要方法：

| 方法 | 用途 |
| --- | --- |
| `to_safe_dict()` | **给日志和外部展示用**。只包含哈希、字节数、证据、诊断、用量。 |
| `to_dict()` | 默认和上面一样安全 |
| `to_dict(include_content=True)` | **仅限本地可信流程**。会输出提示词和回复原文。 |

⚠️ 安全黄金法则：**日志里永远用 `to_safe_dict()`**，`include_content=True` 只用在你自己信任的本地应用里。

---

## 四、诊断工具——`build_diagnostics()`

❓ **出了问题怎么排查？**  
💡 调用 `build_diagnostics(workspace, evidence=None)` 生成一份脱敏的诊断包。它会检查：

- Python 版本
- 工作区是否存在
- Session 存储是否可写
- CLI 命令是否可用
- API Key 是否存在
- 可选的路径、缓存、用量、成本证据

相当于给运行时做一次"体检"。

---

## 五、可观测性——`summarize_observability()`

❓ **怎么知道我的 Agent 跑得好不好？**  
💡 `summarize_observability(data, pricing, source)` 从任务纬度总结：

- 模型路由
- 缓存命中/未命中 Token 数
- Token 总量
- 预估费用
- 成功率
- 首次完成率
- 每次成功的 Token 和成本

这让你能回答："这个 Agent 今天花了多少钱？效率怎么样？"

---

## 六、安全与状态管理

### `WorkspaceSandbox` — 工作区沙箱

❓ **Agent 能随便读写我的文件吗？**  
💡 不能。沙箱把所有文件操作限制在工作区根目录内，并对本地命令按风险分级。

### `PermissionPolicy` — 权限策略

❓ **每次操作都要弹窗确认？**  
💡 不一定。权限策略是一组有序规则，依次判断操作是 `allow`（允许）、`ask`（询问）还是 `deny`（拒绝），并记录脱敏审计事件。

相关类型：

| 类型 | 含义 |
| --- | --- |
| `Risk` | 风险分类：读、写、Shell、网络、Git 改写 |
| `Decision` | 判断结果：允许/询问/拒绝 |
| `PermissionRequest` | 一次权限请求 |
| `PermissionRule` | 一条有序规则 |

### `ChangeManager` — 变更管理器

❓ **Agent 改了文件能后悔吗？**  
💡 可以。ChangeManager 支持三步走：

1. **预览** `preview(change_set)` → 生成 unified diff，不写文件
2. **应用** `apply(change_set)` → 检查路径、哈希、权限后写入
3. **回滚** `rollback(token)` → 按 Token 恢复原始内容，一次有效

相关类型：

| 类型 | 含义 |
| --- | --- |
| `FileChange` | 一个文本文件变更（含路径、原始哈希、新内容） |
| `ChangeSet` | 一组变更，有稳定 ID |
| `RollbackToken` | 回滚凭证，`apply()` 返回 |
| `content_sha256(content)` | 计算内容的 SHA256 帮助函数 |

⚠️ 集成者的责任：ChangeManager 不做用户确认 UI——那是你的工作。调用 `apply()` 之前你得自己弹窗让用户点头。

### `SessionState` — 会话状态

存储可恢复的消息、工具调用、审批记录、变更集、用量和证据。

> ⚠️ 会话持久化文件**可能包含提示词和回复原文**（这是为了支持本地恢复）。**不要**把这些文件当作公开证据上传。

---

## 相关引用

本运行时 API 设计的理论来源：

- **Paper B1 — ReAct (ICLR 2023)**：`Runtime.run()` 的 Agent 循环本质上是 ReAct（推理+行动）模式的工程实现——先思考（thinking mode），再行动（工具调用），观察结果后继续推理。
- **Paper A2 — AIOS (COLM 2025)**：AIOS 提出的 LLM 操作系统架构启发了本运行时的"Runtime 内核 + 权限策略 + 会话管理"分层设计，让 LLM 调用和系统资源管理解耦。
- **Paper A1 — Agent Harness Survey**：这篇综述中对现有 Agent 框架 API 边界的研究，直接影响了本 API 的"公开 vs 内部"一刀切原则。
- **Paper D1**：关于 Agent 安全性的研究，为 `WorkspaceSandbox` 和 `PermissionPolicy` 的风险分级提供了理论支撑。
- **Paper E1 / E2**：关于 Agent 可观测性和成本分析的研究，为 `summarize_observability()` 的指标设计提供了参考。
