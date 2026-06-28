# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 这是 shebang（释伴行），告诉操作系统用环境中的 python3 解释器来运行这个脚本。
#    当你在终端里直接执行 ./live_api_smoke.py 时，系统靠这行找到 Python。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是什么意思？
# 💡 一个"未来导入"，让 Python 把类型注解（如 list[str]）当作字符串延迟求值。
#    好处是运行时性能更好，且支持前向引用（forward reference）。
#    这是 Python 3.7+ 项目的常见写法。
from __future__ import annotations

# ❓ 为什么导入这些标准库模块？
# 💡 每个模块负责一项基础能力：
#    - argparse：解析命令行参数（--out 输出路径）
#    - json：序列化结果到 JSON 格式
#    - os：读取环境变量（如 DEEPSEEK_REASONING_EFFORT）
#    - sys：操作 Python 导入路径
#    - datetime/timezone：生成 UTC 时间戳
#    - pathlib.Path：面向对象路径操作
#    - typing.Any：动态类型注解
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ❓ ROOT 和 SRC 是怎么确定的？为什么要操作 sys.path？
# 💡 ROOT 是项目根目录（当前脚本的父目录的父目录）。
#    SRC 是项目 src 子目录（源码所在位置）。
#    下面三行检查 SRC 是否已经在 Python 的模块搜索路径 sys.path 中，
#    如果不在，就把它插入到最前面（索引 0）。
#    这样脚本就可以直接 import deepseek_runtime 包了。
#    参考 llm-harness-agent 论文 C3 (OpenHands) 中关于运行时路径管理的讨论。
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ❓ from ... import 这几行在做什么？
# 💡 从 deepseek_runtime 包中导入运行客户端和脱敏工具：
#    - DeepSeekClient: 与 DeepSeek API 通信的 HTTP 客户端
#    - RuntimeSettings: 运行时配置（API 密钥、模型名、端点地址等）
#    - request_evidence: 从请求中提取脱敏证据（不保留敏感内容）
#    - response_evidence: 从响应中提取脱敏证据
#    - sha256_bytes: 计算字节数据的 SHA-256 哈希
#    - wire_json: 将 Python 对象编码为 JSON 字节串
# 这整个脚本的设计理念是：只记录脱敏的结构化证据，绝不记录 API 密钥或完整对话内容。
from deepseek_runtime.client import DeepSeekClient, RuntimeSettings
from deepseek_runtime.evidence import request_evidence, response_evidence, sha256_bytes, wire_json


# ❓ SMOKE_PROMPT 是什么？为什么要用大写命名？
# 💡 大写命名是 Python 的惯例，表示这是一个"常量"（虽然 Python 没有真正的常量）。
#    这个字符串是发送给 DeepSeek API 的系统提示词，要求模型回复一句话确认 API 正常工作。
#    注意措辞 "return one concise sentence" 和 "confirm the official chat endpoint responded"——
#    这不是真正的用户请求，而是一个纯功能性验证请求，用来确认 API 端点可达且正常响应。
SMOKE_PROMPT = "DeepSeek runtime live smoke: return one concise sentence confirming the official chat endpoint responded."


# ❓ _choice_message 这个辅助函数是做什么的？
# 💡 从 API 响应的 body（请求体）中提取出模型回复的消息内容。
#    API 的响应结构是嵌套字典：body["choices"][0]["message"]。
#    "choices" 是一个列表（因为一次请求可能有多个回复候选），我们只取第一个。
#    "message" 是模型回复的消息字典，包含 role（角色）和 content（内容）等字段。
# ❓ try/except 为什么捕获 KeyError, IndexError, TypeError？
# 💡 API 响应可能因为网络问题、服务异常等原因返回非标准格式。
#    KeyError：字典中缺少某个键（如 "choices"）
#    IndexError：列表索引越界（如 choices 是空列表）
#    TypeError：某个值不是预期的类型（如 choices 不是列表）
#    任何异常发生时，函数返回空字典 {}，优雅降级而不是崩溃。
def _choice_message(body: dict[str, Any]) -> dict[str, Any]:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {}
    # ❓ 为什么还要检查 isinstance(message, dict)？
    # 💡 确认取到的 message 确实是一个字典。
    #    API 有时可能返回意外的数据类型，双重保险确保代码健壮。
    return message if isinstance(message, dict) else {}


# ❓ _text_summary 又是做什么的？
# 💡 对一段文本内容生成"脱敏摘要"——不保留文本本身，只记录：
#    - 内容是否存在
#    - 内容的 SHA-256 哈希值（指纹）
#    - 内容的字节长度
#    这样既能证明"API 返回了内容"，又不泄露具体内容（安全/隐私考量）。
def _text_summary(value: Any) -> dict[str, Any]:
    # ❓ 如果 value 不是非空字符串怎么办？
    # 💡 如果 value 不是字符串（比如 None 或数字），或字符串为空，
    #    就返回{"present": False, "sha256": None, "bytes": 0}，表示"内容不存在"。
    if not isinstance(value, str) or not value:
        return {"present": False, "sha256": None, "bytes": 0}
    # ❓ wire_json 是做什么的？
    # 💡 wire_json(value) 把 value 编码为 JSON 格式的字节串（bytes）。
    #    然后用 sha256_bytes 计算这个字节串的 SHA-256 哈希。
    #    len(raw) 得到字节长度。
    #    结果示例：{"present": True, "sha256": "abc123def...", "bytes": 42}
    raw = wire_json(value)
    return {"present": True, "sha256": sha256_bytes(raw), "bytes": len(raw)}


