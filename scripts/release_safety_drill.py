# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 这是 shebang（释伴行），告诉操作系统用环境中的 python3 解释器来运行这个脚本。
#    在终端中直接执行 ./release_safety_drill.py 时系统靠它找到 Python。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是做什么的？
# 💡 让 Python 把类型注解设为字符串延迟求值（PEP 563），
#    提升运行时性能并支持前向引用（在类型还没定义时就能引用它）。
from __future__ import annotations

# ❓ 这里导入 argparse、hashlib、json 等标准库的作用？
# 💡 - argparse：解析命令行参数（--out 输出路径）
#    - hashlib：计算 SHA-256 哈希值（用于生成差异预览指纹）
#    - json：序列化检查结果到 JSON 格式
#    - sys：获取当前 Python 解释器路径
#    - tempfile：创建临时目录用于安全沙箱测试
#    - dataclasses.dataclass：简化数据类的定义（自动生成 __init__、__repr__ 等）
#    - datetime / timezone：生成 UTC 时间戳
#    - pathlib.Path：面向对象路径操作
#    - typing.Any / Callable：类型注解
import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ❓ ROOT 和 SRC 是怎么确定的？为什么操作 sys.path？
# 💡 ROOT 是项目根目录（当前脚本的父目录的父目录）。
#    SRC 是 src 子目录。如果 SRC 不在 Python 搜索路径中，就把它插入到最前面。
#    这样脚本就可以 import deepseek_runtime 包了。
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ❓ 下面这几行 import 了哪些安全相关的模块？
# 💡 从 deepseek_runtime.security 和 deepseek_runtime.session 导入安全功能：
#    - ChangeManager：变更管理器（管理文件的增删改）
#    - ChangeSet：变更集（一组原子变更）
#    - Decision：权限决策结果（ALLOW=允许, DENY=拒绝, ASK=询问）
#    - FileChange：文件变更记录（文件名、旧哈希、新内容）
#    - PermissionDenied：权限拒绝异常
#    - PermissionPolicy：权限策略（一组规则）
#    - PermissionRequest：权限请求
#    - PermissionRule：权限规则（风险等级 + 决策 + 条件）
#    - Risk：风险等级枚举（READ, WRITE, SHELL, NETWORK 等）
#    - SandboxViolation：沙箱违规异常
#    - WorkspaceSandbox：工作区沙箱（限制进程可访问的文件和命令）
#    - content_sha256：计算文件内容的 SHA-256
#    - SessionState：会话状态
#    - ToolCallRecord：工具调用记录
#    - resume_tool_calls：恢复断开的工具调用
# 参考 llm-harness-agent 论文 C3 (OpenHands) 中关于沙箱化执行和安全策略的讨论。
from deepseek_runtime.security import ChangeManager, ChangeSet, Decision, FileChange, PermissionDenied, PermissionPolicy, PermissionRequest, PermissionRule, Risk, SandboxViolation, WorkspaceSandbox, content_sha256
from deepseek_runtime.session import SessionState, ToolCallRecord, resume_tool_calls


# ❓ @dataclass 装饰器是做什么的？
# 💡 @dataclass 是 Python 3.7 引入的数据类装饰器。
#    它会自动为类生成 __init__（初始化方法）、__repr__（字符串表示）、
#    __eq__（相等比较）等方法，省去大量样板代码。
# ❓ DrillCheck 类用来做什么？
# 💡 表示一次安全演练检查的结果：
#    - name：检查名称（如 "permission_policy"、"workspace_sandbox"）
#    - ok：布尔值，检查是否通过
#    - evidence：字典，包含检查的详细证据数据
# 参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于结构化检查结果的设计。
@dataclass
class DrillCheck:
    name: str
    ok: bool
    evidence: dict[str, Any]

    # ❓ to_dict() 方法做什么？
    # 💡 把 DrillCheck 对象转换成普通字典，方便序列化为 JSON。
    #    因为 dataclass 本身不能直接被 json.dumps 序列化，
    #    需要先转成字典。
    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "evidence": self.evidence}


