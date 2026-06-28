"""
会话管理层（Session Layer）—— Agent 怎么"记住"它做到了哪一步？

❓ 问：AI Agent 和普通 API 调用最大的区别是什么？
💡 答：Agent 不是"问一句答一句"。它可能需要反复调用工具（搜索文件、执行命令），
   经过多个步骤才能完成一个任务（多轮对话 + 多步工具调用）。
   在这个过程中，它需要"记住"：
   • 到目前为止说了什么（messages）
   • 哪些工具调用已经完成了（tool_calls）
   • 哪些改动已经应用了（change_sets）
   • 花了多少 token（usage）
   
   这就是 Session（会话）的概念——它是 Agent 的"短期记忆"。

参考 llm-harness-agent 论文 B2: Generative Agents —— 开创性的 Agent 记忆架构。
该论文证明了：Agent 的可信行为不取决于模型，而取决于记忆和规划架构。
"""

from __future__ import annotations

import json
import os
import tempfile  # 创建临时文件（原子写入，避免写入过程中崩溃导致数据损坏）
import uuid  # 生成唯一 ID
from dataclasses import asdict, dataclass, field  # 数据类
from pathlib import Path
from typing import Any, Callable

from .evidence import redact  # 从证据模块导入脱敏工具

# =============================================================================
# 📋 常量定义
# =============================================================================

# 当前会话 schema 版本号（用于向后兼容——以后升级格式时，可以判断旧版本如何处理）
SESSION_SCHEMA_VERSION = "1.0"
# 工具调用的合法状态集合（只能在这几个状态之间转换）
TOOL_STATES = {"pending", "running", "succeeded", "failed"}


# =============================================================================
# 📝 ToolCallRecord —— 一次工具调用的"体检报告"
# =============================================================================

# ❓ 问：为什么工具调用需要单独的记录（Record）？
# 💡 答：因为工具调用有副作用（修改文件、执行命令），
#   一旦执行了就不能轻易撤销。我们需要记录：
#   1. 调用前 —— 什么参数、预期什么结果
#   2. 调用中 —— 正在执行
#   3. 调用后 —— 成功还是失败、结果是什么
#   这就是"调用生命周期"管理。参考 llm-harness-agent 论文 A1 中
#   Harness 六组件的"生命周期钩子"（Lifecycle Hooks）。

@dataclass
class ToolCallRecord:
    """
    ❓ 问：类比一下，ToolCallRecord 像什么？
    💡 答：像快递的物流跟踪单——
       name = 快递公司（工具名称）
       arguments = 包裹内容（调用参数）
       status = 物流状态（pending=待揽收, running=运输中, succeeded=已签收, failed=退回）
       result = 签收结果
       error = 退回原因
    """
    name: str  # 工具的名称（例如 "read_file"、"search"）
    arguments: dict[str, Any]  # 调用参数（例如 {"input": "README.md"}）
    side_effect: bool  # 是否有副作用？（True=会修改文件/系统，False=只读操作）
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # 本次调用的唯一 ID
    status: str = "pending"  # 当前状态：pending → running → succeeded/failed
    result: Any = None  # 工具返回的结果
    error: str | None = None  # 如果失败，错误信息是什么

    def validate(self) -> None:
        """
        ❓ 问：validate() 检查什么？
        💡 答：确保 status 字段的值是合法的（属于 TOOL_STATES 集合）。
           如果出现了非法值（比如有人手写成了 "done"），立刻报错。
           这叫"防御性编程"——不相信任何人给你的数据都是对的。
        """
        if self.status not in TOOL_STATES:
            raise ValueError(f"unknown tool status: {self.status}")


# =============================================================================
# 📦 SessionState —— Agent 的"完整快照"
# =============================================================================

# ❓ 问：SessionState 包含了 Agent 的哪些信息？
# 💡 答：它是 Agent 运行过程中的"完整快照"——
# 1. session_id —— 唯一标识这次会话
# 2. step —— 当前执行到第几步
# 3. messages —— 所有对话消息
# 4. tool_calls —— 所有工具调用记录
# 5. approvals —— 需要用户批准的操作
# 6. change_sets —— 已经应用的文件修改
# 7. usage —— token 用量统计
# 8. evidence —— 每一步的通信证据

