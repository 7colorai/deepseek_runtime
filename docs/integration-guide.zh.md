# 集成指南

> ❓ **这个运行时是干什么用的？**  
> 💡 把它想象成一个"Agent 引擎"——你可以把它嵌入到命令行工具、桌面应用、Web 工作台，或者另一个本地 Agent 里。这篇指南教你怎么做。

---

## 一、最简集成（3 行代码就够了）

❓ **我想最快跑起来，最少的代码要怎么写？**  
💡 三步走：配环境、建运行时、跑。

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings

runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
result = runtime.run(
    [{"role": "user", "content": "用一段话解释这个仓库是干什么的。"}],
    workspace=".",
)

if result.ok:
    print(result.final_text)
else:
    print(result.error_class, result.error)
```

**发生了什么？**
1. `RuntimeSettings.from_env()` 从环境变量读 API Key 和模型配置
2. `DeepSeekRuntime(DeepSeekClient(...))` 组装好运行时
3. `runtime.run()` 发消息给 DeepSeek，等回复
4. 检查 `result.ok`，成功了打印最终回答，失败打印错误

📌 就这么简单。但你很快会发现：没有工具（tools），Agent 只能聊天，不能做事。

---

## 二、加上工具——让 Agent 能干实事

❓ **怎么让 Agent 能搜索文件、读代码？**  
💡 给它工具。

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools

runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
tools = WorkspaceTools(".").catalog()

result = runtime.run(
    [{"role": "user", "content": "搜索 RuntimeSettings 并总结它。"}],
    workspace=".",
    tools=tools,
)
```

内置的 `WorkspaceTools` 暴露了：
- `read_file` — 读文件
- `search` — 全文搜索

⚠️ **生产环境警告**：示例里的工具是开箱即用的"样板"，**生产环境一定要用自己的审批和权限策略包一层**，不能让它直接执行有副作用的操作。可以参考 [API 参考](api.zh.md) 中的 `PermissionPolicy` 和 `ChangeManager`。

---

## 三、证据边界——什么可以对外说，什么不能

❓ **我想在 UI 或日志里展示结果，怎么保证安全？**  
💡 记住一条黄金法则：**外部用安全格式，内部用完整格式。**

| 场景 | 用哪个 | 说明 |
| --- | --- | --- |
| UI 展示 / 公开日志 | `result.to_safe_dict()` | 只有元数据，没有原始文本 |
| 可信本地应用 | `result.final_text` 或 `result.to_dict(include_content=True)` | 包含原始回复 |

**绝对不要公开暴露的东西：**
- ❌ 原始提示词（prompt text）
- ❌ 原始回复文本（response text）
- ❌ API Key（永远不会出现在结果里，但你的代码里别乱打日志）
- ❌ `reasoning_content`（模型的"内心独白"）
- ❌ 包含私密消息的会话检查点

💡 用 `to_safe_dict()` 就像给你的数据穿了一件安全服——该有的结构信息都有，但敏感内容全被脱敏了。

---

## 四、推荐 UI 映射——字段怎么展示

❓ **我在做界面，每个字段对应什么 UI 组件？**  
💡 下表给了你一个可以直接用的映射：

| 运行时字段 | UI 用途 |
| --- | --- |
| `ok` | 最终状态指示器（成功/失败图标） |
| `final_text` | 主要回答区（仅限可信本地 UI） |
| `usage` | Token 计数器和预算视图 |
| `evidence[].request_fingerprint` | 调试用的请求副本 ID |
| `evidence[].request_evidence` | 请求结构检查器（开发者工具） |
| `evidence[].response_evidence` | 响应结构检查器（开发者工具） |
| `diagnostics` | 诊断面板（"医生"页面） |
| `error_class` / `error` | 错误横幅 |

---

## 五、发布集成——上线前跑一下这套流程

❓ **我准备基于这个运行时做产品了，发布前要做什么检查？**  
💡 跑下面这套标准化发布流水线：

```bash
# 1. 跑单元测试
python3 -m unittest discover -s tests -v

# 2. 运行诊断
deepseek-runtime doctor --json

# 3. 执行发布演练（检查所有核心功能）
python3 scripts/release_drill.py

# 4. 构建发布产物
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json

# 5. 线上真实 API 冒烟测试（需要有效 API Key）
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json

# 6. 发布门禁审计（汇总前面所有结果，判断是否可以发布）
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

📌 **关于托管服务**：当前版本（`0.1.1a1`）专注于本地运行时内核，不包含托管服务。托管路径详见[托管路线图](hosting-roadmap.zh.md)。

---

## 相关引用

- **Paper B1 — ReAct (ICLR 2023)**：`runtime.run()` 的工具循环机制直接实现了 ReAct 的"推理→行动→观察"范式。集成者可以通过 `tools` 参数注入任意本地行动，Agent 会自动调用并在上下文中观察结果。
- **Paper A2 — AIOS (COLM 2025)**：AIOS 提出的"LLM + OS"分层架构体现在本指南的"证据边界"和"安全工具包装"建议中——运行时内核不做 UI 层的安全决策，但提供原语让集成层构建自己的策略。
- **Paper A1 — Agent Harness Survey**：这篇综述系统地比较了各种 Agent 框架的集成复杂度，本指南的"最简集成→工具集成→安全边界→UI 映射"渐进式结构正是受其启发，让开发者从零到一逐步理解。
- **Paper C1 / C3**：关于 Agent 成本监控和发布工程的研究，为"发布集成"一节中的标准化审计流程提供了参考。
- **Paper D1 / E1**：关于 Agent 安全审计和可观测性的研究，影响了"证据边界"中的脱敏策略和 UI 映射设计。
