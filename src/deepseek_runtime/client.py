"""
客户端层（Client Layer）—— Runtime 怎么跟 DeepSeek API "打电话"？

❓ 问：一个 AI Agent 要跟大模型对话，最原始的方式是什么？
💡 答：发 HTTP 请求。就像你在浏览器里访问网站一样，只不过这里发送的是
   结构化的 JSON 数据，包含你的问题（messages）和你想要的参数（model、temperature 等）。

❓ 问：那 client.py 做了什么特别的事情？
💡 答：它不仅仅是"发请求"——
   1. 它记录了请求的"指纹"（fingerprint），用来证明"这个请求确实是我发的"
   2. 它封装了 DeepSeek 特有的功能：thinking 模式、流式传输、工具调用
   3. 它把网络错误变成结构化的 ProviderResult，方便上层处理
   
   参考 llm-harness-agent 论文 A1（Agent Harness Survey）中的定义：
   Harness 的 "执行循环"（Execution Loop）组件——客户端是循环的起始点。
"""

from __future__ import annotations  # 支持在类型注解中使用自身类名

import os  # 读取环境变量（比如 API Key）
import time  # 计时，记录请求耗时
import urllib.error  # 处理 HTTP 错误（如 401 无权限、429 频率限制）
import urllib.request  # Python 自带的 HTTP 客户端，不需要装第三方库
from dataclasses import dataclass, field  # 数据类，自动生成 __init__ 和 __repr__
from typing import Any, Protocol  # 类型提示

from .evidence import sha256_bytes, wire_json  # 从 evidence 导入"指纹"和"序列化"工具


# =============================================================================
# ⚙️ RuntimeSettings —— 运行时配置：该连哪个 API？用什么模型？
# =============================================================================

# ❓ 问：Agent 需要知道哪些"连接信息"才能调用 DeepSeek API？
# 💡 答：就像你要打电话需要知道对方的号码一样，Agent 需要：
#   • api_key —— 你的"电话号码密码"（认证密钥）
#   • base_url —— 服务地址（DeepSeek 的官方地址）
#   • model —— 用哪个模型（v4-flash 还是 v4-pro）
#   • timeout —— 等多久算超时
#   • max_tokens —— 一次最多回复多少个 token（可以理解为"字数上限"）

@dataclass(frozen=True)  # frozen=True 表示这个类的实例创建后就不能修改了（不可变）
class RuntimeSettings:
    """
    ❓ 问：为什么 settings 要做成"不可变"的？
    💡 答：因为这些配置在整个 Runtime 运行期间不应该被意外修改。
       就像你打电话时不会中途换号码一样。
       如果谁都能改 api_key，代码就会变得不安全、不可预测。
    """
    api_key: str = field(repr=False)  # repr=False 表示打印对象时隐藏这个字段的值（防泄露！）
    base_url: str = "https://api.deepseek.com"  # DeepSeek API 的官方地址
    model: str = "deepseek-v4-flash"  # 默认模型（快速且便宜）
    timeout: float = 120.0  # 请求超时时间（120 秒）
    max_tokens: int = 512  # 每次最多输出 512 个 token

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        """
        ❓ 问：为什么设计 from_env() 这个方法？
        💡 答：因为 API Key 是敏感信息，不能硬编码在代码里。
           从环境变量读取是行业标准做法——你只需要在终端设置一次：
           export DEEPSEEK_API_KEY=sk-xxx
           然后整个程序就能读到它了。
           这参考了 12-Factor App 方法论（"把配置存到环境中"）。

        参考 llm-harness-agent 论文 C1: ToolLLM —— 工具调用的认证管理。
        """
        # 从环境变量 DEEPSEEK_API_KEY 读取 API Key
        key = os.getenv("DEEPSEEK_API_KEY", "")
        # 如果没设置，直接报错——没有 Key 就没法调用 API
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is required for live DeepSeek requests")
        return cls(
            api_key=key,
            # 允许用 DEEPSEEK_BASE_URL 覆盖默认地址（比如使用代理）
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            # 允许用 DEEPSEEK_MODEL 指定模型
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            # 超时时间和最大 token 数也可以从环境变量配置
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "120")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "512")),
        )