# ❓ run_live_smoke 是核心函数吗？
# 💡 是的。这是整个烟雾测试（smoke test）的核心逻辑：
#    1. 从环境变量中读取运行时设置
#    2. 创建一个 DeepSeek API 客户端
#    3. 构造测试请求负载（payload）
#    4. 调用 API
#    5. 从响应中提取脱敏证据
#    6. 检查是否有敏感信息泄露（API 密钥、提示词、回复内容）
#    7. 返回安全的结构化结果
def run_live_smoke() -> dict[str, Any]:
    # ❓ RuntimeSettings.from_env() 是怎么获取配置的？
    # 💡 这是一个工厂方法（class method），它从环境变量中读取配置：
    #    - DEEPSEEK_API_KEY: API 密钥
    #    - DEEPSEEK_BASE_URL: API 端点地址
    #    - DEEPSEEK_MODEL: 模型名称
    #    这些环境变量通常在 .env 文件或 CI 环境中设置。
    settings = RuntimeSettings.from_env()
    # ❓ DeepSeekClient(settings) 创建了什么？
    # 💡 创建一个配置好的 API 客户端对象，它知道：
    #    - 用哪个 API 密钥认证
    #    - 调哪个 URL 地址
    #    - 请求超时、重试策略等
    client = DeepSeekClient(settings)
    # ❓ payload 里有什么？
    # 💡 这是发送给 DeepSeek API 的请求体（JSON 格式）：
    #    - messages: 对话消息列表
    #      - 第一个是 system 消息：提示模型不要泄露机密信息
    #      - 第二个是 user 消息：SMOKE_PROMPT 测试提示词
    #    - thinking: 启用思维链（chain-of-thought）模式
    #    - reasoning_effort: 推理力度，从环境变量读取，默认 "high"
    #    - stream: 是否流式输出，这里设为 False（一次性返回完整响应）
    payload = {
        "messages": [
            {"role": "system", "content": "You are validating a runtime integration. Do not echo secrets."},
            {"role": "user", "content": SMOKE_PROMPT},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": os.getenv("DEEPSEEK_REASONING_EFFORT", "high"),
        "stream": False,
    }
    # ❓ client.chat(payload) 做了什么？
    # 💡 发送聊天请求到 DeepSeek API，等待响应。
    #    result 包含了：HTTP 状态码、响应体、请求耗时、请求 ID、使用量统计等。
    result = client.chat(payload)
    # ❓ 下面几行在提取什么？
    # 💡 从 API 响应中提取模型的回复内容（content）和推理过程（reasoning_content）。
    #    _choice_message 从响应体中提取消息字典。
    #    .get("content") 获取消息的文本内容（模型的实际回复）。
    #    .get("reasoning_content") 获取模型的推理过程（如果启用思维链的话）。
    message = _choice_message(result.body)
    content = message.get("content")
    reasoning_content = message.get("reasoning_content")
    # ❓ safe_output 字典里包含了什么？
    # 💡 这是一个经过脱敏处理的输出结构，只包含安全可公开的信息：
    #    - schema_version: 数据格式版本号
    #    - created_at: 执行时间戳
    #    - success: 请求成功（HTTP 200）且 content 是字符串
    #    - provider_status: 原始 HTTP 状态码
    #    - elapsed_ms: 请求耗时（毫秒）
    #    - request_id_present: 是否有请求 ID（证明请求确实到了服务端）
    #    - model / base_url: 使用什么模型和端点（不含密钥）
    #    - request_fingerprint: 请求指纹（脱敏标识符）
    #    - request_evidence: 请求的脱敏证据
    #    - response_evidence: 响应的脱敏证据
    #    - usage: Token 使用量统计
    #    - content: 回复内容的摘要（哈希，不保留原文）
    #    - reasoning_content: 推理内容的摘要（哈希，不保留原文）
    #    - error / error_class: 错误信息（如果有的话）
    # 参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于安全日志记录和脱敏的建议。
    safe_output = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": result.status == 200 and isinstance(content, str),
        "provider_status": result.status,
        "elapsed_ms": result.elapsed_ms,
        "request_id_present": bool(result.request_id),
        "model": settings.model,
        "base_url": settings.base_url,
        "request_fingerprint": result.request_fingerprint,
        "request_evidence": request_evidence(result.request_payload or payload),
        "response_evidence": response_evidence(result.body),
        "usage": result.usage,
        "content": _text_summary(content),
        "reasoning_content": _text_summary(reasoning_content),
        "error": result.error,
        "error_class": result.error_class,
    }
    # ❓ rendered = json.dumps(...) 是做什么的？
    # 💡 把 safe_output 序列化成 JSON 字符串，然后检查在 JSON 字符串中是否包含敏感信息。
    #    这是"泄露检测"的关键步骤——我们把所有输出的内容串起来，然后搜索其中有没有不
    #    应该出现的敏感信息。
    rendered = json.dumps(safe_output, ensure_ascii=False)
    # ❓ api_key 是从哪里来的？
    # 💡 设置 settings.api_key 包含 API 密钥（比如 "sk-xxxx..."）。
    #    getattr(settings, 'api_key') 或 settings.api_key 获取这个密钥。
    #    注意：api_key 只用于泄露检测，不会被写入到输出中。
    api_key = settings.api_key
    # ❓ leaks 字典在检查什么？
    # 💡 四项"泄露检查"（leak checks），每项检查是否成功避免泄露：
    #    1. api_key_absent: API 密钥不在输出的 JSON 中（保护密钥）
    #    2. prompt_absent: SMOKE_PROMPT 不在输出的 JSON 中（保护提示词）
    #    3. response_content_absent: 模型回复原文不在输出的 JSON 中（保护响应内容）
    #    4. reasoning_content_absent: 推理过程不在输出的 JSON 中（保护推理内容）
    #    如果任何一项是 False，说明泄露发生了。
    #    注意 "absent" 是"不存在"的意思——True 表示"不存在于输出中"，是好的。
    leaks = {
        "api_key_absent": not api_key or api_key not in rendered,
        "prompt_absent": SMOKE_PROMPT not in rendered,
        "response_content_absent": not isinstance(content, str) or content not in rendered,
        "reasoning_content_absent": not isinstance(reasoning_content, str) or reasoning_content not in rendered,
    }
    # ❓ 为什么要把 leaks 放到 safe_output 中？
    # 💡 把泄露检查结果附加到输出报告中，方便审计人员查看。
    safe_output["leak_checks"] = leaks
    # ❓ 为什么要重新赋值 safe_output["success"]？
    # 💡 原来的 success 只检查了 HTTP 状态码和 content 类型是否正确。
    #    新的 success 添加了额外条件：所有泄露检查也必须通过（leaks 的每个值都是 True）。
    #    也就是说：即使 API 返回了 200，但如果输出中包含了密钥或提示词，也算失败。
    safe_output["success"] = bool(safe_output["success"] and all(leaks.values()))
    return safe_output


