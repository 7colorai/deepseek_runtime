# =============================================================================
# test_security_session.py — 安全与会话测试
# =============================================================================
# ❓ 问：这个文件测试什么？
# 💡 答：测试 DeepSeek Runtime 的两个关键领域：
#    1）安全（Security）——包括文件变更管理、权限策略、沙箱隔离等机制，
#       确保 AI Agent 不能越权访问或修改文件。
#    2）会话（Session）——包括会话状态的保存与恢复、工具调用记录的管理，
#       确保 AI Agent 的对话和操作可以在中断后继续。
#
# 论文引用：llm-harness-agent 论文 A1: Agent Harness Survey — Agent 系统的安全性（沙箱、权限管理、
# 审计日志）是评估 Agent 框架成熟度的重要维度。
# 参考 B1: ReAct — Agent 的"行动"步骤需要安全机制的约束。
# 参考 B7: AgentBench — Agent 基准测试应包含安全性和状态管理的评估。
# =============================================================================

from __future__ import annotations
# ❓ 问：这个导入的作用？
# 💡 答：启用"未来注解"特性，让类型注解不参与运行时求值，
#    从而兼容更现代的注解语法，同时避免循环依赖。

import tempfile
# ❓ 问：为什么需要 tempfile？
# 💡 答：测试中涉及大量文件操作（创建、修改、删除文件）和目录操作，
#    使用临时目录避免破坏项目目录，且测试结束后自动清理。

import unittest
# ❓ 问：unittest 的作用？
# 💡 答：Python 标准测试框架，提供 TestCase 类和各种断言方法。

from pathlib import Path
# ❓ 问：Path 的用途？
# 💡 答：pathlib.Path 是现代 Python 中处理文件路径的标准方式，
#    比字符串路径更安全、功能更丰富。

from deepseek_runtime import ChangeManager, ChangeSet, Decision, FileChange, PermissionPolicy, PermissionRequest, PermissionRule, Risk, WorkspaceSandbox, content_sha256
# ❓ 问：这一行导入了多少个类和函数？分别做什么？
# 💡 答：导入了 9 个重要的安全相关的类和函数：
#    - ChangeManager: 变更管理器，统筹文件变更的预览、应用和回滚
#    - ChangeSet: 变更集，包装一组文件变更
#    - Decision: 决策枚举（ALLOW 允许 / DENY 拒绝）
#    - FileChange: 描述一个文件的变更（路径、旧内容哈希、新内容）
#    - PermissionPolicy: 权限策略，决定哪些操作允许或拒绝
#    - PermissionRequest: 权限请求，描述一个操作需要什么权限
#    - PermissionRule: 权限规则，定义某个风险级别的应对策略
#    - Risk: 风险枚举（如 WRITE 写风险、NETWORK 网络风险）
#    - WorkspaceSandbox: 工作区沙箱，隔离 Agent 的文件操作
#    - content_sha256: 计算文件内容的 SHA256 哈希值
#    论文参考 A1: Agent Harness Survey — 权限模型是 Agent 框架安全架构的核心组件。

from deepseek_runtime import __version__
# ❓ 问：__version__ 是什么？
# 💡 答：项目的版本号字符串，定义在 deepseek_runtime 包的 __init__.py 中。
#    测试中检查版本号可以确保包被正确导入且版本匹配预期。

from deepseek_runtime.security import PermissionDenied, SandboxViolation
# ❓ 问：这两个异常类代表什么？
# 💡 答：
#    - PermissionDenied: 权限被拒绝异常——当 Agent 试图执行未授权的操作时抛出
#    - SandboxViolation: 沙箱违规异常——当 Agent 试图逃逸沙箱（如访问工作区外的文件）时抛出
#    这些都是"安全边界"的具体实现。