# =============================================================================
# 📦 ProviderResult —— API 调用的"快递包裹"
# =============================================================================

# ❓ 问：API 返回的数据长什么样？怎么容纳"成功"和"失败"两种情况？
# 💡 答：用一个统一的结构来装所有返回信息。
#   不管成功还是失败，都打包成一个 ProviderResult。
#   成功时：status=200, body={"choices": [...], "usage": {...}}
#   失败时：status=非200或0, error="错误描述"

@dataclass
class ProviderResult:
    """
    ❓ 问：类比一下，ProviderResult 像什么？
    💡 答：像你网购后收到的快递包裹——
       status 是快递状态（已到达/运输中/丢失），
       body 是包裹里的商品（API 返回的数据），
       error 是运单上的备注（如果有问题会写上原因）。
    """
    status: int  # HTTP 状态码（200=成功，4xx=请求错误，5xx=服务器错误，0=网络不通）
    elapsed_ms: int  # 请求花了多少毫秒（用来衡量性能）
    body: dict[str, Any]  # API 返回的 JSON 数据体
    request_fingerprint: str  # 请求的 SHA-256 指纹（用来证明"这是同一个请求"）
    error: str | None = None  # 错误信息（没有错误就是 None）
    error_class: str | None = None  # 错误类型（http/transport/timeout）
    request_id: str | None = None  # 请求的唯一 ID（来自服务器返回的 x-request-id 头）
    request_payload: dict[str, Any] | None = None  # 原始请求体（用于生成请求证据）

    @property
    def usage(self) -> dict[str, Any]:
        """
        ❓ 问：usage 是什么？
        💡 答：Token 用量——这次请求花了多少 token？
           就像跑了多少公里要记里程一样。
           token 是 AI 模型的"里程数"：输入要花钱，输出要花钱，
           缓存命中能省钱。usage 包含了所有这些信息。

        参考 llm-harness-agent 论文 A1 中关于成本可观测性的讨论：
        「缓存可见性和任务成功率、成本应该在同一证据流里。」
        """
        # 从 body 中提取 usage 字段，如果 body 不是字典则返回空字典
        return self.body.get("usage", {}) if isinstance(self.body, dict) else {}


# =============================================================================
# 📡 Transport —— 底层 HTTP 传输协议（可以替换）
# =============================================================================

# ❓ 问：什么是 Transport（传输层）？
# 💡 答：Transport 就是"怎么发送 HTTP 请求"的具体实现。
#   默认用 Python 内置的 urllib（不需要装任何额外库）。
#   但在测试时可以替换成假的 Transport——不真的发请求，而是模拟返回数据。
#   这种设计叫"依赖注入"（DI），是 llm-harness-agent 论文 A2: AIOS
#   中的"模块化架构"思想。

class Transport(Protocol):
    """
    ❓ 问：Protocol 是什么？
    💡 答：Python 的"协议"（接口）。它定义了 Transport 应该长什么样——
       任何满足这个签名的函数都可以当做 Transport 使用。
       就像"只要是能加油的车都能开"一样，这里有"能发 HTTP 请求的函数都能用"。
    """
    def __call__(
        self, method: str, url: str, headers: dict[str, str],
        data: bytes | None, timeout: float
    ) -> tuple[int, dict[str, str], bytes]:
        """
        参数说明：
        - method: HTTP 方法（GET/POST）
        - url: 请求地址
        - headers: 请求头（包含 Authorization、Content-Type 等）
        - data: 请求体（POST 时发送的 JSON 字节）
        - timeout: 超时秒数
        
        返回：
        - 状态码（int）
        - 响应头（dict）
        - 响应体（bytes）
        """
        ...


class StreamTransport(Protocol):
    """
    ❓ 问：流式传输（Stream）和普通传输有什么区别？
    💡 答：普通传输像一口气喝完一整瓶水——等全部数据到了再处理。
       流式传输像用吸管喝——数据一点一点地到，你一边喝一边感觉。
       对于 AI 对话来说，流式传输让用户能看到"模型正在生成"，体验更好。
    """
    def __call__(
        self, method: str, url: str, headers: dict[str, str],
        data: bytes | None, timeout: float
    ) -> tuple[int, dict[str, str], list[tuple[int, bytes]]]:
        """
        返回的不再是整个响应体，而是一个"分块列表"：
        - 每个块 = (收到该块的时间戳(毫秒), 块内容(bytes))
        - 用时间戳可以计算"首字延迟"——用户等了多久才看到第一个字
        
        参考 llm-harness-agent physical-traits 文档中的"Streaming chunks"特性。
        """
        ...


