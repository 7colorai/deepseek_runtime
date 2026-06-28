# =============================================================================
# test_client_runtime.py — DeepSeek Runtime 客户端与运行时测试
# =============================================================================
# ❓ 问：这个文件是干什么的？
# 💡 答：这是一个测试文件，用来验证 DeepSeek Runtime 的"客户端"（负责调用 AI 模型 API）
#    和"运行时"（负责执行整个 AI Agent 流程）是否正常工作。
#    它使用了 Python 内置的 unittest 测试框架。
#
# 论文引用：llm-harness-agent 论文 B1: ReAct 提出了"思考-行动-观察"的 Agent 循环范式，
# 本测试验证的就是这种循环中"行动"（调用 LLM API）和"观察"（处理返回结果）两个环节的正确性。
# 参考 A1: Agent Harness Survey — 测试工具链是 Agent 系统可靠性的基石。
# =============================================================================

from __future__ import annotations
# ❓ 问：这一行是什么意思？
# 💡 答：from __future__ import annotations 是 Python 的一个"未来特性导入"。
#    它让代码中的类型注解（比如 list[dict[str, Any]]）在运行时不会被求值，
#    而是作为字符串保存。这样做的好处是：1）避免循环导入问题；
#    2）允许在旧版 Python 中使用新版注解语法。简单说就是"让类型注解更灵活、更安全"。

import json
# ❓ 问：为什么要导入 json？
# 💡 答：json 是 Python 内置的 JSON 处理库。在 AI Agent 场景中，
#    AI 模型的请求和响应数据都是 JSON 格式（就像一张结构化的表格），
#    所以我们需要 json 来把 Python 对象转换成 JSON 字符串（序列化），
#    或者把 JSON 字符串解析成 Python 对象（反序列化）。
#    论文参考 A1: Agent Harness Survey — JSON 是 Agent 系统中最通用的数据交换格式。

import unittest
# ❓ 问：unittest 是什么？
# 💡 答：unittest 是 Python 标准库中的测试框架。它让我们可以写"测试用例"（TestCase），
#    每个用例验证代码的一个行为。如果一个用例失败了，就说明代码有 bug。
#    对非技术 PM 的理解：就像一份"检查清单"，每项打个 ✓ 或 ✗，
#    确保软件发布前所有功能都正常。

from pathlib import Path
# ❓ 问：Path 是什么？
# 💡 答：Path 来自 pathlib 模块，是 Python 中处理文件路径的现代方式。
#    以前用字符串处理路径（比如 "folder/file.txt"），容易出错。
#    Path 对象提供更安全、更直观的方法来操作文件和目录。
#    比如 Path(".") 表示"当前目录"，可以 .read_text() 读文件内容。

from typing import Any
# ❓ 问：Any 是什么意思？
# 💡 答：Any 是 typing（类型注解）模块中的一个特殊类型，表示"可以是任何类型"。
#    在代码中写 calls: list[dict[str, Any]] 意思是"calls 是一个列表，
#    里面每个元素是字典（dict），字典的值可以是任何东西"。
#    这帮助开发者理解数据结构，但不会强制限制实际值。

from deepseek_runtime.client import DeepSeekClient, ProviderResult, RuntimeSettings
# ❓ 问：这行导入了什么？
# 💡 答：从 deepseek_runtime.client 模块导入了三个重要的东西：
#    - DeepSeekClient：AI 模型的客户端，负责发送请求到 DeepSeek API
#    - ProviderResult：AI 模型提供商返回的结果对象
#    - RuntimeSettings：运行时的配置设置（比如 API 密钥、模型名称等）
#    论文参考 B7: AgentBench — Agent 与 LLM API 的交互是基准测试的核心环节。

from deepseek_runtime.evidence import response_evidence
# ❓ 问：response_evidence 是什么？
# 💡 答：这是从 DeepSeek Runtime 的证据模块中导入的一个函数。
#    它的作用是从 AI 模型的响应中提取"证据"——也就是关键信息，
#    同时自动隐藏敏感内容（比如隐私数据或模型的推理过程）。
#    这样既能用于调试，又不会泄露敏感信息。
#    论文参考 B1: ReAct — Agent 需要从环境（LLM 响应）中提取观察结果作为证据。

