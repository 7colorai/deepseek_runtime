# CLI Agent Loop 使用说明（简体中文 + 苏格拉底式注释）
# =============================================================================
# ❓ 问：这个文件是干什么用的？
# 💡 答：这是一个 Markdown 格式的说明文档，演示如何通过命令行（CLI）使用
#    DeepSeek Runtime 的 Agent 循环功能。用户可以像聊天一样在终端中输入
#    自然语言指令，Agent 会自动调用工作区工具来完成任务。
#
# 论文引用：llm-harness-agent 论文 B1: ReAct — CLI 是 Agent 系统与人类用户交互的
# 最基本的"界面"之一，用户通过命令行触发 Agent 的"思考-行动-观察"循环。
# 参考 A1: Agent Harness Survey — CLI 工具的易用性和安全性是评估 Agent 框架
# 成熟度的重要指标。
# 参考 B7: AgentBench — Agent 在命令行环境中执行任务的能力是其基准测试的重要内容。
# =============================================================================

# # CLI Agent Loop Example（CLI Agent 循环示例）
# ❓ 问：标题中的 "CLI Agent Loop" 是什么意思？
# 💡 答：CLI（Command-Line Interface，命令行界面）Agent Loop（Agent 循环）
#    指的是在终端中启动一个 AI Agent，它会自动执行一个"思考→行动→观察→再思考"
#    的循环来处理用户的任务。你不需要写代码，只需要在终端输入一条命令即可。

# Run a prompt with workspace tools:
# ❓ 问：这句话在说什么？
# 💡 答："运行一个带有工作区工具的提示词"——意思是你可以用一条命令让 Agent
#    使用各种工具（读文件、搜索代码、分析内容等）来完成你的请求。
#    论文参考 B1: ReAct — 这里的"提示词"就是触发 ReAct 循环的初始输入。

# ```bash
# export DEEPSEEK_API_KEY=...
# deepseek-runtime run --workspace . "Search for RuntimeSettings and summarize how configuration works."
# ```
# ❓ 问：这两条命令分别做什么？
# 💡 答：
#    第一条命令 export DEEPSEEK_API_KEY=...
#    export 是 Unix/Linux 中设置环境变量的命令。这里设置了 DEEPSEEK_API_KEY
#    环境变量，它存储着你访问 DeepSeek AI 模型的密钥。你需要把 ... 替换成
#    你自己的 API 密钥（可以在 DeepSeek 官网申请）。
#    这条命令只需运行一次（或在 .bashrc/.zshrc 中配置），每次新开终端时都有效。
#
#    第二条命令 deepseek-runtime run --workspace . "Search for..."
#    这是启动 Agent 的核心命令。逐个解析：
#    - deepseek-runtime: DeepSeek Runtime 的命令行工具名称
#    - run: 子命令，告诉工具你要启动一个 Agent 运行
#    - --workspace .: 指定工作区为当前目录（.），Agent 只能在这个目录中操作文件
#    - "Search for...": 用引号包裹的完整自然语言指令，这就是你给 Agent 的任务
#    整句话的意思是："启动一个 Agent，让它在当前目录下查找 RuntimeSettings
#     的相关信息，然后用通俗的语言总结配置是怎么工作的。"
#    论文参考 B7: AgentBench — 这种"自然语言→命令行→Agent 执行"的流程是
#    Agent 系统人机交互的标准模式。

# Default output is safe for logs and does not include prompt or response text.
# ❓ 问：为什么默认输出适合写入日志？
# 💡 答：这是 DeepSeek Runtime 的安全设计。默认情况下，Agent 的输出
#    经过了"脱敏处理"——它不会包含你输入的问题（prompt）和 AI 的完整回答
#    （response text）中的敏感内容。这样你可以放心把输出保存到日志文件中，
#    不用担心泄露商业机密或个人隐私。
#    论文参考 A1: Agent Harness Survey — 默认安全（Security by Default）是
#    Agent 系统审计和安全合规的核心要求。

# For trusted local debugging only:
# ❓ 问："仅限可信的本地调试"是什么意思？
# 💡 答：这是在提醒用户：下面的命令会输出完整的内容（包括原始的提示词和
#    AI 的回复），这些内容可能包含敏感信息。所以：
#    - "trusted"（可信的）——只在你信任的环境中使用
#    - "local"（本地）——只在你的个人电脑上使用，不要在服务器或共享机器上使用
#    - "debugging"（调试）——仅在排查问题时使用，不要用于日常操作
#    这是对用户的一种安全警示。

# ```bash
# deepseek-runtime run --include-content --workspace . "Search for RuntimeSettings and summarize how configuration works."
# ```
# ❓ 问：这个命令和上面的有什么区别？
# 💡 答：区别在于 --include-content（包含内容）这个参数。
#    没有这个参数时，输出是"安全模式"的——敏感信息被隐藏。
#    加上 --include-content 后，输出是"完整模式"的——包含所有内容。
#    这让你能在本地调试时看到完整的输入和输出，方便排查问题。
#    但注意：不要在生产环境或日志中使用 --include-content 模式。
#    论文参考 A1: Agent Harness Survey — Agent 系统应该同时提供"脱敏"和"完整"
#    两种输出模式，满足安全审计和本地调试的不同需求。
