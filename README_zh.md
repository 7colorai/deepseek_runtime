# DeepSeek Runtime 技术架构总览

> **一句话总结**：DeepSeek Runtime 是一个"可被任何人 Fork 的 Python 运行时内核"，
> 用于在 DeepSeek 官方 API 之上构建本地 AI Agent。

[English](README.md) | [简体中文](README_zh.md)

---

## 📖 关于本文档

❓ **问：这份 README 和其他项目的 README 有什么不同？**

💡 **答：** 它不仅仅教你怎么装、怎么用。它更是一份**技术架构说明书**，逐层拆解 DeepSeek Runtime 的核心设计。

我会用**苏格拉底式**的问答来展开：先问一个你可能有的问题，再给出答案。如果你觉得某个问题太浅，直接跳过去；如果你觉得某个地方讲得不清楚，我写得就不够好。

---

## ❓ 到底什么是 DeepSeek Runtime？

💡 想象一下：你有一个超级聪明的助手（DeepSeek V4 大模型），但它住在 API 服务器里，不在你的电脑上。你想让它帮你读文件、搜代码、修改项目——但它不能直接碰你的电脑。

**DeepSeek Runtime 就是给这个助手装上的"手和脚"**：

- **手**：能调用工具（读文件、执行命令）
- **脚**：能限制活动范围（只能在项目目录里行动）
- **大脑**：能记住做到哪一步了（会话状态）
- **嘴**：能安全地和 API 对话（证据记录，不泄露隐私）
- **安全员**：随时可以叫停危险操作（权限策略、回滚）

---

## 🏗️ 项目背景：为什么需要 Runtime？

❓ **问：DeepSeek 已经提供了 API，为什么还要多一层 Runtime？**

💡 **答：** 因为"调用 API"和"构建可靠的 Agent"之间，有一道巨大的鸿沟。

调用 API 只需要做一件事：
```python
requests.post("https://api.deepseek.com/chat/completions", json={...})
```

但构建一个可靠的本地 Agent 需要解决很多问题：
1. 🔒 **安全性** —— Agent 可能执行危险命令，需要沙箱隔离
2. 🧠 **多步推理** —— Agent 需要"思考→行动→观察"的循环
3. 📝 **证据记录** —— 怎么证明 Agent 调用了 API，又不泄露隐私
4. 💰 **成本控制** —— 花了多少 token，缓存命中了多少
5. 🔄 **断点续传** —— 中断了能从哪一步继续

**这些问题，API 不负责解决，所以我们需要一个 Runtime。**

这正是 llm-harness-agent 论文数据库的核心论断，尤其是论文 **A1: Agent Harness Survey**：

> 「Agent 的可靠性不仅仅取决于模型，更取决于 Harness（执行框架）。
> Harness 层面的改进可以带来 10 倍的性能提升——哪怕不换模型。」

---

## 🎯 核心设计理念

DeepSeek Runtime 的设计围绕一个核心思想：

> **「把"模型能力"和"系统能力"分开」**

| 模型（DeepSeek API）负责 | Runtime（本仓库）负责 |
|---|---|
| 理解问题、生成回答 | 工具的调度和执行 |
| 推理步骤规划 | 安全边界和权限控制 |
| 代码/文本生成 | 会话状态的持久化 |
| 工具调用格式输出 | 通信证据的安全记录 |
| 思考模式（thinking） | Token 用量统计和成本估算 |

这个设计理念源自 llm-harness-agent 论文 **A2: AIOS (LLM Agent Operating System)** ——
把 LLM 当作"CPU"，把 Runtime 当作"操作系统"。

---

## 🏛️ 六层架构