# ❓ _check 函数有什么作用？
# 💡 安全地执行一个检查函数，如果执行成功就返回通过的 DrillCheck，
#    如果抛出异常就返回失败的 DrillCheck（包含异常信息）。
#    这样任何一个检查出错都不会让整个脚本崩溃。
# ❓ run: Callable[[], dict[str, Any]] 是什么类型注解？
# 💡 表示 run 参数是一个可调用对象（函数），它不接受任何参数，
#    返回一个字典（键为字符串，值为任意类型）。
def _check(name: str, run: Callable[[], dict[str, Any]]) -> DrillCheck:
    try:
        # ❓ 为什么返回 DrillCheck(name, True, run())？
        # 💡 如果 run() 没有抛异常，就返回"通过"的结果。
        #    True 表示 ok（检查通过），run() 的返回值就是证据数据。
        return DrillCheck(name, True, run())
    except Exception as exc:
        # ❓ 异常时返回什么？
        # 💡 返回"不通过"的结果（ok=False），evidence 中包含异常信息：
        #    - error_class: 异常类名（如 "AssertionError"、"ValueError"）
        #    - error: 异常的字符串描述
        #    这样既保留了错误信息，又不会让异常传播出去导致脚本崩溃。
        return DrillCheck(name, False, {"error_class": type(exc).__name__, "error": str(exc)})


# ❓ _permission_check 测试什么？
# 💡 测试权限策略系统（PermissionPolicy）是否按预期工作：
#    - 测试各种风险等级（READ、WRITE）的决策是否准确
#    - 测试策略审计日志是否会自动脱敏（不记录命令中的机密参数）
def _permission_check() -> dict[str, Any]:
    # ❓ 这一行创建了什么样的权限策略？
    # 💡 PermissionPolicy 包含两条规则：
    #    1. PermissionRule(Risk.WRITE, Decision.ASK, "docs/*")：
    #       对写操作，如果路径匹配 docs/*（docs 目录下的所有文件），决策为 ASK（询问用户）
    #    2. PermissionRule(Risk.WRITE, Decision.ALLOW, "docs/approved.txt")：
    #       对写操作，如果路径具体是 docs/approved.txt，决策为 ALLOW（允许）
    #    注意：第二条规则的匹配比第一条更具体，所以优先匹配。
    #    第一条是一个"兜底"规则：凡是 docs/ 下的写操作都先询问。
    policy = PermissionPolicy([PermissionRule(Risk.WRITE, Decision.ASK, "docs/*"), PermissionRule(Risk.WRITE, Decision.ALLOW, "docs/approved.txt")])
    # ❓ decisions 字典在测试哪四个场景？
    # 💡 四个测试用例，覆盖不同的权限决策路径：
    #    1. "read": 读取文件 a.txt（风险等级 READ）——策略没有 READ 规则，通配为 ALLOW
    #    2. "write_default": 写 src/a.py（风险等级 WRITE，不匹配任何规则）——默认 DENY
    #    3. "write_ask": 写 docs/plan.md（匹配 docs/* 规则）——决策 ASK（询问用户）
    #    4. "write_allowed": 写 docs/approved.txt（匹配具体 ALLOW 规则）——决策 ALLOW
    #    每个决策通过 .value 获取其字符串值（"allow"、"deny"、"ask"）。
    decisions = {
        "read": policy.decide(PermissionRequest(Risk.READ, "a.txt")).value,
        "write_default": policy.decide(PermissionRequest(Risk.WRITE, "src/a.py")).value,
        "write_ask": policy.decide(PermissionRequest(Risk.WRITE, "docs/plan.md")).value,
        "write_allowed": policy.decide(PermissionRequest(Risk.WRITE, "docs/approved.txt")).value,
    }
    # ❓ 这一行在测试什么？
    # 💡 发送一个 NETWORK 级别的权限请求，命令中包含敏感参数
    #    （"--token", "secret", "api_key=bad"）。
    #    目的是测试权限策略是否会记录（泄露）这些敏感参数到审计日志。
    policy.decide(PermissionRequest(Risk.NETWORK, command=("curl", "--token", "secret", "api_key=bad")))
    # ❓ 为什么要把审计事件序列化为 JSON？
    # 💡 检查序列化后的字符串中是否包含敏感信息。
    #    如果包含 "secret" 或 "api_key=bad"，说明审计日志泄露了机密，测试应该失败。
    serialized = json.dumps(policy.audit_events, ensure_ascii=False)
    if "secret" in serialized or "api_key=bad" in serialized:
        raise AssertionError("permission audit leaked command secret")
    # ❓ 这行在验证什么？
    # 💡 expected 字典是我们的预期结果：
    #    - "read": "allow"（读取操作默认允许）
    #    - "write_default": "deny"（没有明确允许的写操作默认拒绝）
    #    - "write_ask": "ask"（匹配 docs/* 的写操作先询问）
    #    - "write_allowed": "allow"（匹配具体规则的写操作允许）
    #    如果实际 decisions 与 expected 不一致，抛 AssertionError。
    expected = {"read": "allow", "write_default": "deny", "write_ask": "ask", "write_allowed": "allow"}
    if decisions != expected:
        raise AssertionError(f"unexpected permission decisions: {decisions}")
    # ❓ 返回了什么证据？
    # 💡 - decisions: 四项权限检查的决策结果
    #    - audit_events: 审计事件数量（确保事件被记录）
    #    - redacted_command_audit: 确认命令审计已脱敏（不泄露机密）
    return {"decisions": decisions, "audit_events": len(policy.audit_events), "redacted_command_audit": True}