# ❓ main() 函数做什么？
# 💡 命令行入口点——解析参数、调用烟雾测试逻辑、输出结果。
def main() -> None:
    # ❓ ArgumentParser 和 --out 参数？
    # 💡 支持一个可选参数 --out，指定输出文件的路径，默认是 "live-smoke.json"。
    #    type=Path 把字符串自动转为 pathlib.Path 对象。
    parser = argparse.ArgumentParser(description="Call the official DeepSeek API once and write only redacted structural evidence")
    parser.add_argument("--out", type=Path, default=Path("live-smoke.json"))
    args = parser.parse_args()
    # ❓ 为什么单独调用 run_live_smoke()？
    # 💡 关注点分离——run_live_smoke 负责业务逻辑，main 负责 I/O 和退出码。
    #    这样 run_live_smoke 可以被单元测试直接调用，不需要经过命令行界面。
    result = run_live_smoke()
    # ❓ json.dumps 参数说明？
    # 💡 ensure_ascii=False：允许输出中文等非 ASCII 字符
    #    indent=2：缩进 2 个空格，让 JSON 更可读
    #    + "\n"：末尾加换行符，符合 POSIX 文本文件规范
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # ❓ mkdir(parents=True, exist_ok=True) 是做什么？
    # 💡 确保输出文件的父目录存在。如果不存在，就递归创建它。
    #    parents=True：像 mkdir -p 一样创建多级目录
    #    exist_ok=True：如果目录已存在，不会报错
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # ❓ write_text 写入什么？
    # 💡 把 JSON 字符串写入文件。encoding="utf-8" 确保所有字符正确编码。
    args.out.write_text(text, encoding="utf-8")
    # ❓ print(text, end="") 为什么 end=""？
    # 💡 text 末尾已经有 \n 了，防止 print 再加一个多余换行。
    #    这样控制台输出和文件内容完全一致。
    print(text, end="")
    # ❓ raise SystemExit 的退出码逻辑？
    # 💡 success 为 True → 退出码 0（成功）
    #    success 为 False → 退出码 1（失败）
    #    CI/CD 系统依靠退出码判断脚本执行结果。
    raise SystemExit(0 if result["success"] else 1)


# ❓ if __name__ == "__main__": 的作用？
# 💡 Python 惯例：当脚本被直接运行时（`python3 live_api_smoke.py`），
#    执行 main()；当被 import 到其他模块时，不自动执行。
#    这样其他脚本可以安全地 import 这个模块中的函数来重复使用。
if __name__ == "__main__":
    main()
