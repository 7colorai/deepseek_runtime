# 安全策略

> ❓ **本地运行的应用，还需要安全策略吗？**
> 💡 需要。DeepSeek Runtime 是本地优先的，但它依然提供了基础安全组件。正如 [Agent Harness Survey（论文 A1）](https://github.com/yuanchenglu/llm-harness-agent) 指出的，Agent 系统的安全不能只靠外部环境，运行框架本身也必须内置防护。

---

## 🔑 密钥处理 — 你的 API Key 就是钥匙

❓ **我把 API Key 放在哪里？**

💡 放对地方：
- ✅ 设置环境变量 `DEEPSEEK_API_KEY`
- ❌ **不要**放在：提示词里、命令行参数中、会话文件里、Git 提交历史中、公开 Issue 评论里

❓ **那不小心泄露了怎么办？**

💡 DeepSeek Runtime 自带「防手滑」措施：
- `doctor` 命令、发布脚本、实时烟雾测试的输出默认做了**脱敏处理**（redacted），关键信息会被自动遮蔽。
- 但请注意：`deepseek-runtime run --include-content` **是有意不安全的**——它会包含完整的提示词和响应原文。这个参数的名字就叫"include-content"，用它就意味着你主动选择暴露内容。

> 🧠 **背后的思路**：参考 [OpenHands（论文 C3）](https://github.com/yuanchenglu/llm-harness-agent) 对沙箱化执行环境的研究——安全的设计原则不是「完全锁死」，而是「默认安全，显式放开」。DeepSeek Runtime 也遵循这个原则：默认脱敏，只有你主动说"我就是要看原文"时才暴露。

---

## 📋 证据处理 — 发布时什么可以公开？

❓ **我要发布测试结果给团队看，哪些数据是安全的？**

💡 使用以下**安全接口**输出：
- `RuntimeResult.to_safe_dict()` — 安全的运行结果字典
- `deepseek-runtime doctor --json` — 诊断信息的 JSON 输出
- `scripts/live_api_smoke.py` — API 烟雾测试脚本
- `scripts/release_drill.py` — 发布演习脚本
- `scripts/release_gate_audit.py` — 发布门禁审计脚本

❓ **绝对不能公开什么？**

💡 以下内容**严禁发布**到公开渠道：
- 原始提供方（Provider）的响应体
- 原始会话检查点（session checkpoints）
- 任何包含 `reasoning_content` 的文件

> 🧠 **背后的思路**：参考 [AgentBench（论文 B7）](https://github.com/yuanchenglu/llm-harness-agent) 对 Agent 测试的实践——在评估 Agent 时，必须区分「可公开的评估指标」和「内部原始数据」。前者可以安全分享，后者可能包含敏感信息。

---

## 🛡️ 工作区安全 — 运行时做了哪些防护？

❓ **DeepSeek Runtime 会限制 AI Agent 的行为吗？**

💡 是的，通过两个核心机制：

| 组件 | 作用 | 类比 |
|------|------|------|
| `WorkspaceSandbox` | 阻止路径穿越攻击，确保 Agent 只能访问配置的工作区目录 | 给 Agent 画了一个「游乐场围栏」，它出不去 |
| `PermissionPolicy` | 对风险操作进行分类：拒绝、允许、或询问用户 | 像家长审核——"这个操作能不能做？"有三种答案 |

❓ **有这些就够了？**

💡 **不够。** 这是运行时的护栏（guardrail），不是完整的操作系统级沙箱。它不能替代：
- 操作系统沙箱（如 Docker、Firecracker、gVisor）
- 文件权限系统
- 人工审核流程

> 🧠 **背后的思路**：参考 [Coscientist（论文 E1，Nature 2023）](https://github.com/yuanchenglu/llm-harness-agent) 在现实场景中的 Agent 安全实践——真实世界中的 Agent 安全需要**多层防护**：运行时护栏管住"不该做的事"，底层沙箱管住"即使出事也不扩散"，人工审核管住"机器判断不了的事"。DeepSeek Runtime 的 `WorkspaceSandbox` 是**第一层**，不是最后一层。

---

## 🐞 报告问题

❓ **发现问题怎么反馈？**

💡 目前请在 GitHub 仓库提交 Issue：

👉 [https://github.com/7colorai/deepseek_runtime/issues](https://github.com/7colorai/deepseek_runtime/issues)

提交时请遵循本文的安全指引——不要附上 API Key、原始响应体内文或会话检查点数据。