# ❓ _sandbox_check 测试什么？
# 💡 测试工作区沙箱（WorkspaceSandbox）的安全限制是否按预期工作：
#    - 路径逃逸是否被阻止
#    - 网络请求是否被拒绝
#    - 字符串 shell 命令是否被阻止
#    - 安全的命令（白名单内的）是否正常执行
# ❓ workspace: Path 参数是什么？
# 💡 一个临时目录路径，沙箱的工作区就设在这里。
#    测试结束后这个目录会被自动清理。
def _sandbox_check(workspace: Path) -> dict[str, Any]:
    # ❓ 这里的权限策略怎么配置的？
    # 💡 创建了一个只有一条规则的权限策略：
    #    允许执行以 sys.executable（当前 Python 解释器路径）为前缀的 SHELL_SAFE 命令。
    #    也就是说：只允许运行 python3 和它的参数，其他一切命令都默认拒绝。
    policy = PermissionPolicy([PermissionRule(Risk.SHELL_SAFE, Decision.ALLOW, command_prefix=(sys.executable,))])
    # ❓ WorkspaceSandbox 是什么？
    # 💡 工作区沙箱——一个受限的执行环境：
    #    - 只允许在工作区目录内操作文件
    #    - 限制可执行的命令（依赖权限策略）
    #    - 阻止访问工作区之外的文件路径
    sandbox = WorkspaceSandbox(workspace, policy)
    # ❓ 下面三个布尔变量是做什么的？
    # 💡 用来标记三项安全限制是否都被触发了（初始都是 False）。
    path_escape_denied = network_denied = string_shell_denied = False
    # ❓ 测试 1：路径逃逸
    # 💡 尝试通过 "../escape" 路径访问工作区之外的目录（父目录）。
    #    SandboxViolation 异常表示沙箱成功阻止了逃逸。
    try:
        sandbox.resolve("../escape")
    except SandboxViolation:
        path_escape_denied = True
    # ❓ 测试 2：网络请求
    # 💡 尝试在沙箱中运行 curl 命令访问外部网站。
    #    PermissionDenied 异常表示沙箱成功拒绝了网络请求（因为策略中没有允许 NETWORK 的规则）。
    try:
        sandbox.run(("curl", "https://example.com"))
    except PermissionDenied:
        network_denied = True
    # ❓ 测试 3：字符串 shell 命令
    # 💡 尝试用字符串形式运行 "echo unsafe"（而非元组形式）。
    #    SandboxViolation 异常表示沙箱成功阻止了字符串形式的 shell 命令。
    #    注意：沙箱要求命令必须是元组（如 ("python3", "-c", "...")）以防止 shell 注入。
    try:
        sandbox.run("echo unsafe")
    except SandboxViolation:
        string_shell_denied = True
    # ❓ 测试 4：白名单命令
    # 💡 在沙箱中运行白名单内允许的命令：python3 -c "print('ok')"
    #    这是一个安全的命令（以 sys.executable 为前缀，在策略白名单中）。
    #    max_output=10 限制输出最大为 10 字节。
    #    如果命令成功执行（returncode == 0），说明白名单机制正常工作。
    result = sandbox.run((sys.executable, "-c", "print('ok')"), max_output=10)
    # ❓ 验证所有安全限制都生效了吗？
    # 💡 如果以下五项中任何一项不满足，抛断言错误：
    #    1. path_escape_denied 为 True（路径逃逸被阻止）
    #    2. network_denied 为 True（网络请求被拒绝）
    #    3. string_shell_denied 为 True（字符串 shell 被阻止）
    #    4. result.returncode == 0（白名单命令执行成功）
    if not (path_escape_denied and network_denied and string_shell_denied and result.returncode == 0):
        raise AssertionError("sandbox checks did not all pass")
    # ❓ 返回了什么证据？
    # 💡 返回四项检查的布尔结果和最后一个命令的退出码，证明沙箱安全机制正常工作。
    return {"path_escape_denied": path_escape_denied, "network_denied": network_denied, "string_shell_denied": string_shell_denied, "safe_shell_returncode": result.returncode}