# =============================================================================
# 🔌 默认 HTTP 传输实现（用 Python 自带的 urllib）
# =============================================================================

def urllib_transport(
    method: str, url: str, headers: dict[str, str],
    data: bytes | None, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    """
    ❓ 问：urllib 是什么？
    💡 答：Python 自带的网络请求库。不需要 pip install 任何东西。
       它就像你的"基本款手机"——能打电话（发请求）也能接电话（收响应）。
       虽然不如 requests 库好用，但好处是零依赖。

    参考 llm-harness-agent 论文 C3: OpenHands —— 零外部依赖的 Agent 核心。
    """
    # 构造 Request 对象（指定 URL、请求体、方法、请求头）
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        # 发送请求并等待响应（with 语句确保连接被正确关闭）
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # 返回：状态码, 响应头字典, 响应体字节
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        # HTTP 错误（如 401 无权限、429 频率限制）——也返回响应体供分析
        return exc.code, dict(exc.headers.items()), exc.read()


def urllib_stream_transport(
    method: str, url: str, headers: dict[str, str],
    data: bytes | None, timeout: float
) -> tuple[int, dict[str, str], list[tuple[int, bytes]]]:
    """
    ❓ 问：流式传输的实现和普通传输有什么不同？
    💡 答：关键不同在于"逐行读取"——
       普通传输：等待全部数据返回
       流式传输：一边收到数据行，一边处理（逐行迭代 response 对象）
    """
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    started = time.monotonic()  # 记录开始时间（monotonic 时钟不会因为系统时间调整而跳动）
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            # 遍历响应的每一行，记录每行到达的时间戳(毫秒)
            chunks = [
                (round((time.monotonic() - started) * 1000), line)
                for line in response
            ]
            return response.status, dict(response.headers.items()), chunks
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), [
            (round((time.monotonic() - started) * 1000), exc.read())
        ]


# =============================================================================
# 🎯 DeepSeekClient —— DeepSeek API 的"翻译官"
# =============================================================================

# ❓ 问：为什么需要 DeepSeekClient？
# 💡 答：它把"发 HTTP 请求"这个底层操作，翻译成了 Python 程序员能直接调用的方法：
#   • client.chat({...}) —— 发送一条对话请求
#   • client.chat_stream({...}) —— 发送一条流式对话请求
#   • client.models() —— 查询可用模型列表
#   你不需要关心 HTTP、JSON、URL 这些细节，只需要告诉它"我想做什么"。