下面这张图展示了 DeepSeek Runtime 的完整架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                    CLI 层 (cli.py)                                │
│             deepseek-runtime doctor / run                         │
├─────────────────────────────────────────────────────────────────┤
│               运行时层 (runtime.py)                                │
│           ReAct 循环：思考→行动→观察（最多 8 步）                 │
├─────────────────────────────────────────────────────────────────┤
│    会话层 (session.py)    │   安全层 (security.py)                │
│  SessionState / Store     │  Sandbox / Policy / ChangeManager    │
│  「短期记忆」              │  「围栏+权限+回滚」                    │
├──────────────────────────┴──────────────────────────────────────┤
│              客户端层 (client.py)                                 │
│     DeepSeekClient: HTTP 请求 + 指纹 + 流式解析                  │
├─────────────────────────────────────────────────────────────────┤
│  证据层 (evidence.py)   │  可观测性 (observability.py)          │
│  Hash / Redact / 指纹   │  Token / 缓存 / 成本汇总              │
├──────────────────────────┴──────────────────────────────────────┤
│           诊断层 (diagnostics.py)                                 │
│     本地健康检查：Python版本 / API Key / 存储可写性              │
└─────────────────────────────────────────────────────────────────┘
```

---

### 第0层：证据层 (evidence.py) —— 一切安全的基础

❓ **问：为什么「证据」是整个系统的基础？**

💡 **答：** 因为在"本地 Agent"这个场景里，你需要向别人证明"我真的调用了 API"，
但你**不能**把对话原文和 API Key 公之于众。

证据层提供了四个核心工具：

| 工具 | 作用 | 类比 |
|---|---|---|
| `sha256_bytes()` | 给任意数据生成唯一指纹 | 就像人的身份证号——看到号码就能确定身份，但看不到本人长相 |
| `wire_json()` | 稳定序列化 | 确保同样的数据每次都生成完全相同的字节序列 |
| `redact()` | 自动脱敏 | 就像自动打码机——把所有敏感字段替换成 [REDACTED] |
| `fingerprint()` | 一步生成完整指纹 | wire_json + sha256_bytes 的组合拳 |

**关键设计：reasoning_content 的安全红线**

DeepSeek V4/V3 的 API 响应可能包含 `reasoning_content`（模型的"内心独白"）。
证据层**只记录**它存在不存在、字节数、哈希值——**永远不会记录它的原文**。

> 这对应 llm-harness-agent 论文 B1 (ReAct) 和 physical-traits 文档中
> 的"Reasoning-content hygiene"（思考过程卫生规范）：
> 你可以证明思考发生过，但你不必（也不应该）记录思考的内容。

---

### 第1层：客户端层 (client.py) —— 怎么跟 API 打交道

❓ **问：为什么不能直接用 requests 库调 API，还需要一个客户端层？**

💡 **答：** 因为"调 API"不只是发 HTTP 请求——它还包括：

1. **自动合并配置**：模型名称、max_tokens 等参数不用每次调用都写
2. **请求指纹**：每次请求都计算 SHA-256 指纹，证明"这个请求确实是我发的"
3. **统一错误处理**：网络错误、HTTP 错误、JSON 解析错误，全部转成结构化的 `ProviderResult`
4. **流式解析**：解析 SSE（Server-Sent Events）协议，把流式数据组装成结构化证据
5. **依赖注入**：可以替换 HTTP 传输层（测试时用 Mock，无需真实网络）

**`ProviderResult` 就像快递包裹**：
- `status` = 物流状态（200=已送达，0=运输丢了）
- `body` = 包裹里的商品（API 返回的数据）
- `elapsed_ms` = 运输耗时
- `request_fingerprint` = 运单号（指纹）
- `error` = 运单备注（如果有问题）

> 参考 llm-harness-agent 论文 **C1: ToolLLM** 中的工具调用序列化设计和
> **A1** 中关于 Harness"执行循环"（Execution Loop）组件的定义。

---

### 第2层：会话层 (session.py) —— Agent 的短期记忆

❓ **问：Agent 怎么记住"它做到哪一步了"？**

💡 **答：** 通过 `SessionState`——它保存了 Agent 运行过程中的完整快照：

```
SessionState {
  session_id: "abc123...",       // 会话唯一ID
  step: 3,                        // 当前执行步骤
  messages: [...],                // 全部对话历史
  tool_calls: [                   // 所有工具调用记录
    {name: "read_file", status: "succeeded", ...},
    {name: "search", status: "pending", ...}
  ],
  usage: {total_tokens: 1024},   // Token用量
  evidence: [...]                 // 通信证据
}
```

❓ **问：什么是"断点续传"？**

💡 **答：** 想象一下，Agent 在执行第 4 步时断电了。
如果没有断点续传，你只能从头开始——第 1、2、3 步白白浪费了（而且它们可能有副作用）。

`resume_tool_calls()` 函数解决了这个问题：
- 遍历所有工具调用记录
- 状态为 `succeeded` 的→跳过（不重复执行）
- 状态为 `pending/failed` 的→重新执行

> 这对应 llm-harness-agent 论文 **B2: Generative Agents (UIST 2023)** 
> 中开创性的 Agent 记忆架构——Agent 的可信行为不取决于模型，
> 而取决于记忆和规划架构。以及论文 **B4: Reflexion** 
> 中的"反思→重试"机制。

---

### 第3层：安全层 (security.py) —— Agent 的活动围栏

❓ **问：如果 Agent 想执行 rm -rf / 怎么办？**

💡 **答：** 安全层有三个机制层层防护：

**机制一：WorkspaceSandbox（工作区沙箱）**

就像儿童玩的沙箱——你可以在沙箱里尽情玩，
但不能跑出沙箱的范围。

- `resolve()`：检查文件路径是否越界
- `classify_command()`：判断命令风险等级（网络命令？危险命令？Git 修改？）
- `run()`：在沙箱内执行命令（禁止字符串命令，防止注入攻击）

**机制二：PermissionPolicy（权限策略）**

三种决策：
- 🟢 `ALLOW` = 绿灯放行
- 🟡 `ASK` = 需要问用户
- 🔴 `DENY` = 直接拒绝

默认策略："除了只读操作，其他全部拒绝"。
通过 `PermissionRule` 可以逐步放宽限制。

**机制三：ChangeManager（变更管理器）**

支持三步曲：预览 diff → 应用修改 → 回滚撤销。

核心特性：
- **原子写入**：先写临时文件再重命名，写入崩溃不会留半成品
- **自动回滚**：如果多个文件中有任何一个写入失败，自动撤销所有已写入的
- **幂等回滚**：每个回滚令牌只能使用一次

> 参考 llm-harness-agent 论文 **C3: OpenHands** 的沙箱化执行环境和
> **A5** 中关于 Agent 治理（Governance）的讨论。

---

### 第4层：运行时层 (runtime.py) —— Agent 的决策轮盘

❓ **问：运行时层到底执行了什么循环？**

💡 **答：** 它实现了著名的 **ReAct** 循环——这是 llm-harness-agent 论文 **B1 (ICLR 2023)** 的核心贡献：

```
第1步：把用户消息 + 工具定义 → 发给 DeepSeek API
              │
              ▼