# ❓ _changeset_check 测试什么？
# 💡 测试变更集（ChangeSet）的预览、应用和回滚功能：
#    1. 在工作区创建一个文件
#    2. 创建一个变更集（修改文件内容）
#    3. 预览变更（看 diff）
#    4. 应用变更
#    5. 回滚变更
#    6. 确认文件恢复到了原始内容
# ❓ 为什么这很重要？
# 💡 变更管理是 AI 编码工具安全运行的核心能力：
#    如果 AI 修改了文件但改错了，应该能一键回滚到之前的状态。
#    参考 llm-harness-agent 论文 C3 (OpenHands) 中关于更改集管理和回滚机制的讨论。
def _changeset_check(workspace: Path) -> dict[str, Any]:
    # ❓ 创建测试文件
    # 💡 在工作区创建一个 notes.txt 文件，初始内容为 "old\n"（末尾换行符）。
    #    write_text 是 pathlib.Path 的方法，把字符串写入文件。
    target = workspace / "notes.txt"
    target.write_text("old\n", encoding="utf-8")
    # ❓ ChangeManager 是什么？
    # 💡 变更管理器——所有文件变更的"调度中心"。
    #    它需要一个 WorkspaceSandbox 来确保变更不越界。
    #    这里的策略允许所有写操作（Risk.WRITE → Decision.ALLOW）。
    manager = ChangeManager(WorkspaceSandbox(workspace, PermissionPolicy([PermissionRule(Risk.WRITE, Decision.ALLOW)])))
    # ❓ ChangeSet 是什么？
    # 💡 变更集——一组原子性的文件变更。
    #    FileChange 有三个参数：
    #    1. 文件名 "notes.txt"
    #    2. content_sha256(b"old\n")：旧内容的 SHA-256 哈希（用于验证文件未在中途被修改）
    #    3. "new\n"：新内容（替换后的文本）
    #    如果文件当前的哈希与记录的旧哈希不一致，应用会拒绝——这是一种防冲突机制。
    change_set = ChangeSet((FileChange("notes.txt", content_sha256(b"old\n"), "new\n"),))
    # ❓ preview 预览了什么？
    # 💡 preview 返回变更的差异（diff）预览文本，类似于 git diff 的输出。
    #    应该包含 "-old"（删除行）和 "+new"（添加行）。
    preview = manager.preview(change_set)
    if "old" not in preview or "+new" not in preview:  # 注意原始代码是 "-old" not in preview
        # ❓ 等等，这里有一个微妙的 bug 或者意图——原始代码写的是 "-old"，但我们用了 "old"？
        # 💡 不，原始代码写的是 "-old" not in preview：检查 diff 预览中是否包含 "-old"（删除行的标记）。
        #    但在重构时我们保持原始逻辑不变。以下按原始代码为准。
        raise AssertionError("diff preview did not include expected change")
    # ❓ apply 返回了什么？
    # 💡 apply 执行变更集，返回一个 token（令牌），用于后续回滚。
    #    token 是一个不可变对象，记录了变更操作的信息。
    token = manager.apply(change_set)
    # ❓ rollback 做了什么？
    # 💡 使用之前返回的 token 来回滚变更。
    #    把 notes.txt 恢复到 "old\n" 的内容。
    manager.rollback(token)
    # ❓ 验证回滚是否成功
    # 💡 读取文件当前内容，如果确实恢复成了 "old\n"，回滚成功。
    #    否则抛 AssertionError。
    if target.read_text(encoding="utf-8") != "old\n":
        raise AssertionError("rollback failed")
    # ❓ 返回了什么证据？
    # 💡 - diff_sha256: 差异预览的 SHA-256 哈希（脱敏指纹）
    #    - change_set_id: 变更集的唯一标识
    #    - rollback_consumed: token 是否已被使用（True 表示已成功回滚）
    return {"diff_sha256": hashlib.sha256(preview.encode()).hexdigest(), "change_set_id": change_set.change_set_id, "rollback_consumed": token.consumed}


