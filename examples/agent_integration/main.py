# =============================================================================
# main.py — Agent 集成示例
# =============================================================================
# ❓ 问：这个文件演示了什么？
# 💡 答：这是一个极简的 AI Agent 集成示例，展示了如何使用 DeepSeek Runtime
#    创建一个能自主思考、调用工具并回答问题的 Agent。
#    整个示例不到 20 行代码，却完整实现了 B1: ReAct 论文提出的"思考-行动-观察"循环。
#
# 论文引用：
# - B1: ReAct — Agent 通过"思考（Thought）→ 行动（Action）→ 观察（Observation）"
#   的循环来解决复杂问题。本示例中，Agent 先"思考"需要什么信息，
#   然后"行动"——调用 WorkspaceTools 读取文件，最后"观察"结果并给出答案。
# - A1: Agent Harness Survey — 一个优秀的 Agent 框架应该提供简洁的 API，
#   让开发者用最少的代码集成 Agent 能力。
# - B7: AgentBench — Agent 在现实任务（如文件查找、内容摘要）中的表现
#   是评估其能力的重要基准。
# =============================================================================

from __future__ import annotations
# ❓ 问：这行导入什么？
# 💡 答：启用"未来注解"特性，让类型注解（如 -> None）更高效地运行，
#    同时兼容更现代的类型语法。

from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools
# ❓ 问：从 deepseek_runtime 导入了哪些组件？
# 💡 答：导入构建一个 AI Agent 所需的四个核心组件：
#    - DeepSeekClient: AI 模型的客户端，负责与 DeepSeek API 通信
#    - DeepSeekRuntime: 运行时环境，协调 Agent 的执行流程
#    - RuntimeSettings: 运行时配置（API 密钥、模型、端点地址等），
#      通常从环境变量读取（from_env()）
#    - WorkspaceTools: 工作区工具管理器，提供文件读写、搜索等工具给 Agent 使用
#    论文参考 B1: ReAct — 这四个组件对应了 ReAct 循环中"行动"步骤所需的基础设施。


def main() -> None:
    # ❓ 问：main 函数做了什么？
    # 💡 答：main 函数是整个示例的入口。它的工作流程是：
    #    1) 创建运行时环境（自动从环境变量读取配置）
    #    2) 向 Agent 提问——让它找到 README.md 并总结运行时的价值
    #    3) 注册工作区工具（Agent 可以读取文件、搜索内容）
    #    4) 运行 Agent，让它自主完成"思考-行动-观察"的循环
    #    5) 打印 Agent 的最终回答
    #    论文参考 B7: AgentBench — 这个任务（文件查找+内容摘要）正是 AgentBench 中
    #    评估 Agent 实际能力的典型场景。
    #    参考 B1: ReAct — Agent 收到用户的指令后，"思考"需要阅读 README.md，
    #    "行动"使用 read_file 工具，最后"观察"文件内容并生成总结。

    runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
    # ❓ 问：这行代码做了哪些事情？
    # 💡 答：创建了一个"全功能"的 AI Agent 运行时，通过链式调用完成：
    #    1) RuntimeSettings.from_env() — 从环境变量中读取配置
    #       （需要设置 DEEPSEEK_API_KEY、DEEPSEEK_BASE_URL 等）
    #    2) DeepSeekClient(...) — 用配置创建一个 API 客户端
    #    3) DeepSeekRuntime(...) — 用客户端创建运行时环境
    #    这个运行时就是 Agent 的"大脑"，它知道如何调用 AI 模型、
    #    如何管理工具调用、如何处理错误。
    #    论文参考 A1: Agent Harness Survey — 简洁的初始化 API 是框架易用性的关键。

    result = runtime.run(
        # ❓ 问：runtime.run() 启动了什么？
        # 💡 答：启动 Agent 的主循环。Agent 会：
        #    1) 接收用户的消息
        #    2) 调用 AI 模型"思考"如何回应
        #    3) 如果需要信息，调用工作区工具去获取
        #    4) 根据获取到的信息，生成最终回答
        #    这个过程可能迭代多轮（思考→行动→观察→再思考），
        #    直到 Agent 认为可以给出最终答案。

        [{"role": "user", "content": "Find README.md and summarize the runtime value in two bullets."}],
        # ❓ 问：这个列表是什么？
        # 💡 答：这是 Agent 收到的"用户消息"列表。
        #    这里只有一条消息：角色是 "user"（用户），
        #    内容是要求 Agent 找到 README.md 并用两个要点总结运行时的价值。
        #    PM 理解：这就是你对 AI 助手说的话。

        workspace=".",
        # ❓ 问：workspace="." 是什么意思？
        # 💡 答：将当前目录（"."）设为 Agent 的工作区。
        #    Agent 只能在这个目录内读取和操作文件——这是安全限制，
        #    防止 Agent 访问不该看的地方。

        tools=WorkspaceTools(".").catalog(),
        # ❓ 问：tools 参数传入什么？
        # 💡 答：传入 Agent 可以使用的工具列表。
        #    WorkspaceTools(".").catalog() 返回当前目录下所有可用工具的目录，
        #    包括 read_file（读取文件）、search_files（搜索文件）等。
        #    这些工具就是 ReAct 循环中 Agent 可以"调用"的"行动"选项。
        #    论文参考 B1: ReAct — Agent 的工具调用能力是实现"行动"步骤的关键。
    )

    if result.ok:
        # ❓ 问：result.ok 检查什么？
        # 💡 答：检查 Agent 是否成功完成了任务。
        #    ok 为 True 表示 Agent 顺利完成了"思考-行动-观察"循环并生成了答案；
        #    ok 为 False 表示执行过程中出现了错误（如 API 调用失败、工具调用异常等）。

        print(result.final_text)
        # ❓ 问：打印什么内容？
        # 💡 答：打印 Agent 的最终回答（final_text）。
        #    在这个例子中，会打印 README.md 中关于运行时价值的两个要点总结。
        #    论文参考 B1: ReAct — final_text 就是 ReAct 循环最终生成的"回答"。

    else:
        # ❓ 问：else 分支在什么时候执行？
        # 💡 答：当 result.ok 为 False 时，说明 Agent 执行出错。
        #    此时打印错误信息而不是 Agent 的回答。

        print(result.error_class, result.error)
        # ❓ 问：打印什么错误信息？
        # 💡 答：打印两个内容：
        #    - result.error_class: 错误类别（如 PermissionDenied、APIError 等）
        #    - result.error: 具体的错误描述
        #    这样开发者可以快速定位问题。


if __name__ == "__main__":
    # ❓ 问：这个条件的作用？
    # 💡 答：当直接运行本文件时（python main.py），执行 main() 函数；
    #    当被其他模块导入时，不自动执行。这是 Python 的标准实践。

    main()
    # ❓ 问：启动整个程序？
    # 💡 答：运行 main() 函数，启动 AI Agent 执行用户请求的任务。
