# 故障排除

> ❓ **刚上手就遇到问题，怎么办？**
> 💡 别急。下面整理了最常见的 5 个问题及其解决方法。大部分是配置或环境问题，几分钟内就能搞定。

---

## ❓ `DEEPSEEK_API_KEY is required`

**意思**：系统找不到你的 API Key。

**💡 解决方法：**

把 Key 设置到当前 shell 的环境变量中：

```bash
export DEEPSEEK_API_KEY=你的API密钥
```

⚠️ **重要：**
- 不要把这个命令写在脚本文件里（会泄露）
- 不要提交到 Git（会永远留在历史里）
- 每次打开新终端都要重新 export，或者写入 `~/.zshrc` / `~/.bashrc`

> 🧠 参考 [Agent Harness Survey（论文 A1）](https://github.com/yuanchenglu/llm-harness-agent) 中对敏感信息管理的建议：API Key 只存在于运行时内存中，不写入磁盘，这是 Agent 安全的第一条军规。

---

## ❓ `deepseek-runtime: command not found`

**意思**：你还没安装 DeepSeek Runtime，或者没有激活虚拟环境。

**💡 解决方法：**

用可编辑模式（editable mode）安装：

```bash
python3 -m venv .venv         # 创建虚拟环境
source .venv/bin/activate      # 激活它
python3 -m pip install -e .    # 安装 deepseek-runtime
deepseek-runtime doctor --json # 验证安装成功
```

安装完成后运行 `doctor --json`，如果看到 JSON 输出，就说明环境搭好了。

> 🧠 可编辑模式（`-e` 参数）的意思是：你对代码做的任何修改会立即生效，不需要重新安装——这对开发和调试非常有用，参考 [AgentBench（论文 B7）](https://github.com/yuanchenglu/llm-harness-agent) 中推荐的 Agent 开发工作流。

---

## ❓ Doctor 警告说 API Key 不存在

**意思**：运行 `doctor --json` 时，它提示你 API Key 没设置。

**💡 这不是错误，是预期行为。**

`doctor --json` 只做本地诊断——检查环境配置、项目结构、依赖版本等。它**不会**调用 DeepSeek 的远程 API，所以不需要 API Key。

如果你只是想确认安装和配置是否正确，这个警告可以放心忽略。

❓ **那如果我想测试真的 API 调用呢？**

💡 设置好 `DEEPSEEK_API_KEY` 后，用 `scripts/live_api_smoke.py` 做实网烟雾测试。

> 🧠 这和 [Coscientist（论文 E1，Nature 2023）](https://github.com/yuanchenglu/llm-harness-agent) 中的安全测试分层思路一致：先做离线诊断确认"环境本身没问题"，再做在线测试确认"与真实 API 的交互也没问题"。

---

## ❓ 烟雾测试（Live Smoke）返回 HTTP 错误

**意思**：`live_api_smoke.py` 尝试调用 DeepSeek API 但失败了。

**💡 逐一排查以下四项：**

| 检查项 | 正确值 / 操作 |
|--------|-------------|
| `DEEPSEEK_API_KEY` 是否存在且有效 | `echo $DEEPSEEK_API_KEY` — 确保已设置且没过期 |
| `DEEPSEEK_BASE_URL` 是否被意外改写过 | 确保没有指向第三方端点。如果不确定，取消设置这个变量 |
| `DEEPSEEK_MODEL` 是否正确 | 应该是 `deepseek-v4-flash` 或 `deepseek-v4-pro` |
| 账户余额或配额是否充足 | 登录 DeepSeek 官方平台检查 |

> 🧠 Agent 系统与外部 API 交互时的故障排查，[Agent Harness Survey（论文 A1）](https://github.com/yuanchenglu/llm-harness-agent) 将其归为「环境依赖错误」——这些错误通常不是代码 bug，而是执行环境的配置与预期不一致。按清单逐一排查是最有效的方法。

---

## ❓ 发布门禁（Release Gate）报告脱敏失败

**意思**：发布审计脚本检查到某些输出没有被正确脱敏。

**💡 分两步走：**

**第一步：清理旧制品，重新运行**

```bash
rm -f live-smoke.json release-drill.json release-gate-audit.json
python3 scripts/live_api_smoke.py --out live-smoke.json
python3 scripts/release_drill.py
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json
```

**第二步：如果仍然失败**

只查看「泄漏检查布尔值」（leak check booleans）——这些布尔值告诉你哪个检查点出了问题。**不要在公开渠道粘贴完整的实时响应内容。**

> 🧠 这体现了 [OpenHands（论文 C3）](https://github.com/yuanchenglu/llm-harness-agent) 中的「最小暴露原则」：排查问题时只暴露必要的信息量——用布尔值判断"是否有泄漏"，而不是直接查看"泄漏了什么内容"。这样既完成排查，又把安全风险降到最低。
