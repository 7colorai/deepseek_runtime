# DeepSeek Runtime

> 用 DeepSeek API 做本地 Agent？你碰到的安全问题、多步推理、成本控制、断点续传——这个仓库帮你解决了。
>
> 一个开箱即用的 Python 运行时内核，fork 了就能用。

[English](README_en.md) | [简体中文](README.md)

***

## 你在用 DeepSeek API 做 Agent 吗？

如果你试过，大概率遇到过这些：

```
你：帮我读一下项目下的 src/main.py
Agent：好的，让我调用 read_file……等等，我找不到路径……
你：？？你不是在我电脑上吗？
```

核心问题在于：**调 API 和造一个可靠的本地 Agent 之间，有一道巨大的鸿沟。**

直接调 API 只需要一行代码：

```python
requests.post("https://api.deepseek.com/chat/completions", json={...})
```

但要想让这个 Agent 在你的电脑上**安全地**读文件、跑命令、记住状态、别翻车——你需要解决：

- 🔒 **安全性** —— Agent 可能执行危险命令（`rm -rf /` 怎么办？）
- 🧠 **多步推理** —— Agent 需要"思考→行动→观察"的循环，不是一问一答
- 📝 **证据记录** —— 怎么证明 Agent 调用了 API，又不泄露你的 API Key
- 💰 **成本控制** —— 花了多少 Token，缓存命中了多少，花的值不值
- 🔄 **断点续传** —— 中断了能从哪一步继续，而不是重头再来

这些问题 API 不负责解决。所以你需要一个 Runtime。

---

## DeepSeek Runtime 是什么

想象一下：你有一个超级聪明的助手（DeepSeek V4 大模型），但它住在 API 服务器里，不在你的电脑上。你想让它帮你读文件、搜代码、改项目——但它不能直接碰你的电脑。

**DeepSeek Runtime 就是给这个助手装上的"手和脚"**：

- **手**：能调用工具（读文件、执行命令）
- **脚**：能限制活动范围（只能在项目目录里行动）
- **大脑**：能记住做到哪一步了（会话状态）
- **嘴**：能安全地和 API 对话（证据记录，不泄露隐私）
- **安全员**：随时可以叫停危险操作（权限策略、回滚）

---

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/7colorai/deepseek_runtime.git
cd deepseek_runtime

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
python3 -m pip install -e .

# 体检（不需要 API Key）
deepseek-runtime doctor --json
```

有 API Key 了？直接跑：

```bash
export DEEPSEEK_API_KEY=sk-your-key-here

# 让 Agent 读文件、分析项目
deepseek-runtime run --workspace . "请描述这个项目的结构"
```

---

## 什么场景需要它

你不一定需要我，但如果你符合以下任意一条，**这个仓库就是为你写的**：

| 场景 | 为什么需要 Runtime |
|------|------------------|
| 你在 DeepSeek API 上做二次开发 | Runtime 帮你封装好安全、会话、证据——你只需要关心业务逻辑 |
| 你只想 fork 一个能用的 Agent 内核 | 全部 Python，可读性强，删减方便 |
| 你关注 Agent 的成本和安全性 | 内置 Token 统计、缓存分析、沙箱隔离、权限策略 |
| 你想学习 Agent 的系统架构 | 六层架构文件很少（每个文件 < 500 行），适合阅读和改造 |

---

## 六层架构总览

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

每层都是独立文件，代码量不大（每个文件 < 500 行），适合 fork 后按需增删。

---

## 设计思想

### 核心原则：把"模型能力"和"系统能力"分开

| 模型（DeepSeek API）负责 | Runtime（本仓库）负责 |
|------------------------|-------------------|
| 理解问题、生成回答 | 工具调度和执行 |
| 推理步骤规划 | 安全边界和权限控制 |
| 代码/文本生成 | 会话状态持久化 |
| 工具调用格式输出 | 通信证据安全记录 |
| 思考模式（thinking） | Token 用量统计和成本估算 |

### 每层回答一个关键问题

**第 0 层：证据层** → 怎么证明 Agent 真的调了 API，又不泄露隐私？
**第 1 层：客户端层** → 怎么优雅地跟 API 打交道（指纹、流式、错误处理）？
**第 2 层：会话层** → Agent 怎么记住它做到哪一步了？
**第 3 层：安全层** → Agent 想执行 `rm -rf /` 怎么办？（三层防护）
**第 4 层：运行时层** → 思考→行动→观察的循环怎么跑？
**第 5 层：可观测性** → 花了多少钱，花得值不值？

---

## 研究脉络

```
llm-harness-agent (理论研究 / 18 篇深度分析)
    ↓ 验证
deepseekagent (上层产品线 / 面向用户的完整产品)
    ↓ 提炼
deepseek_runtime (可复用的运行时内核)——← 你现在在看这个
```

- 理论研究 → [yuanchenglu/llm-harness-agent](https://github.com/yuanchenglu/llm-harness-agent)
- 上层产品 → [yuanchenglu/deepseekagent](https://github.com/yuanchenglu/deepseekagent)
- API 文档 → [api-docs.deepseek.com](https://api-docs.deepseek.com/)

---

## 文档目录

| 文档 | 内容 | 适合谁 |
|------|------|-------|
| [API 参考](docs/api.md) | 每个公开类和方法的详细说明 | 开发者 |
| [集成指南](docs/integration-guide.md) | 怎么把 Runtime 集成到自己的应用中 | 开发者 |
| [物理特性](docs/physical-traits.md) | DeepSeek V4 专有特性的支持矩阵 | 架构师 |
| [已知未知](docs/known-unknowns.md) | 当前版本已知的局限和未来验证计划 | 所有人 |
| [托管路线图](docs/hosting-roadmap.md) | 未来多租户服务的规划 | CEO/架构师 |
| [安全策略](SECURITY.md) | API Key 处理、证据处理、安全报告 | 所有人 |
| [故障排除](TROUBLESHOOTING.md) | 常见问题和解决方法 | 使用者 |

---

## 发布验证流程

```bash
# 单元测试
python3 -m unittest discover -s tests -v

# 本地体检
deepseek-runtime doctor --json

# 完整发布验证
python3 scripts/release_drill.py
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json

# 实时 API 验证
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json

# 发布门禁审计
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

---

## 许可

Apache-2.0。详见 [LICENSE](LICENSE)。

---

> ⭐ 如果这个仓库帮你省下了时间，点个 Star 让更多人看到。
>
> *有问题？开 Issue 讨论。想贡献？PR 欢迎。*