@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)  # 会话唯一 ID
    schema_version: str = SESSION_SCHEMA_VERSION  # Schema 版本号
    step: int = 0  # 当前执行步数
    messages: list[dict[str, Any]] = field(default_factory=list)  # 所有消息
    tool_calls: list[ToolCallRecord] = field(default_factory=list)  # 工具调用记录
    approvals: list[dict[str, Any]] = field(default_factory=list)  # 审批记录
    change_sets: list[dict[str, Any]] = field(default_factory=list)  # 文件修改集
    usage: dict[str, int] = field(default_factory=dict)  # Token 用量
    evidence: list[dict[str, Any]] = field(default_factory=list)  # 通信证据

    def validate(self) -> None:
        """
        ❓ 问：validate() 检查哪些事情？
        💡 答：三个检查：
           1. schema 版本是否匹配（防止加载了旧版本的数据）
           2. step 不能是负数
           3. 所有 tool_calls 的 status 都合法
        """
        if self.schema_version != SESSION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported session schema version: {self.schema_version}"
            )
        if self.step < 0:
            raise ValueError("session step must be non-negative")
        for call in self.tool_calls:
            call.validate()

    def to_dict(self) -> dict[str, Any]:
        """
        ❓ 问：to_dict() 做了哪些事？
        💡 答：三步走——
           1. 先验证状态是否合法
           2. 转换成普通字典（用 dataclasses.asdict）
           3. 脱敏（把敏感字段替换成 [REDACTED]）
           这样输出的结果可以安全地写入文件或日志。
        """
        self.validate()
        return redact(asdict(self))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionState":
        """
        ❓ 问：from_dict() 是 to_dict() 的逆操作吗？
        💡 答：是的。to_dict() 把对象变成字典（序列化），
           from_dict() 把字典变回对象（反序列化）。
           这个模式在计算机里叫"序列化/反序列化"——
           你把对象保存到文件时需要序列化，从文件读取时需要反序列化。

        参考 llm-harness-agent 论文 B4: Reflexion —— 状态持久化机制。
        """
        # 检查 schema 版本
        if value.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported session schema version: {value.get('schema_version')}"
            )
        # 从字典重建 SessionState 对象
        state = cls(
            session_id=str(value["session_id"]),
            schema_version=str(value["schema_version"]),
            step=int(value.get("step", 0)),
            messages=list(value.get("messages", [])),
            # 把每个 tool_calls 字典转成 ToolCallRecord 对象
            tool_calls=[
                ToolCallRecord(**call) for call in value.get("tool_calls", [])
            ],
            approvals=list(value.get("approvals", [])),
            change_sets=list(value.get("change_sets", [])),
            usage=dict(value.get("usage", {})),
            evidence=list(value.get("evidence", [])),
        )
        # 验证重建后的状态是否合法
        state.validate()
        return state


# =============================================================================
# 💾 SessionStore —— 会话的"档案柜"
# =============================================================================

# ❓ 问：SessionState 是内存中的数据，怎么持久化到磁盘？
# 💡 答：SessionStore 负责把 SessionState 保存成 JSON 文件，或者从 JSON 文件加载。
#   每个会话对应一个文件：{session_id}.json
#   保存过程使用"原子写入"（先写临时文件，再重命名）——确保即使写入过程中断电，
#   也不会留下一半的文件。

