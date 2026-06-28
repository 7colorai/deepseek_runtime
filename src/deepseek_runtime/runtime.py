"""
运行时层（Runtime Layer）—— Agent 的"大脑"，决定怎么思考、怎么行动

❓ 问：DeepSeekRuntime 到底做了什么？
💡 答：它执行一个"思考→行动→观察"的循环（ReAct Loop），
   就像是给 AI 装上了一个"决策轮盘"——
   1. 把用户的问题发给 DeepSeek API
   2. API 可能回复文字，也可能回复"我要调用这个工具"
   3. 如果是工具调用 → 在本地执行工具 → 把结果发给 API
   4. 重复 2-3 步，直到 API 给出最终答案或达到步骤上限

❓ 问：这个循环和 llm-harness-agent 有什么关系？
💡 答：这就是 llm-harness-agent 论文 B1: ReAct 的核心思想——
   「推理（Reasoning）和行动（Acting）交替进行，互相促进」。
   这篇 ICLR 2023 的论文是几乎所有现代 Agent 系统的理论基础。

   同时，这个 runtime.py 也是 A1: Agent Harness Survey 中
   定义的 Harness "执行循环"（Execution Loop）组件的具体实现：
   它管理上下文（Context Manager）、调度工具（Tool Registry）、
   记录状态（State Store），构成了 Agent 执行的基础设施。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .client import DeepSeekClient
from .diagnostics import build_diagnostics
from .evidence import redact, request_evidence, response_evidence, sha256_bytes, wire_json


# ===== ToolHandler（工具处理器）=====

# ❓ 问：什么是 ToolHandler？
# 💡 答：它是一个函数的"模板"——接受一个字典参数，返回一个字符串。
#   所有工具函数都必须符合这个"形状"（签名）。
#   这就像万能插座：不管什么电器，只要插头符合规格就能用。
ToolHandler = Callable[[dict[str, Any]], str]


# ===== RuntimeResult（运行时结果）=====

@dataclass
class RuntimeResult:
    """
    ❓ 问：一次 Agent 运行会产生什么结果？
    💡 答：一个 RuntimeResult 包含了运行的所有产出——
       - ok：任务是否成功完成
       - final_text：最终的回复文字
       - messages：整个对话过程中所有的消息（用户的 + AI 的 + 工具的）
       - usage：总共花了多少 token
       - evidence：每一步的请求/响应证据
       - diagnostics：运行时的系统诊断信息
       - error/error_class：如果失败，错误信息和类型
       - status：HTTP 状态码
       - step：总共执行了多少步
    """
    ok: bool  # 任务是否成功
    final_text: str = ""  # AI 的最终回复
    messages: list[dict[str, Any]] = field(default_factory=list)  # 所有消息
    usage: dict[str, int] = field(default_factory=dict)  # Token 用量统计
    evidence: list[dict[str, Any]] = field(default_factory=list)  # 通信证据
    diagnostics: dict[str, Any] = field(default_factory=dict)  # 系统诊断
    error: str | None = None  # 错误信息
    error_class: str | None = None  # 错误类型
    status: int | None = None  # HTTP 状态码
    step: int = 0  # 执行步数

    def _text_summary(self, value: str | None) -> dict[str, Any]:
        """把文本内容转换成"安全摘要"——只记录哈希和大小，不记录原文"""
        if not value:
            return {"present": False, "sha256": None, "bytes": 0}
        raw = wire_json(value)
        return {"present": True, "sha256": sha256_bytes(raw), "bytes": len(raw)}

    def to_safe_dict(self) -> dict[str, Any]:
        """
        安全地输出结果——不包含 prompt 和 response 的原文。
        这是默认的输出模式，适合写入日志或发布为证据。

        参考 llm-harness-agent physical-traits 文档中关于"Redacted release evidence"的要求：
        所有公开证据必须经过脱敏处理。
        """
        return {
            "ok": self.ok,
            "final_text": self._text_summary(self.final_text),  # 只有 hash，没有原文
            "message_count": len(self.messages),
            "message_evidence": request_evidence({"messages": self.messages})["messages"],
            "usage": self.usage,
            "evidence": redact(self.evidence),  # 脱敏
            "diagnostics": redact(self.diagnostics),  # 脱敏
            "error": self.error,
            "error_class": self.error_class,
            "status": self.status,
            "step": self.step,
        }

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        """根据 include_content 参数决定是否输出原文"""
        if include_content:
            return redact(asdict(self))
        return self.to_safe_dict()


# ===== DeepSeekRuntime（Agent 运行时）=====

# ❓ 问：类比一下，DeepSeekRuntime 像什么？
# 💡 答：像工厂的"生产线"——
#   原材料（用户的问题）从一端进入生产线，
#   经过多个工作站（每一步的 thinking + tool call），
#   最终从另一端产出成品（AI 的回答）。
#   每个工作站都有质检员（evidence 记录）和计数器（usage统计）。

@dataclass
class DeepSeekRuntime:
    """
    核心 Agent 运行时，执行 ReAct 循环（推理→行动→观察）。

    ❓ 问：max_steps = 8 是什么意思？
    💡 答：这是"循环上限"——Agent 最多能调用 8 次工具。
       为什么需要上限？因为 AI 可能陷入死循环（一直调用工具不停止）。
       设置上限就像给生产线设置"最多处理 8 道工序"的安全阀门。

    参考 llm-harness-agent 论文 B1: ReAct (ICLR 2023) ——
    推理与行动交替的循环结构。
    """
    client: DeepSeekClient  # DeepSeek API 客户端
    max_steps: int = 8  # 最大工具调用步数

    def run(
        self,
        messages: list[dict[str, Any]],
        workspace: str | Path = ".",
        tools: dict[str, ToolHandler] | None = None,
    ) -> RuntimeResult:
        """
        ❓ 问：run() 方法的主要执行流程是什么？
        💡 答：六步循环——
           第1步：把用户消息和工具定义发送给 DeepSeek API
           第2步：检查 API 是否返回了工具调用请求
           第3步：如果有工具调用 → 在本地执行对应的工具函数
           第4步：把工具执行结果发给 API
           第5步：重复第2步
           第6步：如果 API 直接回复了文本 → 结束循环，返回结果

        参考 llm-harness-agent 论文 A1 中 Harness 六组件模型的"执行循环"组件。
        """
        workspace_path = Path(workspace)
        # 复制一份消息列表，避免修改原始数据
        active_messages = [dict(message) for message in messages]
        active_tools = tools or {}

        # ❓ 问：tool_specs 是做什么的？
        # 💡 答：它把 Python 函数描述成 DeepSeek API 能理解的"工具定义"。
        #   API 需要知道每个工具的：名字、功能描述、需要什么参数。
        #   这样 AI 才知道"什么时候可以用什么工具，以及怎么用"。
        tool_specs = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Run {name}",
                    # API 要求工具参数用 JSON Schema 描述
                    "parameters": {
                        "type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"],
                    },
                },
            }
            for name in sorted(active_tools)
        ]

        total_usage: dict[str, int] = {}
        evidence: list[dict[str, Any]] = []

        # 在运行前收集系统诊断信息
        diagnostics = build_diagnostics(workspace_path)

        # ⚡ ReAct 循环开始
        for step in range(1, self.max_steps + 1):
            # ❓ 问：为什么默认启用 thinking 模式？
            # 💡 答：DeepSeek V4/V3 支持显式的 thinking（思考）模式。
            #   启用后，模型会在给出答案前进行内部推理，质量更高。
            #   这是 llm-harness-agent 论文中讨论的"DeepSeek 物理特性"之一。
            payload: dict[str, Any] = {
                "messages": active_messages,
                "thinking": {"type": "enabled"},
            }
            if tool_specs:
                payload["tools"] = tool_specs

            # 向 DeepSeek API 发送请求
            result = self.client.chat(payload)

            # 累加 token 用量
            for key, value in result.usage.items():
                if isinstance(value, int):
                    total_usage[key] = total_usage.get(key, 0) + value

            # 记录这一步的通信证据
            evidence.append({
                "step": step,
                "status": result.status,
                "elapsed_ms": result.elapsed_ms,
                "request_fingerprint": result.request_fingerprint,
                "request_id": result.request_id,
                "usage": result.usage,
                "request_evidence": request_evidence(result.request_payload or payload),
                "response_evidence": response_evidence(result.body),
                "error": result.error,
                "error_class": result.error_class,
            })

            # 检查 API 返回是否成功
            if result.status != 200:
                return RuntimeResult(
                    False, messages=active_messages, usage=total_usage,
                    evidence=evidence, diagnostics=diagnostics,
                    error=result.error, error_class=result.error_class,
                    status=result.status, step=step,
                )

            # 解析 AI 的回复消息
            try:
                message = result.body["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                return RuntimeResult(
                    False, messages=active_messages, usage=total_usage,
                    evidence=evidence, diagnostics=diagnostics,
                    error="malformed provider response", step=step,
                )

            # 把 AI 的回复追加到对话历史中
            active_messages.append(message)

            # ❓ 问：怎么知道 AI 是"想说答案"还是"想调用工具"？
            # 💡 答：看 message 里有没有 tool_calls 字段——
            #   如果有 tool_calls → AI 想调用工具
            #   如果没有 → AI 在直接回答问题
            calls = message.get("tool_calls") or []

            if not calls:
                # 🎉 AI 直接给出了最终答案！循环结束。
                return RuntimeResult(
                    True,
                    final_text=message.get("content", ""),
                    messages=active_messages,
                    usage=total_usage,
                    evidence=evidence,
                    diagnostics=diagnostics,
                    step=step,
                )

            # 🔧 AI 想调用工具——遍历每个调用
            for call in calls:
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    # 解析 AI 生成的 JSON 参数
                    arguments = json.loads(function.get("arguments") or "{}")
                    # 调用对应的本地工具处理函数
                    output = active_tools[name](arguments)
                except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
                    # 工具调用出错，把错误信息返回给 AI，让它决定怎么处理
                    output = f"Tool error: {type(exc).__name__}: {exc}"

                # 把工具调用的结果追加到对话中
                # role="tool" 告诉 AI："这是你刚才调用的工具返回的结果"
                active_messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": output,
                })
            # 循环回到顶部，把工具结果发给 AI，看它下一步怎么说

        # ⛔ 达到了最大步数限制，AI 还没有给出最终答案
        return RuntimeResult(
            False,
            messages=active_messages,
            usage=total_usage,
            evidence=evidence,
            diagnostics=diagnostics,
            error="maximum steps reached",
            step=self.max_steps,
        )


# ===== WorkspaceTools（工作区工具集）=====

# ❓ 问：如果用户不想自己写工具函数，有没有默认的工具？
# 💡 答：有！WorkspaceTools 提供了两个基本的文件操作工具：
#   1. read_file —— 读取工作区内的文件内容
#   2. search —— 在工作区内搜索关键字
#   开发者可以在此基础上扩展自己的工具集。

@dataclass
class WorkspaceTools:
    """内置的工作区工具集——提供基本的文件读写和搜索能力"""
    root: str | Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    def _path(self, raw: str) -> Path:
        """
        ❓ 问：_path() 做了哪些安全检查？
        💡 答：和 security.py 的 resolve() 类似——
           检查路径是否在工作区内，防止越界读取。
           这叫"路径遍历防护"（Path Traversal Prevention），
           是 Agent 安全的基础要求。
        """
        candidate = (self.root / raw).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes workspace")
        return candidate

    def read_file(self, args: dict[str, Any]) -> str:
        """
        读取文件内容（最多 20000 字符）。
        工具名称叫 read_file，供 AI 调用。
        """
        # 从参数中提取 input 作为文件路径
        path = self._path(str(args.get("input", "")))
        return path.read_text(encoding="utf-8")[:20_000]

    def search(self, args: dict[str, Any]) -> str:
        """
        在工作区内搜索关键字（最多返回 100 条结果）。
        工具名称叫 search，供 AI 调用。
        """
        needle = str(args.get("input", ""))
        if not needle:
            raise ValueError("search input must not be empty")
        matches = []
        for path in self.root.rglob("*"):
            if path.is_file() and ".git" not in path.parts and path.stat().st_size < 1_000_000:
                try:
                    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if needle in line:
                            matches.append(f"{path.relative_to(self.root)}:{number}:{line[:200]}")
                            if len(matches) >= 100:
                                return "\n".join(matches)
                except (UnicodeDecodeError, OSError):
                    pass
        return "\n".join(matches) or "No matches"

    def catalog(self) -> dict[str, ToolHandler]:
        """返回工具名称到处理函数的映射字典"""
        return {"read_file": self.read_file, "search": self.search}