第2步：API 返回了什么？
      ├── 直接回复了文字 → 🎉 输出答案，结束！
      └── 想调用工具 → ⬇
              │
第3步：解析工具调用 → 在本地执行对应的工具函数
              │
              ▼
第4步：把工具结果 → 追加到对话历史 → 再次发给 API
              │
              ▼
      回到第2步（最多循环 8 次）
```

❓ **问：为什么最多 8 步？**

💡 **答：** AI 可能陷入"死循环"——不停地调用工具但不给出答案。
设置 8 步上限就像给生产线装一个安全阀门。

**运行时产出的 RuntimeResult 包含：**
- `ok`：成功还是失败
- `final_text`：AI 的最终答案
- `messages`：完整对话（用户+AI+工具 共十几条消息）
- `usage`：Token 总用量
- `evidence`：每一步的请求/响应证据
- `diagnostics`：运行时诊断

**"安全输出"的设计**：
- `to_safe_dict()` → 不包含原文，只有哈希和结构。适合日志、发布
- `to_dict(include_content=True)` → 包含原文。仅限本地可信调试

> 参考 llm-harness-agent 论文 **B1: ReAct**（ICLR 2023，11,000+ 引用）：
> 推理与行动交替的循环是现代 Agent 系统的理论基础。
> 以及 **A1** 中 Harness 六组件模型的"执行循环"（E）组件。

---

### 第5层：可观测性 (observability.py) —— 花了多少钱？快不快？

❓ **问：CEO 最关心什么？花的钱值不值。**

💡 **答： observability.py 回答的就是这个问题——**

每次 Agent 运行后，它可以给出：

| 指标 | 含义 | 为什么重要 |
|---|---|---|
| task_count | 做了多少个任务 | 了解工作量 |
| success_rate | 成功率 | 质量指标 |
| prompt_cache_hit_tokens | 缓存命中的 token 数 | 省钱的关键（缓存命中比未命中便宜 10 倍） |
| prompt_cache_miss_tokens | 缓存未命中的 token 数 | 需要优化的地方 |
| total_tokens | 总 token 数 | 总消耗 |
| estimated_cost_usd | 预估美元成本 | 钱花在哪 |
| cost_per_success_usd | 每次成功花费 | 成本效率 |

**缓存为什么重要？**
DeepSeek 的定价中，缓存命中输入（$0.014/M tokens）比缓存未命中输入（$0.14/M tokens）
便宜 10 倍。所以缓存命中率直接决定了你的运营成本。

> 参考 llm-harness-agent 论文 **D1: Memory Mechanism Survey** 和
> **A1** 中关于 Harness 可观测性组件（Observability）的讨论。

---

### 诊断层 (diagnostics.py) —— 系统体检报告

❓ **问：Agent 跑不起来怎么办？**

💡 **答：** 运行 `deepseek-runtime doctor --json`，它会检查：

1. ✅ Python 版本是否 ≥ 3.11
2. ✅ 工作区目录是否存在
3. ✅ Session 存储目录是否可写
4. ✅ deepseek-runtime CLI 命令是否可用
5. ⚠️ DEEPSEEK_API_KEY 环境变量是否设置
6. 💡 证据文件是否可读（可选）

**设计哲学：诊断不调用真实 API。**

即使没有 API Key，你也可以运行 doctor 来检查本地环境是否健康。
API Key 的问题会作为一个"警告"（warning）报告，而不是"错误"（error）。

---

## 🔗 研究脉络与论文引用

DeepSeek Runtime 是 llm-harness-agent 研究项目的**工程实现验证**。

研究脉络：

```
llm-harness-agent (理论研究)
    ↓ 验证