class SessionStore:
    """
    ❓ 问：类比一下，SessionStore 像什么？
    💡 答：像图书馆的档案室——
       每本书（SessionState）都有一个索书号（session_id），
       放在一个专门的架子上（root 目录）。
       你可以把书存进去（save），也可以取出来（load）。

    参考 llm-harness-agent 论文 D1: Memory Mechanism Survey ——
    讨论了 Agent 记忆的存储、检索和持久化机制。
    """

    def __init__(self, root: Path):
        """
        ❓ 问：root 参数是什么？
        💡 答：会话文件的存放目录。默认是 .deepseek-runtime/sessions/
           这个目录一般放在项目的根目录下。
        """
        self.root = root  # 会话文件存放的根目录
        self.root.mkdir(parents=True, exist_ok=True)  # 确保目录存在

    def path(self, session_id: str) -> Path:
        """
        ❓ 问：path() 函数做了哪些安全检查？
        💡 答：三个检查——
           1. session_id 不能为空
           2. session_id 只能包含字母、数字、下划线、连字符
           3. 限制字符集可以防止"路径遍历攻击"
           什么是路径遍历攻击？如果 session_id 是 "../../etc/passwd"，
           不加检查的话，就能读取到系统密码文件了！
        """
        if not session_id or any(
            character
            not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in session_id
        ):
            raise ValueError("invalid session id")
        return self.root / f"{session_id}.json"

    def save(self, state: SessionState) -> Path:
        """
        ❓ 问：save() 为什么用"临时文件 + 重命名"模式？
        💡 答：这叫"原子写入"（Atomic Write）——
           1. 先在同一个目录下创建一个临时文件（.temp）
           2. 写入全部数据
           3. 调用 fsync() 确保数据真正落盘
           4. 最后用 os.replace() 替换目标文件
           
           好处：如果写入过程中程序崩溃，临时文件会被自动清理，
           而目标文件要么是完整的旧版本，要么是完整的新版本——永远不会是"半成品"。
        """
        destination = self.path(state.session_id)  # 确定目标路径
        # 序列化成 JSON 字符串（排序 key，漂亮的缩进）
        payload = (
            json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
            + "\n"
        )
        # 创建临时文件（前缀用点 + 目标文件名，方便识别）
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=self.root
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()  # 刷新缓冲区
                os.fsync(handle.fileno())  # 强制写入磁盘
            # 用 os.replace 替换目标文件（原子操作）
            os.replace(temp_name, destination)
        finally:
            # 无论成功还是失败，都删除临时文件
            Path(temp_name).unlink(missing_ok=True)
        return destination

    def load(self, session_id: str) -> SessionState:
        """
        ❓ 问：load() 做了哪些错误处理？
        💡 答：
           1. 如果文件内容是非法 JSON（解析失败）→ 报错"corrupt session checkpoint"
           2. 如果 JSON 不是一个字典 → 报错"root must be an object"
           3. 如果 schema 版本不匹配 → from_dict() 会报错
           所有这些错误都是 ValueError 类型，调用方可以根据需要捕获。
        """
        try:
            value = json.loads(
                self.path(session_id).read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupt session checkpoint: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("corrupt session checkpoint: root must be an object")
        return SessionState.from_dict(value)


# =============================================================================
# 🔄 resume_tool_calls —— 中断后恢复工具调用
# =============================================================================

# ❓ 问：如果 Agent 在执行工具调用时中断了（比如断电），怎么恢复？
# 💡 答：resume_tool_calls() 函数处理的就是这个场景。
#   它遍历 state 中所有工具调用记录：
#   1. 如果状态是 "succeeded" → 跳过（已经完成了）
#   2. 如果状态是 "pending" → 重新执行
#   3. 如果状态是 "failed" → 自动重试
#
# 参考 llm-harness-agent 论文 B4: Reflexion —— 通过"反思"（Reflection）
# 机制，Agent 可以从失败中学习并重试，而无需重新开始。

def resume_tool_calls(
    state: SessionState,
    handlers: dict[str, Callable[[dict[str, Any]], Any]],
    save: Callable[[SessionState], object] | None = None,
) -> SessionState:
    """
    ❓ 问：参数 save 是做什么的？
    💡 答：这是一个"回调函数"——每次工具调用状态发生变化时，
       都会调用 save() 来持久化当前状态。
       这样即使后续的工具调用失败了，已经完成的调用结果也不会丢失。
       这叫"断点续传"（Checkpoint Resume）。

    ❓ 问：handlers 是什么？
    💡 答：工具名 → 处理函数的映射。
       比如 {"read_file": read_file_handler, "search": search_handler}。
       当 Agent 需要调用 "read_file" 时，就从 handlers 中找到对应的函数来执行。
    """
    # 遍历每条工具调用记录
    for call in state.tool_calls:
        call.validate()  # 先验证状态是否合法
        if call.status == "succeeded":
            # 已经成功的调用跳过（避免重复执行有副作用的操作）
            continue

        # 标记为"正在运行"
        call.status = "running"
        if save:
            save(state)  # 持久化当前状态（断点）

        try:
            # 调用对应的处理函数
            call.result = handlers[call.name](call.arguments)
            call.error = None  # 清除之前的错误
            call.status = "succeeded"  # 标记成功
        except Exception as exc:
            # 任何异常都记录为失败
            call.error = f"{type(exc).__name__}: {exc}"
            call.status = "failed"

        if save:
            save(state)  # 再次持久化（保存执行结果）

    return state