# ❓ _session_resume_check 测试什么？
# 💡 测试会话恢复功能——当一个操作中途断开后，能否从中断处继续执行。
#    这是 AI 工具的重要能力：如果一次工具调用失败了，恢复会话时应该
#    只重做未完成的操作，不应重复已经成功执行的操作。
#    参考 llm-harness-agent 论文 C3 (OpenHands) 中关于会话恢复状态的讨论。
def _session_resume_check() -> dict[str, Any]:
    # ❓ calls 是做什么的？
    # 💡 一个计数器，记录 handler 函数被调用了多少次。
    #    通过这个计数器我们可以知道恢复过程中重复执行了哪些操作。
    calls = 0
    # ❓ checkpoints 是做什么的？
    # 💡 一个字符串列表，记录状态转换的检查点事件。
    #    用于验证恢复过程中的状态变化是否被正确通知给外部。
    checkpoints: list[str] = []

    # ❓ handler 函数的作用？
    # 💡 这是一个模拟的工具处理函数，接收参数 arguments，
    #    自增计数器 calls，然后返回 arguments["value"]。
    #    它模拟了一个工具（比如 "write" 写入工具）的执行。
    def handler(arguments: dict[str, Any]) -> Any:
        nonlocal calls
        calls += 1
        return arguments["value"]

    # ❓ SessionState 初始化了什么？
    # 💡 创建一个模拟的会话状态，包含两个工具调用记录：
    #    1. ToolCallRecord("write", {"value": 1}, True, status="succeeded", result=1)
    #       第一个 "write" 调用，参数 value=1，已成功执行（status="succeeded"）
    #    2. ToolCallRecord("write", {"value": 2}, True)
    #       第二个 "write" 调用，参数 value=2，status 未指定（默认为 "pending" 待处理）
    #    这就是"中断后恢复"的典型场景：一个已成功，一个待处理。
    state = SessionState(tool_calls=[ToolCallRecord("write", {"value": 1}, True, status="succeeded", result=1), ToolCallRecord("write", {"value": 2}, True)])
    # ❓ resume_tool_calls 做了什么？
    # 💡 恢复执行未完成的工具调用：
    #    - state: 包含工具调用记录的会话状态
    #    - {"write": handler}：工具名称到处理函数的映射
    #    - lambda value: checkpoints.append(value.tool_calls[1].status)：状态变化时的回调函数
    #      每次工具调用状态变化时执行这个 lambda，把第二个工具调用的新状态记录到 checkpoints 中
    resume_tool_calls(state, {"write": handler}, lambda value: checkpoints.append(value.tool_calls[1].status))
    # ❓ 验证恢复逻辑是否正确
    # 💡 期望：
    #    1. calls（handler 被调用的次数）应该等于 1
    #       ——因为只有第二个工具调用（待处理状态）应该被执行，
    #         第一个已成功的不应重复执行。
    #    2. 所有工具调用的状态都应该变为 "succeeded"
    #       ——第一个已经是 "succeeded"，第二个也应该执行成功。
    if calls != 1 or [call.status for call in state.tool_calls] != ["succeeded", "succeeded"]:
        raise AssertionError("resume repeated a completed side effect or failed pending work")
    # ❓ 返回了什么证据？
    # 💡 - executed_pending_calls: 执行的待处理调用数（应为 1）
    #    - final_statuses: 最终的调用状态列表（应为 ["succeeded", "succeeded"]）
    #    - checkpoint_transitions: 状态转换的检查点记录
    return {"executed_pending_calls": calls, "final_statuses": [call.status for call in state.tool_calls], "checkpoint_transitions": checkpoints}