from deepseek_runtime.runtime import DeepSeekRuntime, WorkspaceTools
# ❓ 问：这里又导入了什么？
# 💡 答：从 deepseek_runtime.runtime（运行时模块）导入：
#    - DeepSeekRuntime：整个运行时环境的核心类，负责协调 Agent 的执行流程
#    - WorkspaceTools：工作区工具管理器，它知道 Agent 可以在工作区中使用哪些工具
#      （比如读取文件、搜索内容等）


class ClientRuntimeTests(unittest.TestCase):
    # ❓ 问：这个类的作用是什么？
    # 💡 答：ClientRuntimeTests 是一个测试类，继承自 unittest.TestCase。
    #    它包含多个测试方法，每个方法测试一个特定的功能点。
    #    PM 理解方式：就像一份"质检报告"，每个章节检查产品的不同方面。
    #    论文参考 A1: Agent Harness Survey — 系统化的测试套件是 Agent 框架成熟度的标志。

    def test_client_chat_builds_official_endpoint_request(self) -> None:
        # ❓ 问：这个测试方法要验证什么？
        # 💡 答：它要验证 DeepSeekClient 是否正确地构建了发送到 DeepSeek 官方 API 的请求。
        #    具体来说，它检查请求的方法（POST）、URL 地址、认证头（Authorization）、
        #    请求体中的模型名称和消息内容是否都正确。
        #    论文参考 B1: ReAct — Agent 的"行动"步骤需要正确调用外部工具（这里是 LLM API）。

        calls: list[dict[str, Any]] = []
        # ❓ 问：创建一个空列表做什么？
        # 💡 答：calls 是一个列表，用来"记录"每次调用传输层（transport）的信息。
        #    测试会用一个"假的"传输函数代替真正的网络请求，
        #    每次调用这个假函数时，我们会把调用的参数保存到 calls 列表中，
        #    最后检查这些参数是否符合预期。

        def transport(method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float):
            # ❓ 问：这个 transport 函数是干什么的？
            # 💡 答：这是一个"模拟传输层"函数（也叫 mock 函数）。
            #    在真实场景中，DeepSeekClient 会通过 HTTP 网络协议发送请求到 DeepSeek 的服务器。
            #    但在测试中，我们不想真的发送网络请求（因为需要网络、API 密钥等），
            #    所以我们用这个模拟函数来"假装"发送请求，并返回一个假的响应。
            #    它的参数（method, url, headers, data, timeout）就是真实请求会用的参数。

            calls.append({"method": method, "url": url, "headers": headers, "data": data, "timeout": timeout})
            # ❓ 问：这一行在做什么？
            # 💡 答：把这次调用的所有参数保存到 calls 列表中。
            #    这样测试结束后，我们可以检查 calls[0] 来确认
            #    客户端是否正确地构造了请求。
            #    论文参考 A1: Agent Harness Survey — Mock 测试是 Agent 系统测试的主要方法之一。

            body = {"choices": [{"message": {"role": "assistant", "content": "answer"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}}
            # ❓ 问：这个 body 是什么格式？
            # 💡 答：这是一个模拟的 AI 模型响应体（JSON 格式）。
            #    真实的 DeepSeek API 返回格式是这样的：
            #    - choices: 模型生成的回复列表（每个回复是一个 choice）
            #    - message: 包含 role（角色：assistant）和 content（回复内容）
            #    - finish_reason: 为什么停止生成（"stop" 表示正常结束）
            #    - usage: 用量统计，total_tokens 表示用了多少个"词元"（Token）

            return 200, {"x-request-id": "req-1"}, json.dumps(body).encode()
            # ❓ 问：返回的是什么？
            # 💡 答：模拟的 HTTP 响应，包含三个部分：
            #    1）状态码 200 — 表示 HTTP 请求成功
            #    2）响应头（headers）— 包含请求 ID "req-1"
            #    3）响应体（body）— 经过 json.dumps() 转换成 JSON 字符串，
            #       再用 .encode() 编码成字节数据（bytes），模拟真实的网络传输

        client = DeepSeekClient(RuntimeSettings(api_key="secret", base_url="https://api.deepseek.com", model="deepseek-v4-flash"), transport=transport)
        # ❓ 问：这行在做什么？
        # 💡 答：创建一个 DeepSeekClient 实例，并传入两个参数：
        #    1）RuntimeSettings — 运行时配置，包括：
        #       - api_key="secret"（API 密钥，测试中用 "secret" 代替真实密钥）
        #       - base_url="https://api.deepseek.com"（API 的基础地址）
        #       - model="deepseek-v4-flash"（使用的模型名称）
        #    2）transport=transport — 传入我们自定义的模拟传输函数
        #    这样客户端就不会真的发送网络请求，而是调用我们的 transport 函数。
        #    论文参考 B1: ReAct — Agent 的"工具调用"需要配置正确的 API 端点。

        result = client.chat({"messages": [{"role": "user", "content": "hello"}]})
        # ❓ 问：client.chat() 是在做什么？
        # 💡 答：调用客户端的聊天方法，传入一个消息字典。
        #    这个消息表示：用户（user）发送了消息 "hello"。
        #    客户端会把这个消息打包成 API 请求，通过 transport 函数"发送"出去，
        #    然后返回一个 ProviderResult 对象（保存了 API 的响应结果）。

        self.assertEqual(result.status, 200)
        # ❓ 问：这个断言在检查什么？
        # 💡 答：检查 result.status（响应状态码）是否等于 200。
        #    200 表示 HTTP 请求成功。如果不等于 200，测试失败，说明有问题。
        #    self.assertEqual() 是 unittest 提供的方法，
        #    如果两个值不相等，测试就会报错。

        self.assertEqual(result.request_id, "req-1")
        # ❓ 问：为什么检查 request_id？
        # 💡 答：检查响应中的请求 ID 是否等于 "req-1"。
        #    这个 ID 是我们在模拟传输函数中返回的。
        #    确认客户端正确地从响应头中提取了请求 ID。

        self.assertEqual(calls[0]["method"], "POST")
        # ❓ 问：这里在检查什么？
        # 💡 答：检查第一次传输调用使用的是 POST 方法。
        #    对 AI API 的请求通常使用 HTTP POST 方法（而非 GET），
        #    因为 POST 可以发送包含消息内容的请求体（body）。

        self.assertEqual(calls[0]["url"], "https://api.deepseek.com/chat/completions")
        # ❓ 问：URL 为什么是这个？
        # 💡 答：检查请求发送到了正确的 API 端点。
        #    DeepSeek 的聊天补全 API 路径是 /chat/completions，
        #    加上基础地址（base_url）就是完整的 URL。
        #    论文参考 B7: AgentBench — Agent 系统需要正确配置 LLM API 端点。

        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret")
        # ❓ 问：Authorization 头是做什么的？
        # 💡 答：检查 HTTP 请求头中的 Authorization（授权）字段。
        #    "Bearer secret" 是一种标准的认证方式：
        #    - Bearer 是认证类型（持有者令牌）
        #    - secret 就是 API 密钥
        #    这告诉服务器："我有权限访问这个 API，我的密钥是 secret"

        payload = json.loads(calls[0]["data"])
        # ❓ 问：这里在做什么？
        # 💡 答：从传输记录中取出 data（请求体），用 json.loads() 解析成 Python 字典。
        #    因为数据在传输时是字节格式（bytes），需要反序列化才能读取内容。

        self.assertEqual(payload["model"], "deepseek-v4-flash")
        # ❓ 问：检查 model 字段干什么？
        # 💡 答：确认请求体中指定的模型名称是 "deepseek-v4-flash"，
        #    和 RuntimeSettings 中配置的一致。
        #    这样可以确保客户端正确地把配置传递给了 API 请求。

        self.assertEqual(payload["messages"][0]["content"], "hello")
        # ❓ 问：为什么检查消息内容？
        # 💡 答：确认发送给 API 的消息内容确实是 "hello"。
        #    这样验证了从用户输入到 API 请求的整个传递链是正确的。

    def test_runtime_safe_dict_does_not_include_prompt_or_response_text(self) -> None:
        # ❓ 问：这个测试要验证什么安全特性？
        # 💡 答：测试运行时的"安全字典"功能。
        #    DeepSeek Runtime 提供了一个 to_safe_dict() 方法，
        #    它会返回一个"安全版本"的结果字典——其中不包含用户的提示词（prompt）
        #    和 AI 的回复内容，以防止敏感信息泄露到日志中。
        #    而 to_dict(include_content=True) 则包含所有内容（用于调试）。
        #    论文参考 A1: Agent Harness Survey — Agent 系统的安全审计要求敏感数据脱敏。

        class FakeClient:
            # ❓ 问：为什么又创建一个假客户端？
            # 💡 答：FakeClient 是一个模拟的客户端类，用来替代真实的 DeepSeekClient。
            #    它只有一个 chat 方法，返回一个预设的 ProviderResult。
            #    这样测试运行时就不用真的调用 AI 模型，测试更快、更可靠。

            def chat(self, payload: dict[str, Any]) -> ProviderResult:
                # ❓ 问：这个 chat 方法返回什么？
                # 💡 答：它直接返回一个 ProviderResult 对象，包含模拟的 API 响应：
                #    - status=200（成功）
                #    - elapsed_ms=1（耗时 1 毫秒）
                #    - body 中包含一个 choices 列表，其中 assistant 回复了 "private answer"
                #    - request_fingerprint="abc"（请求指纹，用于追踪）
                #    - request_payload=payload（保存原始请求负载）
                return ProviderResult(
                    status=200,
                    elapsed_ms=1,
                    body={"choices": [{"message": {"role": "assistant", "content": "private answer"}, "finish_reason": "stop"}], "usage": {"total_tokens": 7}},
                    request_fingerprint="abc",
                    request_payload=payload,
                )

        runtime = DeepSeekRuntime(FakeClient())  # type: ignore[arg-type]
        # ❓ 问：创建一个 DeepSeekRuntime 实例？
        # 💡 答：用 FakeClient 创建一个 DeepSeekRuntime 实例。
        #    注释 "# type: ignore[arg-type]" 告诉类型检查器忽略这里的类型不匹配警告，
        #    因为 FakeClient 不完全符合 DeepSeekClient 的类型定义，但我们知道它能工作。

        result = runtime.run([{"role": "user", "content": "private prompt"}], workspace=Path("."))
        # ❓ 问：runtime.run() 在做什么？
        # 💡 答：调用运行时的 run 方法，传入一个用户消息 "private prompt"，
        #    工作区设置为当前目录（"."）。
        #    运行时内部会调用 client.chat() 并与工作区交互，
        #    最后返回一个 RunResult 对象。

        safe = json.dumps(result.to_safe_dict(), ensure_ascii=False)
        # ❓ 问：to_safe_dict() 是什么？
        # 💡 答：result.to_safe_dict() 返回一个"安全字典"版本的运行结果。
        #    这个安全字典会自动移除敏感内容（提示词和回复），
        #    适合写入日志或审计记录。
        #    ensure_ascii=False 确保非 ASCII 字符（如中文）不被转义。
        #    论文参考 A1: Agent Harness Survey — 安全审计要求 Agent 系统能输出脱敏的日志。

        raw = json.dumps(result.to_dict(include_content=True), ensure_ascii=False)
        # ❓ 问：to_dict(include_content=True) 和上面的有什么区别？
        # 💡 答：这个调用返回"完整字典"版本，include_content=True 表示包含所有内容
        #    （包括提示词和回复）。这个版本仅用于本地调试，不适合写入日志，
        #    因为可能包含敏感信息。

        self.assertTrue(result.ok)
        # ❓ 问：检查 result.ok 是什么意思？
        # 💡 答：result.ok 是一个布尔值，表示运行是否成功完成。
        #    self.assertTrue() 检查该值是否为 True。
        #    如果运行时执行出错，ok 就是 False。

        self.assertNotIn("private prompt", safe)
        # ❓ 问：这个断言在验证什么安全特性？
        # 💡 答：验证在安全字典（safe）中不包含 "private prompt"（用户的提示词）。
        #    这是安全性的关键——即使用户的提示词包含敏感信息，
        #    安全字典也不会泄露它。

        self.assertNotIn("private answer", safe)
        # ❓ 问：这个呢？
        # 💡 答：验证安全字典中也不包含 AI 的回复 "private answer"。
        #    有些 AI 回复可能包含商业机密或个人数据，同样需要保护。

        self.assertIn("private prompt", raw)
        # ❓ 问：为什么完整字典要包含提示词？
        # 💡 答：在完整字典（raw）中，"private prompt" 应该存在。
        #    这样在本地调试时才能看到完整的输入输出，排查问题。
        #    这三个断言一起验证了：安全字典"确实脱敏了"，完整字典"确实保留了内容"。

        self.assertIn("private answer", raw)
        # ❓ 问：同理，这里验证什么？
        # 💡 答：验证完整字典中包含 AI 的回复 "private answer"。
        #    如果 raw 中也没有，那说明内容在传输过程中丢失了，这也是 bug。

    def test_runtime_reports_malformed_provider_response(self) -> None:
        # ❓ 问：这个测试要测什么错误场景？
        # 💡 答：测试当 AI 模型提供商返回的响应格式不正确时，
        #    运行时能否正确识别并报告"malformed provider response"（格式错误的提供商响应）错误。
        #    这很重要：AI API 有时会返回异常格式的数据，
        #    系统需要优雅地处理而不是崩溃。
        #    论文参考 B1: ReAct — Agent 需要能够处理异常的工具返回结果。

        class FakeClient:
            # ❓ 问：这次 FakeClient 返回了什么不一样的东西？
            # 💡 答：这次返回的 body 中，choices 列表是空的（[]）。
            #    正常情况应该至少有一个 choice 包含 AI 的回复。
            #    空 choices 就是一种"格式错误"的响应。

            def chat(self, payload: dict[str, Any]) -> ProviderResult:
                return ProviderResult(status=200, elapsed_ms=1, body={"choices": []}, request_fingerprint="abc", request_payload=payload)

        result = DeepSeekRuntime(FakeClient()).run([{"role": "user", "content": "hello"}], workspace=Path("."))  # type: ignore[arg-type]
        # ❓ 问：这里发生了什么？
        # 💡 答：创建 DeepSeekRuntime 实例（使用 FakeClient），然后立即调用 run() 方法。
        #    这是一行链式调用（不需要中间变量）。传入用户消息 "hello"，
        #    工作区为当前目录。

        self.assertFalse(result.ok)
        # ❓ 问：为什么 result.ok 是 False？
        # 💡 答：因为 AI 返回的响应格式有问题（空 choices），
        #    运行时应该检测到这个问题并将 result.ok 设为 False。
        #    这是正确的行为——系统诚实报告了异常，而不是假装成功。

        self.assertEqual(result.error, "malformed provider response")
        # ❓ 问：检查 error 字段做什么？
        # 💡 答：验证 result.error 字段包含 "malformed provider response" 错误消息。
        #    这样上层代码可以根据不同的错误类型做出不同的处理（比如重试、记录日志、通知用户）。

    def test_response_evidence_hides_reasoning_content(self) -> None:
        # ❓ 问：这个测试关于什么功能？
        # 💡 答：测试 response_evidence() 函数是否能正确隐藏 AI 模型的"推理内容"。
        #    深度思考模型（如 DeepSeek-R1）在给出最终答案前，
        #    会有一段内部推理过程（reasoning_content），其中可能包含未加工的敏感信息。
        #    response_evidence() 函数会把这个推理内容替换成一个标记 "has_reasoning_content"，
        #    既不泄露推理细节，又告知调用方"这里原本有推理内容"。
        #    论文参考 A1: Agent Harness Survey — Agent 系统的安全审计需要处理中间推理过程的数据脱敏。

        evidence = response_evidence(
            # ❓ 问：response_evidence() 的输入是什么？
            # 💡 答：传入一个完整的 AI 响应字典，其中：
            #    - content: "visible"（可见的最终回复）
            #    - reasoning_content: "hidden reasoning"（隐藏的推理过程）
            #    - finish_reason: "stop"（正常结束）
            #    函数会处理这个字典并返回一个新的"证据"字典。

            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "visible", "reasoning_content": "hidden reasoning"},
                        "finish_reason": "stop",
                    }
                ]
            }
        )

        serialized = json.dumps(evidence, ensure_ascii=False)
        # ❓ 问：为什么序列化证据字典？
        # 💡 答：把 evidence 字典转成 JSON 字符串，方便后续用 assertIn/assertNotIn
        #    检查字符串中是否包含某些关键词。

        self.assertIn("has_reasoning_content", serialized)
        # ❓ 问：为什么"has_reasoning_content"应该存在？
        # 💡 答：检查序列化后的证据中是否包含 "has_reasoning_content"。
        #    这个标记告诉调用方：原始响应中有推理内容，只是被隐藏了。
        #    这提供了一种"透明度"——你知道有内容被隐藏了，但看不到具体内容。

        self.assertNotIn("hidden reasoning", serialized)
        # ❓ 问：为什么"hidden reasoning"不应该存在？
        # 💡 答：确认原始的推理内容 "hidden reasoning" 被成功隐藏了。
        #    如果它出现在证据中，说明脱敏失败，敏感信息被泄露了。

        self.assertNotIn("visible", serialized)
        # ❓ 问：为什么连"visible"（可见的回复）也没有？
        # 💡 答：response_evidence() 不仅隐藏推理内容，也会隐藏最终的回复内容。
        #    它只提取元数据（是否有推理内容、返回码等），而不包含实际的消息文本。
        #    这是一种"最小化信息泄露"的安全设计。

    def test_workspace_tools_accept_string_root(self) -> None:
        # ❓ 问：这个简单测试验证什么？
        # 💡 答：验证 WorkspaceTools（工作区工具）能否接受一个字符串形式的根路径。
        #    WorkspaceTools 通常接受 Path 对象，但也要兼容字符串参数，
        #    因为用户可能直接从命令行传入字符串路径。
        #    论文参考 B1: ReAct — Agent 的工具调用接口需要灵活易用。

        tools = WorkspaceTools(".").catalog()
        # ❓ 问：这行做了什么？
        # 💡 答：用字符串 "."（表示当前目录）创建 WorkspaceTools 实例，
        #    然后调用 catalog() 方法返回所有可用工具的目录（列表）。
        #    如果 WorkspaceTools 不能正确处理字符串参数，这里会报错。

        self.assertIn("read_file", tools)
        # ❓ 问：为什么检查 read_file 工具？
        # 💡 答：验证返回的工具列表中包含 "read_file"（读取文件）工具。
        #    read_file 是工作区工具中的基本工具之一。
        #    如果它不在列表中，说明 catalog() 方法可能有问题。


if __name__ == "__main__":
    # ❓ 问：这个条件判断是什么意思？
    # 💡 答：if __name__ == "__main__" 是 Python 中的一个惯用写法。
    #    __name__ 是当前模块的名称。当文件被直接运行时，__name__ 等于 "__main__"；
    #    当文件被其他模块导入时，__name__ 等于文件名（不包括 .py）。
    #    所以这段代码只在"直接运行本文件"时执行，导入时不会运行。

    unittest.main()
    # ❓ 问：unittest.main() 做什么？
    # 💡 答：自动发现并运行当前模块中所有继承自 unittest.TestCase 的测试方法。
    #    运行结果会在控制台输出：通过（.）、失败（F）或错误（E）。
    #    PM 理解：相当于一键执行所有质检项目，自动生成质检报告。
