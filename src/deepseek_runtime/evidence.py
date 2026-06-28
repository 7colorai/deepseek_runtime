"""
证据层（Evidence Layer）—— 什么是"证据"？为什么要设计这一层？

❓ 问：AI Agent 调用 DeepSeek API 之后，我们怎么证明"我真的调用了"？
❓ 问：如果 response 里含有模型内部的推理过程（thinking/reasoning），
   我们能不能直接存起来？会不会有隐私风险？
❓ 问：有没有一种方法，既能证明"这个请求长什么样"，又不把敏感信息泄露出去？

💡 答：evidence.py 就是答案。它定义了一组"安全地记录证据"的工具函数。
   它的核心哲学来自 llm-harness-agent（论文数据库 B4: Reflexion，
   以及 A1: Agent Harness Survey）：
   「证据必须可验证，但同时必须可安全公开」。
   你不需要存原始内容，只需要存内容的"指纹"（hash）就够了。
"""

from __future__ import annotations  # 让 Python 支持在类型注解中使用自身类名（后向兼容）

import hashlib  # Python 自带的哈希工具，用来给数据生成唯一的"指纹"
import json  # 用来处理 JSON 数据（DeepSeek API 的请求/响应都是 JSON 格式）
from typing import Any  # 声明"任何类型"，Python 的类型提示工具


# =============================================================================
# 🧩 常量定义 —— 什么是"敏感数据"？
# =============================================================================

# ❓ 问：为什么要把内容标记为 [REDACTED]（已脱敏）？
# 💡 答：当你不确定某个字段是否安全时，与其冒险泄露，不如直接替换成这个标记。
#   这就像把机密文件的文字涂黑，只让人看到"这里原来有字"。
#   参考 llm-harness-agent 论文 A1，Harness 六组件中的"安全/沙箱"层。
REDACTED = "[REDACTED]"

# ❓ 问：哪些字段是"敏感"的，必须被隐藏？
# 💡 答：API Key（密钥）、Authorization（认证头）、reasoning_content（模型的思考过程）。
#   DeepSeek V4/V3 的 response 里可能包含 reasoning_content，这是模型内部的"心路历程"，
#   不应该被写到日志或公开证据里。参考 llm-harness-agent/physical-traits 文档中的
#   "Reasoning-content hygiene"（思考过程卫生规范）。
SENSITIVE_KEYS = {"authorization", "api_key", "reasoning_content"}


# =============================================================================
# 🔧 核心工具函数 —— 给数据打"指纹"和"编码"
# =============================================================================