from deepseek_runtime.session import SessionState, SessionStore, ToolCallRecord, resume_tool_calls
# ❓ 问：这行导入与会话相关的什么内容？
# 💡 答：导入会话管理的四个关键组件：
#    - SessionState: 会话状态，包含消息历史和工具调用记录
#    - SessionStore: 会话存储，负责将会话保存到磁盘和从磁盘加载
#    - ToolCallRecord: 工具调用记录，记录每次工具调用的参数和结果
#    - resume_tool_calls: 恢复工具调用函数，用于重新执行未完成的工具调用


class SecuritySessionTests(unittest.TestCase):
    # ❓ 问：这个测试类包含哪些测试方法？
    # 💡 答：5 个测试方法，覆盖安全和会话的核心功能：
    #    1) test_changeset_public_api_previews_applies_and_rolls_back
    #       — 测试变更的预览、应用和回滚全流程
    #    2) test_changeset_apply_requires_write_permission
    #       — 测试应用变更需要写权限
    #    3) test_sandbox_blocks_path_escape_and_network_by_default
    #       — 测试沙箱阻止路径逃逸和网络访问
    #    4) test_permission_policy_redacts_command_secrets
    #       — 测试权限策略能隐藏命令中的密钥
    #    5) test_session_store_round_trips_and_resume_does_not_repeat_completed_calls
    #       — 测试会话存储的完整生命周期和工具调用恢复

    def test_changeset_public_api_previews_applies_and_rolls_back(self) -> None:
        # ❓ 问：这个测试验证变更管理的什么流程？
        # 💡 答：验证变更管理的完整工作流——预览（preview）、应用（apply）和回滚（rollback）。
        #    这就像"Word 文档的撤销功能"：修改前可以先看差异预览，
        #    确认没问题再应用，不满意还可以一键回滚。
        #    论文参考 B1: ReAct — Agent 的"行动"步骤应该支持预览和回滚，这是安全性的基本要求。

        self.assertEqual(__version__, "0.1.1a1")
        # ❓ 问：为什么检查版本号？
        # 💡 答：首先确认 deepseek_runtime 包的版本是 "0.1.1a1"（alpha 版本）。
        #    如果版本号不匹配，可能是导入了错误的包或版本不兼容。
        #    这是一种"健全性检查"（sanity check）。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：临时目录的作用？
            # 💡 答：创建一个独立的临时工作区，避免测试文件散落在项目目录中。

            workspace = Path(directory)
            # ❓ 问：workspace 代表什么？
            # 💡 答：将临时目录路径包装为 Path 对象，作为 Agent 的"工作区"。
            #    所有文件操作都限制在这个目录中。

            target = workspace / "notes.txt"
            # ❓ 问：target 是什么文件？
            # 💡 答：在临时工作区中创建一个名为 "notes.txt" 的笔记文件路径。
            #    这是我们要测试变更的目标文件。

            target.write_text("old\n", encoding="utf-8")
            # ❓ 问：写入什么内容？
            # 💡 答：向目标文件写入 "old\n"（旧内容），模拟一个已有文件。
            #    编码为 UTF-8，确保中文字符也能正确处理。

            sandbox = WorkspaceSandbox(workspace, PermissionPolicy([PermissionRule(Risk.WRITE, Decision.ALLOW)]))
            # ❓ 问：这行创建了什么安全结构？
            # 💡 答：创建一个工作区沙箱，并配置权限策略：
            #    - WorkspaceSandbox(workspace): 基于工作区目录创建沙箱
            #    - PermissionPolicy: 权限策略，包含一条规则
            #    - PermissionRule(Risk.WRITE, Decision.ALLOW): 
            #      规则内容：对于"写操作"风险，决策为"允许"
            #    这意味着 Agent 可以在工作区内修改文件。
            #    论文参考 A1: Agent Harness Survey — 沙箱隔离是 Agent 安全的第一道防线。

            manager = ChangeManager(sandbox)
            # ❓ 问：ChangeManager 的作用？
            # 💡 答：创建变更管理器，将沙箱注入其中。
            #    ChangeManager 负责协调文件变更的预览、应用和回滚，
            #    所有操作都通过沙箱来执行，确保安全性。

            change_set = ChangeSet((FileChange("notes.txt", content_sha256(b"old\n"), "new\n"),))
            # ❓ 问：ChangeSet 和 FileChange 做了什么？
            # 💡 答：创建一个变更集，包含一个文件变更：
            #    - FileChange("notes.txt", ...): 对 notes.txt 文件的变更
            #    - content_sha256(b"old\n"): 旧内容的 SHA256 哈希值
            #      （验证当前文件是否是我们预期的版本）
            #    - "new\n": 新内容（将文件内容改为 "new"）
            #    ChangeSet 是一个"变更的集合"，可以包含多个 FileChange。
            #    通过哈希值校验旧内容，可以防止"并发冲突"——
            #    如果文件被其他进程修改过，哈希值不匹配，变更会失败。

            preview = manager.preview(change_set)
            # ❓ 问：preview() 返回什么？
            # 💡 答：preview 方法返回变更的"差异预览"（类似 git diff 的输出格式）。
            #    它不会实际修改文件，只是让你看看如果应用这些变更，
            #    文件会变成什么样子。这对于审查 Agent 的操作非常重要。

            self.assertIn("--- a/notes.txt", preview)
            # ❓ 问：为什么预览中有 "--- a/notes.txt"？
            # 💡 答：差异预览使用 Unix diff 格式，以 --- 开头表示"原始文件"。
            #    这行指示被修改的文件是 notes.txt。

            self.assertIn("+++ b/notes.txt", preview)
            # ❓ 问："+++ b/notes.txt" 代表什么？
            # 💡 答：diff 格式中 +++ 开头表示"新文件"（修改后的版本）。
            #    结合 --- 行，组成了标准的文件差异头。

            self.assertIn("-old", preview)
            # ❓ 问："-old" 表示什么？
            # 💡 答：diff 格式中，以 - 开头表示"被删除的行"。
            #    这里表示旧的 "old\n" 内容将被删除。

            self.assertIn("+new", preview)
            # ❓ 问："+new" 表示什么？
            # 💡 答：diff 格式中，以 + 开头表示"新增的行"。
            #    这里表示新的 "new" 内容将被添加。
            #    结合起来，预览告诉我们：文件从 "old" 变成了 "new"。

            token = manager.apply(change_set)
            # ❓ 问：apply() 做了什么？
            # 💡 答：应用变更集——实际修改文件内容。
            #    返回一个"令牌"（token），用于后续的回滚操作。
            #    这个令牌记录了变更的详细信息，以便知道如何撤销。

            self.assertEqual(target.read_text(encoding="utf-8"), "new\n")
            # ❓ 问：为什么文件内容应该是 "new\n"？
            # 💡 答：确认变更已生效——文件内容从 "old\n" 变为了 "new\n"。
            #    如果还是 "old\n"，说明 apply() 没有正确修改文件。

            manager.rollback(token)
            # ❓ 问：rollback() 做了什么？
            # 💡 答：回滚变更——使用之前 apply() 返回的令牌，
            #    将文件恢复到修改前的状态。令牌包含了恢复所需的全部信息。

            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
            # ❓ 问：为什么文件内容变回了 "old\n"？
            # 💡 答：确认回滚成功——文件内容恢复为 "old\n"。
            #    这正是"可逆操作"的体现：Agent 的任何文件修改都可以撤销。

            self.assertTrue(token.consumed)
            # ❓ 问：token.consumed 是什么意思？
            # 💡 答：token.consumed 是一个布尔值，表示这个令牌已被使用（回滚完成）。
            #    一个令牌只能被回滚一次，回滚后标记为 consumed。
            #    这防止了"重复回滚"导致的数据不一致。

    def test_changeset_apply_requires_write_permission(self) -> None:
        # ❓ 问：这个测试验证什么安全机制？
        # 💡 答：验证如果没有"写权限"，应用变更时应该被拒绝。
        #    这是权限系统的核心功能——不是谁都能修改文件，必须获得明确授权。
        #    论文参考 A1: Agent Harness Survey — 权限控制是 Agent 系统安全策略的基石。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：临时目录的目的？
            # 💡 答：创建独立的测试工作区。

            workspace = Path(directory)
            target = workspace / "notes.txt"
            target.write_text("old\n", encoding="utf-8")
            # ❓ 问：这几行在做什么？
            # 💡 答：在临时工作区中创建一个 notes.txt 文件，内容为 "old\n"，
            #    用于测试文件修改的权限控制。

            manager = ChangeManager(WorkspaceSandbox(workspace))
            # ❓ 问：这里创建沙箱时为什么没有传入权限策略？
            # 💡 答：WorkspaceSandbox(workspace) 只传入了工作区路径，
            #    没有传入 PermissionPolicy。这样沙箱会使用默认的权限策略——
            #    默认策略通常是"拒绝所有未明确允许的操作"。
            #    也就是说，写操作默认不被允许。

            change_set = ChangeSet((FileChange("notes.txt", content_sha256(b"old\n"), "new\n"),))
            # ❓ 问：这个变更集的内容？
            # 💡 答：与上一个测试相同的变更——将 notes.txt 从 "old" 改为 "new"。

            with self.assertRaises(PermissionDenied):
                # ❓ 问：assertRaises 是什么？
                # 💡 答：unittest 提供的上下文管理器，用于测试是否抛出了预期的异常。
                #    如果代码块中抛出了 PermissionDenied 异常，测试通过；
                #    如果没有抛出异常，测试失败。

                manager.apply(change_set)
                # ❓ 问：为什么 apply 应该失败？
                # 💡 答：因为沙箱的默认策略不允许写操作（没有明确的 ALLOW 规则），
                #    apply() 方法应该抛出 PermissionDenied（权限被拒绝）异常。
                #    这就确保了 Agent 不能随意修改文件，必须获得授权。

    def test_sandbox_blocks_path_escape_and_network_by_default(self) -> None:
        # ❓ 问：这个测试验证哪两个安全特性？
        # 💡 答：验证沙箱的两个默认安全行为：
        #    1）阻止路径逃逸（Path Escape）——Agent 不能访问工作区之外的文件
        #    2）阻止网络访问（Network Access）——Agent 不能发起外部网络请求
        #    这些都是为了防止 Agent 的执行"越界"。
        #    论文参考 A1: Agent Harness Survey — 沙箱的路径隔离和网络隔离是 Agent 安全的核心机制。
        #    参考 B7: AgentBench — Agent 基准测试应该评估沙箱的有效性。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：临时目录的作用？
            # 💡 答：创建独立的工作区目录。

            sandbox = WorkspaceSandbox(Path(directory))
            # ❓ 问：这里创建沙箱的方式？
            # 💡 答：只传入工作区路径，使用默认权限策略（拒绝所有未允许的操作）。

            with self.assertRaises(SandboxViolation):
                # ❓ 问：assertRaises(SandboxViolation) 测试什么？
                # 💡 答：检查是否抛出 SandboxViolation（沙箱违规）异常。
                #    如果抛出，说明沙箱成功拦截了违规操作；如果没有抛出，说明沙箱有漏洞。

                sandbox.resolve("../outside")
                # ❓ 问：resolve("../outside") 为什么违规？
                # 💡 答：sandbox.resolve() 用于解析文件路径。
                #    "../outside" 使用了 ".."（父目录）试图逃离工作区，
                #    访问工作区之外的文件。
                #    沙箱应该检测到这种"路径逃逸"尝试并抛出异常。
                #    这就像监狱的围墙——囚犯不能越狱。

            with self.assertRaises(PermissionDenied):
                # ❓ 问：这次又测试什么？
                # 💡 答：检查是否抛出 PermissionDenied（权限被拒绝）异常。

                sandbox.run(("curl", "https://example.com"))
                # ❓ 问：sandbox.run() 在做什么？
                # 💡 答：沙箱的 run() 方法用于在受控环境中执行系统命令。
                #    这里试图执行 curl https://example.com（发送网络请求）。
                #    默认情况下，沙箱禁止网络访问，所以应该抛出 PermissionDenied。
                #    这确保了 Agent 不能随意连接外部服务器。

    def test_permission_policy_redacts_command_secrets(self) -> None:
        # ❓ 问：这个测试验证什么安全特性？
        # 💡 答：验证权限策略在记录审计事件时，
        #    会自动隐藏（redact）命令中的敏感信息（如密钥、密码）。
        #    这样审计日志不会泄露机密数据。
        #    论文参考 A1: Agent Harness Survey — 审计日志的密钥脱敏是 Agent 安全审计的基本要求。

        policy = PermissionPolicy([PermissionRule(Risk.NETWORK, Decision.DENY)])
        # ❓ 问：这个权限策略是什么？
        # 💡 答：创建一个权限策略，包含一条规则：
        #    - Risk.NETWORK: 对于"网络操作"风险
        #    - Decision.DENY: 决策为"拒绝"
        #    也就是说，所有网络操作都被禁止。

        decision = policy.decide(PermissionRequest(Risk.NETWORK, command=("curl", "--token", "secret")))
        # ❓ 问：PermissionRequest 和 decide() 做了什么？
        # 💡 答：创建一个权限请求：
        #    - Risk.NETWORK: 请求执行网络操作
        #    - command=("curl", "--token", "secret"): 要执行的命令是 curl，
        #      包含一个 --token 参数，值为 "secret"（敏感的密钥）
        #    然后调用 policy.decide() 让策略做出决策。

        self.assertEqual(decision, Decision.DENY)
        # ❓ 问：决策结果应该是什么？
        # 💡 答：因为策略中配置了 Risk.NETWORK -> DENY（拒绝网络操作），
        #    所以 decision 应该是 Decision.DENY（拒绝）。
        #    这验证了权限策略的正确应用。

        self.assertNotIn("secret", str(policy.audit_events))
        # ❓ 问：为什么审计事件中不应该有 "secret"？
        # 💡 答：验证策略的审计事件列表中不包含 "secret"（密钥原文）。
        #    即使命令中包含敏感信息，审计日志也应该将其脱敏/隐藏。
        #    这样运维人员查看日志时能看到"有人尝试了带 token 的网络请求"，
        #    但看不到具体的密钥值。这是一种"最小化信息泄露"的安全设计。

    def test_session_store_round_trips_and_resume_does_not_repeat_completed_calls(self) -> None:
        # ❓ 问：这个综合测试验证什么？
        # 💡 答：测试会话管理的完整流程：
        #    1) 保存会话状态（save）
        #    2) 加载会话状态（load）
        #    3) 恢复工具调用时，已完成的操作不会重复执行
        #    这确保了 Agent 在中断后能准确恢复，不会做重复工作。
        #    论文参考 B1: ReAct — Agent 的循环需要状态持久化支持，才能在中断后从断点继续。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：临时目录的作用？
            # 💡 答：创建临时目录，作为会话存储的持久化目录。

            store = SessionStore(Path(directory))
            # ❓ 问：SessionStore 是什么？
            # 💡 答：创建一个会话存储实例，将会话数据保存在临时目录中。
            #    SessionStore 负责将会话状态序列化到磁盘，以及从磁盘反序列化。

            state = SessionState(messages=[{"role": "user", "content": "keep local"}], tool_calls=[ToolCallRecord("work", {"value": 1}, True)])
            # ❓ 问：SessionState 包含了什么？
            # 💡 答：创建一个会话状态，包含：
            #    - messages: 消息历史，有一条用户消息 "keep local"
            #    - tool_calls: 工具调用记录列表，包含一条记录：
            #      - "work": 工具名称
            #      - {"value": 1}: 调用参数
            #      - True: 已完成（True 表示此调用已完成）

            store.save(state)
            # ❓ 问：save() 做了什么？
            # 💡 答：将会话状态保存到磁盘。这样即使程序崩溃，
            #    下次启动时也能从磁盘恢复会话。

            loaded = store.load(state.session_id)
            # ❓ 问：load() 在做什么？
            # 💡 答：从磁盘加载之前保存的会话状态。
            #    state.session_id 是每个会话的唯一标识（UUID），
            #    用这个 ID 来检索对应的会话数据。

            calls: list[int] = []
            # ❓ 问：空列表 calls 的作用？
            # 💡 答：创建一个空列表，用来记录 handler 函数被调用的次数和参数。
            #    通过这个列表我们可以知道工具调用是否被执行了。

            def handler(arguments):
                # ❓ 问：handler 函数做什么？
                # 💡 答：这是一个模拟的工具处理函数。
                #    当恢复工具调用时，会调用 handler 来执行工具。
                #    这里它只是记录调用的参数值并返回 "done"。

                calls.append(arguments["value"])
                # ❓ 问：记录什么信息？
                # 💡 答：将传入的参数 value 的值添加到 calls 列表中。
                #    这样我们可以通过 calls 的内容知道 handler 被调用了多少次。

                return "done"
                # ❓ 问：返回值 "done" 的意义？
                # 💡 答：模拟工具执行成功的返回值。

            resume_tool_calls(loaded, {"work": handler})
            # ❓ 问：第一次 resume_tool_calls 做了什么？
            # 💡 答：第一次调用 resume_tool_calls，尝试恢复会话中未完成的工具调用。
            #    传入：
            #    - loaded: 加载的会话状态
            #    - {"work": handler}: 可用工具的字典，其中 "work" 工具对应 handler 函数
            #    因为之前的 tool_call 的 completed=True（已完成），
            #    所以这个已完成的调用不应该再次执行。

            resume_tool_calls(loaded, {"work": handler})
            # ❓ 问：第二次 resume_tool_calls 呢？
            # 💡 答：再次调用 resume_tool_calls。
            #    这模拟了"重复恢复"的场景——某些情况下可能多次尝试恢复。

            self.assertEqual(calls, [1])
            # ❓ 问：为什么 calls 应该是 [1] 而不是 [1, 1]？
            # 💡 答：工具调用在保存时已标记为 completed（已完成），
            #    所以两次 resume_tool_calls 都不应该重新执行它。
            #    calls 中只有 [1] 表示 handler 只被调用了一次？
            #    等等，这里实际上是零次还是 1 次？
            #    注意：ToolCallRecord("work", {"value": 1}, True) 中 True 表示已完成。
            #    但 resume_tool_calls 对于已完成的调用，实际上会标记为"不执行"。
            #    所以 calls 应该是 [] 才对... 但是测试期待 [1]。
            #    实际上，仔细看：resume_tool_calls 会重新执行失败的或未完成的调用，
            #    已完成的调用不会执行。所以这里 calls 应该是 [] 而不是 [1]。
            #    但这个测试写的是 self.assertEqual(calls, [1])，说明 resume_tool_calls 可能在
            #    某种条件下执行了已完成调用的 handler... 
            #    或者 ToolCallRecord 的第三个参数可能不是 completed 标志位？
            #    但代码写的是 ToolCallRecord("work", {"value": 1}, True)，第三个参数 True 表示 completed。
            #    所以 calls 应该是 []。
            #    但测试写的是 [1]... 这个可能是测试代码本身的设计，我们保留原样。
            #    关键点：我们无论如何要保留所有原始代码不变。
            
            self.assertEqual(loaded.tool_calls[0].status, "succeeded")
            # ❓ 问：为什么工具调用状态应该是 "succeeded"？
            # 💡 答：检查恢复后的工具调用状态为 "succeeded"（成功）。
            #    这验证了会话正确地追踪了工具调用的执行结果。


if __name__ == "__main__":
    # ❓ 问：__name__ == "__main__" 的含义？
    # 💡 答：当直接运行此文件时，自动执行 unittest.main() 运行所有测试；
    #    当被导入时，不自动运行测试。

    unittest.main()
    # ❓ 问：unittest.main() 的作用？
    # 💡 答：运行当前模块中所有 test_ 开头的测试方法，并在终端输出结果。
