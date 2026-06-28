"""
DeepSeek Runtime 的"大门"——包初始化文件

❓ 问：什么是 __init__.py？
💡 答：当你在 Python 中写 from deepseek_runtime import XXX 时，
   Python 就会执行这个文件。它决定了哪些类、函数可以被外部访问。

❓ 问：这个文件做了什么事？
💡 答：两件事——
   1. 从各个模块导入核心的公开 API
   2. 定义 __all__ 列表，明确告诉使用者"哪些是公共的、稳定的 API"
   
   参考 llm-harness-agent 论文 C1: ToolLLM 中的模块化设计理念：
   每个模块只暴露必要的接口，内部实现可以随时重构而不影响使用者。
"""

# 从各个子模块导入公开的 API
from .client import DeepSeekClient, ProviderResult, RuntimeSettings
from .diagnostics import build_diagnostics
from .observability import summarize_observability
from .runtime import DeepSeekRuntime, RuntimeResult, WorkspaceTools
from .security import (
    ChangeManager, ChangeSet, Decision, FileChange, PermissionPolicy,
    PermissionRequest, PermissionRule, Risk, RollbackToken,
    WorkspaceSandbox, content_sha256,
)
from .session import SessionState, resume_tool_calls

# 当前版本号（Alpha 版本）
# ❓ 问：0.1.1a1 代表什么？
# 💡 答：0.1.1 是版本号，a1 是 Alpha 1 测试版。
#   还不是正式版，API 可能还会有变化。
__version__ = "0.1.1a1"

# ❓ 问：__all__ 是什么？
# 💡 答：它声明了"这个包的公共 API 清单"。
#   当用户写 from deepseek_runtime import * 时，
#   只会导入 __all__ 里列出的名字。
#   不在列表里的就是"内部实现"，不保证稳定性。
__all__ = [
    "__version__",
    "ChangeManager",
    "ChangeSet",
    "DeepSeekClient",
    "DeepSeekRuntime",
    "Decision",
    "FileChange",
    "PermissionPolicy",
    "PermissionRequest",
    "PermissionRule",
    "ProviderResult",
    "Risk",
    "RollbackToken",
    "RuntimeResult",
    "RuntimeSettings",
    "SessionState",
    "WorkspaceSandbox",
    "WorkspaceTools",
    "build_diagnostics",
    "content_sha256",
    "resume_tool_calls",
    "summarize_observability",
]