class DeepSeekClient:
    """
    ❓ 问：这个类的设计哲学是什么？
    💡 答：它把 HTTP 通信的两层分开了：
       • 上层（你看到的）：chat(), chat_stream(), models() —— 业务方法
       • 下层（可替换的）：transport, stream_transport —— 网络传输
       上层的业务逻辑（怎么构造请求、怎么解析响应）是固定的，
       下层的传输实现（用 urllib 还是 requests）是可替换的。
       这就是"关注点分离"（Separation of Concerns）——每个组件只关心自己的事。
    """

    def __init__(
        self,
        settings: RuntimeSettings,
        transport: Transport = urllib_transport,
        stream_transport: StreamTransport = urllib_stream_transport,
    ):
        """
        ❓ 问：为什么要允许替换 transport？
        💡 答：为了测试！
           在实际运行时，用 urllib_transport 真正发请求。
           但在测试时，可以传入一个"假的 transport"，不真的发请求，
           而是返回预设的数据。这样测试就不需要网络连接了。
        """
        self.settings = settings  # 保存运行时配置（API Key、模型等）
        self.transport = transport  # 普通传输实现
        self.stream_transport = stream_transport  # 流式传输实现

    def models(self) -> ProviderResult:
        """
        ❓ 问：models() 是做什么的？
        💡 答：查询 DeepSeek 有哪些模型可用。相当于问："你支持什么车型？"
           调用的是 GET /models 接口。
        """
        return self._request("GET", "/models", None)

    def chat(self, payload: dict[str, Any]) -> ProviderResult:
        """
        ❓ 问：chat() 是做什么的？
        💡 答：最核心的方法——发送一次对话请求。
           调用的是 POST /chat/completions 接口。
           它会自动合并默认的 model 和 max_tokens 设置。

        参数 payload 的结构示例：
        {
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好！有什么可以帮你的？"}
            ],
            "thinking": {"type": "enabled"},  # 启用思考模式
            "tools": [...]  # 可选：工具定义
        }
        """
        # 合并默认设置：在 payload 的基础上加上 model 和 max_tokens
        complete = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            **payload  # payload 中的字段会覆盖前面的默认值
        }
        return self._request("POST", "/chat/completions", complete)

    def chat_stream(self, payload: dict[str, Any]) -> ProviderResult:
        """
        ❓ 问：chat_stream() 和 chat() 的核心区别是什么？
        💡 答：chat() 等全部结果返回后再解析。
           chat_stream() 使用 SSE（Server-Sent Events，服务器推送事件）协议，
           数据会一个 chunk 一个 chunk 地到达。
           
           这个方法不仅返回最终结果，还返回流式传输的"结构证据"：
           • event_count —— 一共收到了多少个事件
           • first_event_ms —— 多久收到了第一个事件（首字延迟）
           • top_level_fields —— 所有事件的外层字段
           • delta_fields —— delta 中的字段（content、tool_calls 等）
           
        参考 llm-harness-agent physical-traits 中关于流式传输的讨论。
        """
        # 在 payload 中添加 stream: true 开启流式模式
        complete = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            **payload,
            "stream": True  # 这个字段告诉 DeepSeek："请流式返回"
        }
        # 序列化请求体（生成稳定的字节序列用于指纹计算）
        data = wire_json(complete)
        # 计算请求的 SHA-256 指纹
        request_hash = sha256_bytes(data)
        started = time.monotonic()

        try:
            # 发送流式请求
            status, headers, chunks = self.stream_transport(
                "POST",
                self.settings.base_url + "/chat/completions",
                {
                    # Bearer Token 认证——把 API Key 放在请求头里
                    "Authorization": f"Bearer {self.settings.api_key}",
                    "Content-Type": "application/json",
                    # Accept: text/event-stream 告诉服务器"我支持流式响应"
                    "Accept": "text/event-stream",
                },
                data,
                self.settings.timeout,
            )

            # 解析 SSE 事件流
            events: list[dict[str, Any]] = []
            first_event_ms = None
            for offset_ms, raw in chunks:
                # 把字节解码成字符串（如果解码失败用 ? 代替非法字符）
                line = raw.decode(errors="replace").strip()
                # SSE 协议中，数据行以 "data:" 开头
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()  # 去掉 "data:" 前缀
                if value == "[DONE]":  # SSE 的结束标记
                    continue
                try:
                    import json
                    event = json.loads(value)  # 解析 JSON 事件
                except ValueError:
                    continue  # 解析失败就跳过（可能是空行或心跳包）
                # 记录第一个事件的时间（即流式响应的"首字延迟"）
                first_event_ms = offset_ms if first_event_ms is None else first_event_ms
                events.append(event)

            # ❓ 问：为什么还要从事件中提取 usage？
            # 💡 答：在流式传输中，token 用量（usage）通常在最后一个事件里才出现。
            #   reversed(events) 从后往前找，找到第一个带 usage 的事件。
            usage = next(
                (event.get("usage", {}) for event in reversed(events) if event.get("usage")),
                {}
            )

            # 提取所有 events 中的 choices（候选回复）
            choices = [
                choice
                for event in events
                for choice in event.get("choices", [])
                if isinstance(choice, dict)
            ]
            # 提取 delta（增量数据）——流式传输中每次只返回一小部分
            deltas = [
                choice.get("delta", {})
                for choice in choices
                if isinstance(choice.get("delta", {}), dict)
            ]

            # 构造流式响应的"结构证据"
            body = {
                "usage": usage,
                "stream_evidence": {
                    "event_count": len(events),  # 总事件数
                    "first_event_ms": first_event_ms,  # 首字延迟（毫秒）
                    # 所有事件中出现过的顶层字段
                    "top_level_fields": sorted({key for event in events for key in event}),
                    # delta 中出现的字段
                    "delta_fields": sorted({key for delta in deltas for key in delta}),
                    # 所有 finish_reason（停止原因）
                    "finish_reasons": sorted({
                        str(choice.get("finish_reason"))
                        for choice in choices
                        if choice.get("finish_reason") is not None
                    }),
                    "has_content": any(bool(delta.get("content")) for delta in deltas),
                    # 是否出现了 reasoning_content（思考过程）
                    "has_reasoning_content": any(
                        bool(delta.get("reasoning_content")) for delta in deltas
                    ),
                    # 工具调用名称列表
                    "tool_names": sorted({
                        str(call.get("function", {}).get("name"))
                        for delta in deltas
                        for call in delta.get("tool_calls") or []
                        if call.get("function", {}).get("name")
                    }),
                },
            }
            error = None if status < 400 else "stream request failed"
            error_class = None if status < 400 else "http"
            # 从响应头中提取请求 ID（用于追踪问题）
            request_id = headers.get("x-request-id") or headers.get("X-Request-Id")

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # 网络错误（DNS 解析失败、连接超时、连接被断开等）
            status, body = 0, {"error": {"message": str(exc)}}
            error, error_class, request_id = str(exc), "transport", None

        # ❓ 问：为什么 ProviderResult 的 elapsed_ms 在这里计算？
        # 💡 答：在整个请求过程的开头就记了 started，结束时 elapsed_ms = 当前时间 - started。
        #   这样不管中间经历了什么（重试、流式解析），耗时都算进去了。
        return ProviderResult(
            status,
            round((time.monotonic() - started) * 1000),
            body,
            request_hash,
            error,
            error_class,
            request_id,
            complete,
        )

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> ProviderResult:
        """
        ❓ 问：_request 是内部方法（以下划线开头），它做了什么？
        💡 答：它是 chat() 和 models() 的"共享骨架"——
           所有 HTTP 请求的共同流程：
           1. 序列化请求体 → 2. 计算指纹 → 3. 发送请求 → 4. 解析响应 → 5. 返回结果

        ❓ 问：为什么指纹在前面计算而不是在后面？
        💡 答：因为我们要在发送请求前就确定"我发出了什么"的指纹。
           如果等请求完成后才计算，那计算的就是"响应"而不是"请求"了。
        """
        import json  # 在这里导入，避免在文件顶部导入所有地方都用不到的模块

        # 如果有 payload，序列化成 JSON 字节；没有则传 None（比如 GET 请求）
        data = wire_json(payload) if payload is not None else None
        # 计算请求体的 SHA-256 指纹
        request_hash = sha256_bytes(data or b"")
        started = time.monotonic()

        try:
            # 通过 transport 发送 HTTP 请求
            status, headers, raw = self.transport(
                method,
                self.settings.base_url + path,
                {
                    "Authorization": f"Bearer {self.settings.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                data,
                self.settings.timeout,
            )
            try:
                # 把响应体（字节）解析成 Python 字典
                body = json.loads(raw)
            except json.JSONDecodeError:
                # 如果响应不是合法的 JSON，也记录下原始内容
                body = {"error": {"message": raw.decode(errors="replace")}}

            # HTTP 状态码 >= 400 表示有错误
            error = body.get("error", {}).get("message") if status >= 400 else None
            error_class = "http" if status >= 400 else None
            # DeepSeek API 会在响应头中返回 x-request-id，用于追踪
            request_id = headers.get("x-request-id") or headers.get("X-Request-Id")

        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # 网络层出错（DNS 解析失败、连接超时等）
            status = 0
            body = {"error": {"message": str(exc)}}
            error = str(exc)
            error_class = "transport"
            request_id = None

        return ProviderResult(
            status,
            round((time.monotonic() - started) * 1000),
            body,
            request_hash,
            error,
            error_class,
            request_id,
            payload,
        )