def wire_json(value: Any) -> bytes:
    """
    ❓ 问：什么是 wire_json？为什么叫"wire"（电线）？
    💡 答：wire 指的是"在网络上传输"时的样子。这个函数把任意 Python 数据
       （字典、列表等）转换成网络传输用的字节流。
       它和普通的 json.dumps 有什么区别？
       答：它用逗号和冒号做分隔符（去掉多余空格），确保同样的数据每次都生成
       完全相同的字节序列。这一点对"指纹"计算至关重要。
       参考 llm-harness-agent 论文 C1: ToolLLM，工具调用的序列化格式。
    """
    # separators=(",", ":") 去掉 JSON 的空白字符，让序列化结果紧凑且确定
    # ensure_ascii=False 允许输出中文等非 ASCII 字符
    # .encode("utf-8") 把字符串变成字节（网络传输或哈希计算都需要字节）
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def canonical_json(value: Any) -> str:
    """
    ❓ 问：canonical（规范的/标准的）JSON 又是什么？
    💡 答：wire_json 追求紧凑，canonical_json 追求"可读且稳定"。
       它会按 key 的字母顺序排序（sort_keys=True），这样不管你怎么调整字典里
       字段的顺序，最终生成的字符串都是一样的。
       这在做"证据对比"时非常有用——你可以比较两次请求是否"本质上相同"。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """
    ❓ 问：SHA-256 是什么？为什么用它？
    💡 答：SHA-256 是一种"哈希算法"——不管输入多大的数据，它都输出一个固定长度
       （64个字符）的十六进制字符串。而且：
       • 同样的输入 → 同样的输出（确定性）
       • 输入稍微改一点 → 输出完全不同（雪崩效应）
       • 几乎不可能从输出反推出输入（单向性）
       所以我们可以用它来给数据生成"指纹"（fingerprint）。
       就像你的身份证号一样，你不用展示全部信息，只要报出这个号就能唯一标识。
       参考 llm-harness-agent 论文 B4: Reflexion，证据哈希验证机制。
    """
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: Any) -> str:
    """
    ❓ 问：fingerprint（指纹）函数做了什么？
    💡 答：它把任意数据 → 转成 wire 字节 → 算 SHA-256 → 返回 64 字符指纹。
       三步走：先序列化、再哈希。
       效果：你输入 {"name": "hello"}，输出是一个字符串比如 "a1b2c3..."。
       从输出你无法猜到输入内容，但你可以用它来验证"这是同一个数据"。
    """
    # 第一步：把数据转成网络传输用的字节
    # 第二步：对字节计算 SHA-256 哈希
    return sha256_bytes(wire_json(value))


# =============================================================================
# 🔒 脱敏（Redaction）—— 如何安全地输出证据？
# =============================================================================

def redact(value: Any) -> Any:
    """
    ❓ 问：redact（脱敏/编辑隐藏）函数做了什么？
    💡 答：它递归地遍历数据，把所有"敏感字段"的值替换成 [REDACTED]。
       就像一个自动化的"马赛克工具"，专门给敏感信息打码。
       比如输入：{"api_key": "sk-123", "messages": [{"content": "hi"}]}
       输出：{"api_key": "[REDACTED]", "messages": [{"content": "hi"}]}
       
       参考 llm-harness-agent 论文 A1 中关于"安全发布证据"的讨论：
       「发布证据必须经过脱敏检查，任何敏感信息都不应该出现在公共日志中。」
    """
    # 如果是字典，遍历每个 key
    if isinstance(value, dict):
        return {
            # 如果 key 的小写形式在敏感词集合里 → 替换成 REDACTED
            # 否则 → 递归处理 value（防止嵌套的数据里也有敏感信息）
            key: (REDACTED if key.lower() in SENSITIVE_KEYS else redact(item))
            for key, item in value.items()
        }
    # 如果是列表，对每一项递归脱敏
    if isinstance(value, list):
        return [redact(item) for item in value]
    # 其他类型（字符串、数字等）→ 保留原样
    return value


# =============================================================================
# 📋 响应证据（Response Evidence）—— API 返回了什么？
# =============================================================================

# ❓ 问：为什么需要"响应证据"？
# 💡 答：当 DeepSeek API 返回一个响应后，我们不能直接存原始的 response body，
#   因为里面可能包含 reasoning_content（模型思考过程）。
#   但我们需要证明"我确实收到了一个响应，并且我知道它的结构"。
#   所以 response_evidence() 提取的是"结构证据"而不是"内容"。


def response_evidence(body: dict[str, Any]) -> dict[str, Any]:
    """
    ❓ 问：这个函数具体提取了哪些"结构证据"？
    💡 答：
       1. top_level_fields —— 响应顶层有哪些字段（比如 choices, usage, id 等）
       2. choices —— 每个候选答案的结构：
          - finish_reason（为什么停止生成）
          - message_fields（消息里有哪些字段）
          - tool_names（模型想调用哪些工具）
          - has_content（有没有真正的内容）
          - content_sha256（内容的 SHA-256 指纹，而不是内容本身！）
          - content_bytes（内容的字节大小）
          - has_reasoning_content（是否包含思考过程——只记"有无"，不记内容）
       
       这种设计哲学来自 llm-harness-agent 的"Reasoning-content hygiene"：
       「你可以证明 thinking 环节发生过，但你不必（也不应该）记录 thinking 的内容。」
    """
    # 准备一个空列表，用来装每个 choice（候选答案）的证据
    choices = []

    # 遍历 response body 中的 choices 数组
    for choice in body.get("choices", []):
        # 从 choice 中提取 message（回复消息），确保它是字典
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        # 获取消息的 content（文本内容）
        content = message.get("content")
        # 把 content 转成 wire 字节（用于计算指纹和大小）
        content_bytes = wire_json(content) if content is not None else b""

        # 把当前 choice 的结构证据添加到列表中
        choices.append(
            {
                # 模型为什么停止生成？（stop=正常停止，length=超长截断，tool_calls=要调用工具）
                "finish_reason": choice.get("finish_reason"),
                # message 里有哪些字段（按字母排序，方便对比）
                "message_fields": sorted(message),
                # 模型想调用哪些工具的名字
                "tool_names": [
                    call.get("function", {}).get("name")
                    for call in message.get("tool_calls") or []
                ],
                # 有没有真正的内容文本？（True/False）
                "has_content": bool(message.get("content")),
                # 内容的 SHA-256 指纹（不是内容本身！）
                "content_sha256": sha256_bytes(content_bytes) if content is not None else None,
                # 内容的字节数（用来估计成本或判断大小）
                "content_bytes": len(content_bytes),
                # 是否包含 thinking/reasoning 内容？（只记"有/无"）
                # 🔥 永远不记录 reasoning_content 的值！这是安全红线
                "has_reasoning_content": bool(message.get("reasoning_content")),
            }
        )

    # 返回完整的响应证据
    return {
        # 响应顶层有哪些字段（排序后方便对比不同响应）
        "top_level_fields": sorted(body),
        # 每个候选答案的结构证据
        "choices": choices,
    }


# =============================================================================
# 📤 请求证据（Request Evidence）—— 我们发送了什么？
# =============================================================================

# ❓ 问：那请求（request）的证据又是什么？
# 💡 答：当 DeepSeekRuntime 向 API 发送请求时，我们也需要记录"请求长什么样"，
#   而不存储 prompt 的原文。request_evidence() 做的是：
#   • 记录每条消息的 role（角色：user/assistant/system/tool）
#   • 记录每条消息的字段列表
#   • 记录内容的指纹（而不是内容本身）
#   • 记录模型名称、thinking 模式、工具定义等"元信息"


def request_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """
    ❓ 问：这和 response_evidence 有什么区别？
    💡 答：response_evidence 记录"API 给了什么"，request_evidence 记录"我们发了什么"。
       两者合起来就构成了一个完整的"通信证据链"。
       
       这对应 llm-harness-agent 理论中 Harness 的"执行循环"（Execution Loop）组件
       ——你需要记录循环的每一步输入和输出，才能追溯问题。
    """
    # 准备一个空列表，存储每条消息的结构摘要
    messages = []

    # 遍历 payload（请求体）中的 messages 数组
    for message in payload.get("messages", []):
        # 获取消息的内容
        content = message.get("content")
        # 转成字节（用于哈希和大小计算）
        content_bytes = wire_json(content) if content is not None else b""

        # 为每条消息建立结构摘要
        messages.append(
            {
                # 角色：user（用户）、assistant（AI）、system（系统指令）、tool（工具结果）
                "role": message.get("role"),
                # 消息里有哪些字段（按字母排序）
                "fields": sorted(message),
                # 内容的指纹（不是内容本身！）
                "content_sha256": sha256_bytes(content_bytes) if content is not None else None,
                # 内容的字节数
                "content_bytes": len(content_bytes),
                # 是否包含 reasoning_content（思考过程）
                "has_reasoning_content": bool(message.get("reasoning_content")),
                # 如果是 AI 回复，它想调用哪些工具
                "tool_names": [
                    call.get("function", {}).get("name")
                    for call in message.get("tool_calls") or []
                ],
            }
        )

    # 返回完整的请求结构摘要
    return {
        # 请求体顶层有哪些字段
        "top_level_fields": sorted(payload),
        # 使用的模型名称（如 deepseek-v4-flash）
        "model": payload.get("model"),
        # 每条消息的结构摘要
        "messages": messages,
        # 请求中定义的工具名称列表
        "tool_names": [
            tool.get("function", {}).get("name")
            for tool in payload.get("tools") or []
        ],
        # 是否启用了 thinking 模式
        "thinking": payload.get("thinking"),
        # 推理强度（effort）级别
        "reasoning_effort": payload.get("reasoning_effort"),
        # 是否使用流式（stream）传输
        "stream": payload.get("stream", False),
    }