deepseekagent (上层产品线)
    ↓ 提炼
deepseek_runtime (可复用 Runtime 内核)——← 你现在在看这个
```

### 核心引用论文

本项目的设计和实现直接引用了以下论文（完整列表见 [llm-harness-agent 论文数据库](https://github.com/yuanchenglu/llm-harness-agent/blob/master/references/papers.md)）：

| 编号 | 论文 | 出处 | 在本项目中的体现 |
|---|---|---|---|
| **A1** | Agent Harness for LLM Agents: A Survey | Preprints 2026 | 六组件 Harness 模型：E(执行循环)在 runtime.py，T(工具注册)在 WorkspaceTools，S(状态存储)在 session.py |
| **A2** | AIOS: LLM Agent Operating System | COLM 2025 | OS 比喻：把 LLM 当 CPU，Runtime 当操作系统 |
| **B1** | ReAct: Synergizing Reasoning and Acting | ICLR 2023 | 运行时主循环（思考→行动→观察） |
| **B2** | Generative Agents: Interactive Simulacra | UIST 2023 | 会话记忆架构（SessionState） |
| **B3** | Toolformer: LMs Can Teach Themselves to Use Tools | NeurIPS 2023 | 工具调用协议（ToolHandler） |
| **B4** | Reflexion: Language Agents with Verbal RL | NeurIPS 2023 | 断点续传、失败重试、证据哈希验证 |
| **C1** | ToolLLM: Mastering 16000+ Real-world APIs | ICLR 2024 | 工具序列化格式、认证管理 |
| **C3** | OpenHands: Open Platform for AI SW Engineers | ICLR 2025 | 沙箱化执行环境 |
| **D1** | Survey on Memory Mechanism of LLM Agents | ACM TOIS 2025 | Token 管理和成本估算 |

---

## 🚀 快速安装

```bash
# 克隆仓库
git clone https://github.com/7colorai/deepseek_runtime.git
cd deepseek_runtime

# 创建虚拟环境（隔离依赖）
python3 -m venv .venv
source .venv/bin/activate

# 安装本包（可编辑模式）
python3 -m pip install -e .

# 运行体检（不需要 API Key）
deepseek-runtime doctor --json
```

## 🎬 快速运行

```bash
# 设置 API Key（从 DeepSeek 官网获取）
export DEEPSEEK_API_KEY=sk-your-key-here

# 运行 Agent
deepseek-runtime run --workspace . "请描述这个项目的结构"
```

默认输出是**安全模式**——只包含指纹、结构摘要、用量统计，不包含对话原文。

## 🔧 发布验证流程

```bash
# 1. 运行单元测试
python3 -m unittest discover -s tests -v

# 2. 本地体检
deepseek-runtime doctor --json

# 3. 完整发布验证（安全、可观测性、构建）
python3 scripts/release_drill.py
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json

# 4. 调用一次真实 API（验证可连通）
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json

# 5. 发布门禁审计
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

---

## 📚 文档目录

| 文档 | 内容 | 适合谁看 |
|---|---|---|
| [API 参考](docs/api.md) | 每个公开类和方法的详细说明 | 开发者 |
| [集成指南](docs/integration-guide.md) | 怎么把 Runtime 集成到自己的应用中 | 开发者 |
| [物理特性](docs/physical-traits.md) | DeepSeek V4 专有特性的支持矩阵 | 架构师 |
| [已知未知](docs/known-unknowns.md) | 当前版本已知的局限和未来的验证计划 | 所有人 |
| [托管路线图](docs/hosting-roadmap.md) | 未来多租户服务的规划 | CEO/架构师 |
| [安全策略](SECURITY.md) | API Key 处理、证据处理、安全报告 | 所有人 |
| [故障排除](TROUBLESHOOTING.md) | 常见问题和解决方法 | 使用者 |

---

## 📄 许可

Apache-2.0。详见 [LICENSE](LICENSE)。