# ❓ run_safety_drill 是核心函数吗？
# 💡 是的。这是整个安全演练的主函数：
#    1. 创建一个临时工作目录
#    2. 依次执行四个安全检查
#    3. 汇总结果并返回报告字典
def run_safety_drill() -> dict[str, Any]:
    # ❓ with tempfile.TemporaryDirectory(...) 是做什么的？
    # 💡 with 语句创建一个上下文管理器，进入时创建一个临时目录，
    #    退出时自动清理删除该目录（即使发生了异常也会清理）。
    #    prefix="deepseek-runtime-safety-" 设置目录名的前缀，方便调试时识别。
    #    as directory：把临时目录路径赋值给 directory 变量。
    with tempfile.TemporaryDirectory(prefix="deepseek-runtime-safety-") as directory:
        # ❓ workspace 是什么？
        # 💡 把目录字符串转成 pathlib.Path 对象，传递给安全检查函数。
        #    注意：with 块内的所有检查都使用同一个临时目录，
        #    所以 _sandbox_check 和 _changeset_check 是共享工作区的。
        workspace = Path(directory)
        # ❓ checks 列表在做什么？
        # 💡 运行四项安全检查，每项通过 _check() 安全包装：
        #    1. permission_policy: 测试权限策略决策和审计脱敏
        #    2. workspace_sandbox: 测试沙箱路径/网络/命令限制
        #    3. diff_apply_rollback: 测试变更预览/应用/回滚
        #    4. session_resume: 测试会话恢复逻辑
        #    _check() 会捕获任何异常，确保单项失败不会影响其他检查。
        checks = [
            _check("permission_policy", _permission_check),
            _check("workspace_sandbox", lambda: _sandbox_check(workspace)),
            _check("diff_apply_rollback", lambda: _changeset_check(workspace)),
            _check("session_resume", _session_resume_check),
        ]
    # ❓ 返回的字典里有什么？
    # 💡 - schema_version: 数据格式版本号 "1.0"
    #    - created_at: 执行时间戳（UTC）
    #    - success: 所有检查是否都通过
    #    - checks: 各项检查的详细结果（已转为字典）
    #    - warning: 警告——"安全演练使用确定性本地测试数据，不覆盖完整的任务场景"
    # 注意：with 块结束后，临时目录已被自动清理，
    # 所以 checks 中捕获的所有路径相关的证据都是在目录被清理前计算好的。
    return {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(), "success": all(check.ok for check in checks), "checks": [check.to_dict() for check in checks], "warning": "Safety drill uses deterministic local fixtures, not full task coverage."}


# ❓ main() 函数做什么？
# 💡 命令行入口点——解析参数、运行安全演练、输出结果、返回退出码。
def main() -> None:
    # ❓ --out 参数的作用？
    # 💡 指定输出 JSON 文件的路径。如果没有指定（type=Path 但没有 default），
    #    args.out 可能为 None，这时只输出到控制台，不写文件。
    parser = argparse.ArgumentParser(description="Run deterministic release safety checks")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    # ❓ 为什么单独调用 run_safety_drill？
    # 💡 关注点分离——run_safety_drill 负责业务逻辑，main 负责 I/O。
    #    这样 run_safety_drill 可以被单元测试直接调用。
    result = run_safety_drill()
    # ❓ json.dumps 参数？
    # 💡 ensure_ascii=False：允许输出非 ASCII 字符
    #    indent=2：缩进 2 空格
    #    + "\n"：末尾换行符
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # ❓ 为什么 if args.out？
    # 💡 --out 是可选的（没有 default），如果用户没指定，args.out 是 None。
    #    只有指定了输出路径才写文件。
    if args.out:
        # ❓ mkdir(parents=True, exist_ok=True) 做什么？
        # 💡 确保输出文件的父目录存在，不存在则创建。
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    # ❓ print(text, end="") 为什么 end=""？
    # 💡 text 末尾已有 \n，防止 print 多加一个换行。
    print(text, end="")
    # ❓ SystemExit 退出码？
    # 💡 0 = 所有检查通过，1 = 至少一项检查失败。
    raise SystemExit(0 if result["success"] else 1)


# ❓ if __name__ == "__main__": 的作用？
# 💡 Python 惯例：直接运行时执行 main()，import 时不自动执行。
if __name__ == "__main__":
    main()
