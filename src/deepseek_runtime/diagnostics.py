# ❓ 问：文件开头为什么要写 from __future__ import annotations？
# 💡 答：这是为了"向前兼容"。Python 的类型注解（type hints）在不同版本中行为不同。
#    加上这行后，所有注解都会被当作字符串"延迟求值"——只做类型检查工具用，不在运行时真正计算。
#    这样这个模块就能同时在 Python 3.9、3.10、3.11 … 3.13 等版本中正确运行，不会报错。
from __future__ import annotations

# ❓ 问：这里为什么空了一行？
# 💡 答：这是 Python 代码的约定排版——import 语句块之前、文件头注释之后空一行，
#    让代码结构清晰可读。下面进入导入标准库的阶段。

# ❓ 问：这个诊断模块为什么需要导入这么多标准库？每种库是干什么的？
# 💡 答：这个模块要做本地健康检查，不同检查项需要不同的能力：
#    - json：解析"证据文件"（evidence files），里面存的是 LLM API 调用记录，JSON/JSONL 格式
#    - os：读取环境变量（如 DEEPSEEK_API_KEY）和检查文件写入权限
#    - platform：获取操作系统名称和版本（macOS / Linux / Windows）
#    - shutil：在系统 PATH 中搜索 deepseek-runtime CLI 命令是否存在
#    - sys：获取 Python 版本号、可执行文件路径等运行时信息
#    - pathlib.Path：跨平台地操作文件路径（比手动拼字符串更安全）
#    - typing：为函数参数和返回值添加类型注解，方便代码阅读和 IDE 智能提示
#
#    💡 论文参考（Agent Harness Survey - A1）：这段导库对应 Harness 六组件中的
#    "运行环境检测组件"——它负责感知当前 Python 版本、操作系统、文件系统状态，
#    是整个诊断系统的基础设施层。
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

# ❓ 问：这里为什么又空了一行？
# 💡 答：导入区结束后空两行，然后写常量定义。这是 Python 的 PEP 8 代码风格规范，
#    顶级定义（类/函数/常量）之间空两行，内部定义之间空一行。

# ❓ 问：SCHEMA_VERSION 和 RUNTIME_VERSION 这两个常量是干什么的？
# 💡 答：它们是这个诊断模块的"版本标签"，会写入最终的诊断报告字典中：
#    - SCHEMA_VERSION = "1.0"：表示诊断报告的数据结构是 v1.0 格式。
#      如果以后报告结构变了（比如新增了字段），版本号会升级，下游工具据此知道如何解析。
#    - RUNTIME_VERSION = "0.1.1a1"：表示 DeepSeek Runtime 当前的发行版本。
#      "0.1.1" 是语义版本号，"a1" 表示第一个 alpha 预发布版本。
SCHEMA_VERSION = "1.0"
RUNTIME_VERSION = "0.1.1a1"

# ❓ 问：为什么这里空两行？
# 💡 答：常量区和后面的函数定义之间空两行，符合 PEP 8 顶级定义之间空两行的规范。

# ❓ 问：这个 _check 函数是干什么的？
# 💡 答：它是一个"检查结果构造器"，是整个诊断模块最核心的工具函数。
#    每次执行一项健康检查（比如"Python 版本是否 >= 3.11"），都需要返回一个统一格式的结果字典。
#    _check 确保所有检查结果有相同的"形状"：
#    - name（str）：检查项的名称，如 "python_version"
#    - status（str）：状态，只能是 "pass"（通过）、"warn"（警告但不致命）、"fail"（失败）
#    - message（str）：描述信息，如 "Python >= 3.11 required"
#    - **fields（任意额外字段）：附加的上下文信息，如 version="3.11.4"
#    返回示例：{"name": "python_version", "status": "pass", "message": "Python >= 3.11 required", "version": "3.11.4"}
#
#    💡 论文参考（Survey on LLM Agents - A3）：在 Agent 评估框架中，每个评估维度都需要标准化输出格式。
#    _check 函数就是这个思路在诊断模块中的具体体现——每项检查都按统一 schema 报告，方便汇总和排序。
def _check(name: str, status: str, message: str, **fields: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, **fields}

# ❓ 问：_int_or_none 这个"转整数或返回 None"的函数，为什么不直接用 int() 强制转换？
# 💡 答：因为 LLM API 返回的数据里，整数可能以各种形式出现，直接用 int() 会出错：
#    - True/False 是布尔值，Python 中 bool 是 int 的子类，int(True) 会返回 1，这不是我们想要的
#    - 数字字符串 "42" 可以用 int() 转，但 API 通常不会返回字符串格式的数字
#    - 浮点数 42.0 也可以用 int() 转，但 42.5 转成 42 会丢失精度
#    这个函数严格按类型处理：布尔值排除，真正的整数直接返回，
#    浮点数只当值是整数时（如 42.0）才转，其余一律返回 None。
#    这是防御式编程，确保不会把类型错误的数据写入诊断报告。
def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None

# ❓ 问：_number_or_none 和 _int_or_none 功能相似，为什么要分开写？
# 💡 答：因为 token 数量一定是整数（如 1500 个 token），但价格可能是小数（如 0.00215 美元）。
#    两个函数各司其职：
#    - _int_or_none：只接受整数，用于 token 相关字段
#    - _number_or_none：同时接受整数和小数，用于成本/价格字段
#    同样地，布尔值被排除在外（避免 True 被误当作 1.0 传入成本计算）。
def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None

# ❓ 问：_first_int 这个"取第一个可用的整数"函数，到底解决什么问题？
# 💡 答：不同 LLM 提供商（OpenAI、Anthropic、DeepSeek 等）的 API 返回 JSON 时，
#    同一含义的字段名可能完全不同。
#    比如"缓存命中 token 数"，有的叫 prompt_cache_hit_tokens，有的叫 cache_hit_tokens。
#    _first_int 接受任意多个候选值，按顺序找到第一个能转成整数的返回。
#    这意味着上层代码只需要知道"我要取缓存命中的 token 数"，
#    而不需要知道具体是哪个字段名——兼容逻辑集中在这里处理。
def _first_int(*values: Any) -> int | None:
    for value in values:
        normalized = _int_or_none(value)
        if normalized is not None:
            return normalized
    return None

# ❓ 问：_load_evidence 这个"加载证据文件"的函数的返回值为什么是元组？
# 💡 答：因为文件读取可能成功也可能失败。返回元组 (数据, 错误) 是 Go 语言风格的错误处理模式：
#    - 成功时：返回 (解析后的数据, None)
#    - 失败时：返回 (None, 错误描述字符串)
#    调用方通过判断 error 是否为 None 来决定走哪条路，不会遗漏错误处理。
#
#    💡 论文参考（papers.md 中的证据机制）：在 llm-harness-agent 框架中，
#    "证据（Evidence）"是评估 Agent 行为可追溯性的核心概念。
#    每个 LLM API 调用记录称为一个"证据事件"（evidence event），
#    包含模型名、路由决策原因（route_reason）、缓存命中/未命中状态、
#    token 消耗量（prompt/completion/cached tokens）和估算成本。
#    证据文件的格式有两种：
#    - .jsonl（每行一个 JSON 对象）：适用于多次调用的流水日志
#    - .json（整个文件一个 JSON 对象或数组）：适用于单次或批量的调用记录
def _load_evidence(path: Path) -> tuple[Any | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{type(exc).__name__}: {exc}"
    stripped = text.strip()
    if not stripped:
        return [], None
    try:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in stripped.splitlines() if line.strip()], None
        return json.loads(stripped), None
    except json.JSONDecodeError as exc:
        return None, f"JSONDecodeError: {exc}"

# ❓ 问：_extract_usage 为什么要在 usage 和 tokens 两个字段里来回试？
# 💡 答：不同 LLM 服务商对"token 用量"这个信息的字段命名不统一。
#    这是又一个"适配多种 API 格式"的兼容层：
#    - 先查 "usage" 字段（DeepSeek、OpenAI 新版 API 的命名）
#    - 没有再查 "tokens" 字段（一些旧版或第三方 API 的命名）
#    只要有一个是字典，就返回它。这样上层的候选提取代码不需要知道具体的字段名。
def _extract_usage(value: dict[str, Any]) -> dict[str, Any] | None:
    usage = value.get("usage")
    if isinstance(usage, dict):
        return usage
    tokens = value.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    return None

# ❓ 问：_extract_cache 为什么要传入两个参数 value 和 usage？缓存信息可能藏在哪里？
# 💡 答：LLM API 返回的缓存详情（cache details）可能出现在两个不同位置：
#    1. 顶层 "cache" 字段：某些 API（如 Anthropic）把缓存信息直接放在顶层
#    2. usage 内部的 "prompt_tokens_details" 子字段：OpenAI 风格的嵌套结构
#    这个函数先查顶层 cache，没有再深入 usage 内部找。
#    两个地方都没有就返回空字典 {}，保证上层代码永远有值可用，不用处理 None。
def _extract_cache(value: dict[str, Any], usage: dict[str, Any] | None) -> dict[str, Any]:
    cache = value.get("cache")
    if isinstance(cache, dict):
        return cache
    details = (usage or {}).get("prompt_tokens_details")
    return details if isinstance(details, dict) else {}

# ❓ 问：_cache_hit_tokens 为什么需要从 usage 和 cache 两个来源中查，还要尝试五种字段名？
# 💡 答：因为"缓存命中 token 数"在不同 LLM 提供商甚至同一提供商的不同 API 版本中，
#    至少有五种不同的字段名！
#    从上到下依次尝试：
#    1. usage.prompt_cache_hit_tokens（DeepSeek / 较新 API 标准命名）
#    2. usage.cache_hit_tokens（较老 API 的缩写命名）
#    3. cache.prompt_cache_hit_tokens（缓存详情中的标准命名）
#    4. cache.hit_tokens（缓存详情的缩写命名）
#    5. cache.cached_tokens（另一种语义命名）
#    只要有一个是有效整数，直接返回。这个"宽容输入、统一输出"的设计模式贯穿整个模块。
def _cache_hit_tokens(usage: dict[str, Any] | None, cache: dict[str, Any]) -> int | None:
    usage = usage or {}
    return _first_int(usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"), cache.get("prompt_cache_hit_tokens"), cache.get("hit_tokens"), cache.get("cached_tokens"))

# ❓ 问：_cache_miss_tokens 的参数和 _cache_hit_tokens 类似，但为什么字段名变体少一些？
# 💡 答：缓存未命中（cache miss）的字段名变体确实比命中（hit）少。
#    因为 miss 字段是 API 规范相对后期才加入的，历史包袱少。
#    目前主要两种叫法：prompt_cache_miss_tokens 和 cache_miss_tokens。
#    这对理解 Agent 的缓存效率很重要——hit 和 miss 的比例可以衡量
#    "重复使用相同 prompt 上下文"的比例。命中率越高，说明 LLM 调用的成本越低、响应越快。
def _cache_miss_tokens(usage: dict[str, Any] | None, cache: dict[str, Any]) -> int | None:
    usage = usage or {}
    return _first_int(usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"), cache.get("prompt_cache_miss_tokens"), cache.get("miss_tokens"))

# ❓ 问：_candidate_from_dict 这个函数中的"candidate"（候选）是什么意思？
# 💡 答：在证据文件的体系里，每次 LLM API 调用记录称为一个"候选事件"（candidate event）。
#    候选的意思是：这个记录"可能"包含有用的 token 用量和成本数据，需要进一步判断。
#    函数的作用是：从一个字典（代表一条 API 调用记录）中，提取出对诊断有价值的关键信息：
#    - model：调用了哪个模型
#    - route_reason：路由决策原因（为什么选这个模型/路径）
#    - prompt_cache_hit_tokens / miss_tokens：缓存命中/未命中数量
#    - total_tokens：总 token 数
#    - estimated_cost：估算成本
#    如果一条记录没有任何 usage、cache 或 cost 信息，就返回 None 跳过。
#
#    💡 论文参考（Agent Harness Survey - A1）：候选提取对应 Harness 六组件中的
#    "证据归一化组件"——将不同格式、不同来源的原始 API 记录统一成标准结构。
def _candidate_from_dict(value: dict[str, Any], model_context: str | None) -> dict[str, Any] | None:
    usage = _extract_usage(value)
    cache = _extract_cache(value, usage)
    model = value.get("model")
    request = value.get("request_evidence")
    metadata = value.get("metadata")
    if not isinstance(model, str) and isinstance(request, dict):
        model = request.get("model")
    if not isinstance(model, str) and isinstance(metadata, dict):
        model = metadata.get("model")
    if not isinstance(model, str):
        model = model_context
    route_reason = value.get("route_reason")
    if not isinstance(route_reason, str) and isinstance(metadata, dict):
        route_reason = metadata.get("route_reason")
    cost = value.get("estimated_cost", value.get("cost"))
    if usage is None and not cache and _number_or_none(cost) is None:
        return None
    return {
        "model": model if isinstance(model, str) else None,
        "route_reason": route_reason if isinstance(route_reason, str) else None,
        "prompt_cache_hit_tokens": _cache_hit_tokens(usage, cache),
        "prompt_cache_miss_tokens": _cache_miss_tokens(usage, cache),
        "total_tokens": _int_or_none((usage or {}).get("total_tokens")),
        "estimated_cost": _number_or_none(cost),
    }

# ❓ 问：_collect_candidates 为什么要用递归方式遍历？证据文件的结构有多复杂？
# 💡 答：证据文件不是简单的扁平数组，它可能是一个深层嵌套的结构。
#    比如一个请求可能包含多个模型的并行调用（"models" 字段），
#    每个模型调用又可能包含子请求（request_evidence），
#    还可能按时间线分成多个步骤（每个步骤有不同的 routing 决策）。
#    这个函数递归地遍历整个数据结构：
#    - 如果是字典：先检查当前节点能否提取为候选；然后处理 "models" 子字典
#      （key 是模型名如 "deepseek-v4-flash"，value 是该模型的调用记录）；
#      接着递归遍历字典中所有其他子字段。
#    - 如果是列表：对每个元素递归调用自己。
#    最终将所有层级中找到的候选记录合并到一个列表中返回。
def _collect_candidates(value: Any, model_context: str | None = None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        current = _candidate_from_dict(value, model_context)
        if current is not None:
            candidates.append(current)
        models = value.get("models")
        if isinstance(models, dict):
            for model, payload in models.items():
                candidates.extend(_collect_candidates(payload, str(model)))
        for key, item in value.items():
            if key != "models":
                candidates.extend(_collect_candidates(item, model_context))
    elif isinstance(value, list):
        for item in value:
            candidates.extend(_collect_candidates(item, model_context))
    return candidates

# ❓ 问：_empty_usage_summary 返回的"空 usage 汇总"为什么还要包含这么多字段？直接返回 None 不行吗？
# 💡 答：不行。因为下游代码（如监控面板、日志系统）期望 usage_summary 永远是固定的字典结构。
#    如果返回 None 或空字典，下游代码每次使用前都需要先判空（if data is not None），
#    容易遗漏导致 AttributeError 崩溃。
#    这个"占位"结构确保在三种异常场景下都有安全的默认值：
#    - not_requested：用户没有提供证据文件路径
#    - read_error：文件存在但读取失败（权限/格式错误）
#    - no_usage_found：文件已读取但没有任何有效数据
#    所有数值字段（events、model、tokens、cost）都是 None 或 0，不会影响统计聚合。
def _empty_usage_summary(source: str | None, status: str) -> dict[str, Any]:
    return {
        "source": source,
        "status": status,
        "events": 0,
        "latest": {
            "model": None,
            "route_reason": None,
            "prompt_cache_hit_tokens": None,
            "prompt_cache_miss_tokens": None,
            "total_tokens": None,
            "estimated_cost": None,
        },
    }

# ❓ 问：evidence_summary 是"证据汇总"的公开函数，它的返回值三个部分各是什么？
# 💡 答：返回值是一个三元组 (usage_summary, check_item, warnings)，三个部分各司其职：
#    1. usage_summary（dict）：LLM API 使用情况的解析结果，包含 source（证据文件路径）、
#       status（available / not_requested / read_error / no_usage_found）、
#       events（提取到的候选事件总数）、latest（最新一条事件的详情）。
#    2. check_item（dict）：一个标准的诊断检查项，会加入 build_diagnostics 的 checks 列表。
#       状态有三种：
#       - "pass"：成功读取并提取到至少一条 usage 数据
#       - "warn"：未提供证据文件（path=None）或文件为空/无有效数据（不影响程序运行）
#       - "fail"：文件存在但读取失败（权限不足、JSON 解析错误等——需要人工介入修复）
#    3. warnings（list[str]）：需要上游关注的警告列表，如 "evidence_missing"。
#
#    💡 论文参考（Survey on LLM Agents - A3）：这个汇总函数体现了 Agent 评估中
#    "可观测性"（observability）的要求——能够追踪每一次 LLM 调用的资源消耗和路由决策，
#    是评估 Agent 经济性和运行效率的关键数据来源。
def evidence_summary(path: Path | None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    if path is None:
        return _empty_usage_summary(None, "not_requested"), _check("evidence", "warn", "no evidence file provided"), ["evidence_missing"]
    value, error = _load_evidence(path)
    if error is not None:
        return _empty_usage_summary(str(path), "read_error"), _check("evidence", "fail", error, path=str(path)), [f"evidence_read_failed: {error}"]
    candidates = _collect_candidates(value)
    if not candidates:
        return _empty_usage_summary(str(path), "no_usage_found"), _check("evidence", "warn", "no route/cache/usage/cost evidence found", path=str(path)), ["evidence_missing"]
    return {"source": str(path), "status": "available", "events": len(candidates), "latest": candidates[-1]}, _check("evidence", "pass", "route/cache/usage/cost evidence summarized", path=str(path)), []

# ❓ 问：_config_summary 从环境变量中提取了哪些 DeepSeek 配置？每个配置的默认值是什么？
# 💡 答：它从环境变量字典（默认是 os.environ）中提取五个关键配置：
#    1. DEEPSEEK_API_KEY：API 密钥——判断是"present"（已设置）还是"absent"（未设置）
#    2. DEEPSEEK_BASE_URL：API 基础地址——判断是"configured"（自定义地址）还是"default"（官方默认地址）
#    3. DEEPSEEK_MODEL：调用的默认模型名——默认值 "deepseek-v4-flash"
#    4. DEEPSEEK_TIMEOUT：请求超时秒数——默认值 "120"（字符串形式，保留原始环境变量格式）
#    5. DEEPSEEK_MAX_TOKENS：每次请求最多生成的 token 数——默认值 "512"
#    这个汇总让诊断报告能展示运行环境的配置快照，便于排查"为什么连不上"或"为什么配置与预期不符"的问题。
def _config_summary(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "deepseek_api_key": "present" if env.get("DEEPSEEK_API_KEY") else "absent",
        "base_url": "configured" if env.get("DEEPSEEK_BASE_URL") else "default",
        "model": env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "timeout": env.get("DEEPSEEK_TIMEOUT", "120"),
        "max_tokens": env.get("DEEPSEEK_MAX_TOKENS", "512"),
    }

# ❓ 问：_runtime_summary 收集了哪些运行时环境信息？entrypoint 是怎么检测的？
# 💡 答：它收集当前运行环境的六类信息，构成一个"环境快照"：
#    - runtime_version：DeepSeek Runtime 自身的发布版本号
#    - python：Python 解释器版本号（如 "3.11.4"，只取主版本号，去掉编译信息）
#    - python_executable：Python 解释器的完整文件路径
#    - platform：操作系统和硬件平台描述（如 "macOS-14.0-arm64-arm-64bit"）
#    - workspace：工作目录的绝对路径（通过 resolve() 解析符号链接）
#    - entrypoints：检查 deepseek-runtime CLI 命令是否在系统 PATH 中可用
#      检测逻辑：先用 shutil.which 在 PATH 中搜索"deepseek-runtime"命令，
#      找不到就检查当前运行脚本的名字是否以"deepseek-runtime"开头
#      （因为用户可能直接通过入口脚本运行，而不是通过已安装的命令）。
def _runtime_summary(workspace: Path) -> dict[str, Any]:
    executable = Path(sys.argv[0])
    entrypoint_available = bool(shutil.which("deepseek-runtime")) or executable.name.startswith("deepseek-runtime")
    return {
        "runtime_version": RUNTIME_VERSION,
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "workspace": str(workspace.resolve()),
        "entrypoints": {"deepseek-runtime": entrypoint_available},
    }

# ❓ 问：build_diagnostics 是整个诊断模块的入口函数，它的输入输出是什么？做了哪些检查？
# 💡 答：它是诊断系统的"总司令"（main entry point），供外部工具或启动脚本调用。
#
#    输入参数：
#    - workspace（Path）：当前工作目录路径，用于检查工作区是否存在、会话存储是否可写
#    - evidence（Path | None，可选）：证据文件的路径，不传就不检查 API 使用情况
#    - env（Mapping[str, str] | None，可选）：环境变量字典，不传就取 os.environ
#
#    内部按顺序执行六项健康检查，每项生成一个标准 _check 字典：
#    ① python_version：Python 版本是否 >= 3.11
#    ② workspace：工作区路径是否存在且是一个目录
#    ③ session_store_writable：会话存储目录是否可写入
#    ④ entrypoints：deepseek-runtime CLI 命令是否在 PATH 中
#    ⑤ api_key：DEEPSEEK_API_KEY 环境变量是否已设置
#    ⑥ evidence：证据文件是否存在、可读且包含有效 token/cache/cost 数据
#
#    最终输出一个完整的诊断报告字典，包含：
#    - schema_version：数据格式版本
#    - ok：是否所有检查项都没有"fail"——这是个快速判断系统是否健康的总开关
#    - checks：所有六项检查的明细列表
#    - config_summary：环境配置摘要（API 密钥、模型、超时等）
#    - runtime：运行时环境快照（Python 版本、操作系统、CLI 入口等）
#    - diagnostics：会话存储路径 + 证据文件使用情况汇总
#    - warnings：所有需要关注的非致命警告
#
#    💡 论文参考（Agent Harness Survey - A1）：这里的 checks 列表对应 Harness 六组件中的
#    "评估组件"——将每个检查项按 pass/warn/fail 三类状态分类，并汇总成整体健康度评分（ok 字段）。
#    证据机制（evidence）对应"可追溯组件"，确保每次 LLM 调用的资源消耗和路由决策都有据可查。
def build_diagnostics(workspace: Path, evidence: Path | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    config = _config_summary(env)
    runtime = _runtime_summary(workspace)

    # --- 检查①：Python 版本是否 >= 3.11 ---
    # ❓ 问：为什么要求 Python >= 3.11？
    # 💡 答：3.11 引入了大量性能优化和类型语法增强（如 str | None 联合类型写法），
    #    这个模块使用了这些新语法特性，所以版本不足时只能给警告而非致命错误，
    #    让用户在低版本 Python 下也能运行，只是不保证全部功能正常。
    python_ok = sys.version_info >= (3, 11)
    checks.append(_check("python_version", "pass" if python_ok else "warn", "Python >= 3.11 required", version=runtime["python"]))
    if not python_ok:
        warnings.append("python_below_supported_version")

    # --- 检查②：工作区路径是否存在且为目录 ---
    # ❓ 问：workspace 如果是文件而不是目录会怎样？
    # 💡 答：如果 workspace 存在但指向一个文件（而非目录），后续的路径拼接（如 workspace / ".deepseek-runtime"）会失败。
    #    所以这里用 exists() + is_dir() 双重检查，确保路径既存在又是一个目录。
    if not workspace.exists() or not workspace.is_dir():
        checks.append(_check("workspace", "fail", "workspace path must exist and be a directory", path=str(workspace)))
    else:
        checks.append(_check("workspace", "pass", "workspace exists", path=str(workspace.resolve())))

    # --- 检查③：会话存储路径是否可写 ---
    # ❓ 问：session_store 路径是 workspace/.deepseek-runtime/sessions，为什么要逐级回退找可写目标？
    # 💡 答：因为会话存储目录可能还不存在（首次运行），但它的父目录或 workspace 本身应该是可写的。
    #    可写性检查的目标选择逻辑：优先用 session_store 本身（已存在时）；不存在则用其父目录；
    #    父目录也不存在则回退到 workspace。这种逐级回退确保最大兼容性——即使 .deepseek-runtime 目录还没创建，
    #    只要 workspace 可写，就能推断出将来可以创建子目录。
    session_store = workspace / ".deepseek-runtime" / "sessions"
    writable_target = session_store if session_store.exists() else session_store.parent if session_store.parent.exists() else workspace
    session_writable = workspace.exists() and os.access(writable_target, os.W_OK)
    checks.append(_check("session_store_writable", "pass" if session_writable else "fail", "session store parent is writable" if session_writable else "session store parent is not writable", path=str(session_store)))

    # --- 检查④：CLI 入口 deepseek-runtime 是否可用 ---
    # ❓ 问：为什么 entrypoint 检查只给 warn 不给 fail？
    # 💡 答：deepseek-runtime CLI 不是运行时必需组件——核心功能可以直接通过 Python API 调用。
    #    没有 CLI 只是少了命令行交互能力，不影响程序运行，所以用 warn 而非 fail。
    checks.append(_check("entrypoints", "pass" if runtime["entrypoints"]["deepseek-runtime"] else "warn", "deepseek-runtime entrypoint is available" if runtime["entrypoints"]["deepseek-runtime"] else "deepseek-runtime entrypoint is not on PATH", entrypoints=runtime["entrypoints"]))

    # --- 检查⑤：API Key 是否已设置 ---
    # ❓ 问：API Key 缺失为什么也只给 warn 而不是 fail？
    # 💡 答：缺失 API Key 意味着向 DeepSeek 模型发起的在线调用会失败，
    #    但本地诊断功能（检查 Python 版本、工作区、会话存储等）仍然可以正常运行。
    #    用户可能只是想做本地环境检测，并不需要马上调用模型，所以给 warn 而非 fail 更合理。
    api_key_present = config["deepseek_api_key"] == "present"
    checks.append(_check("api_key", "pass" if api_key_present else "warn", "DEEPSEEK_API_KEY is present" if api_key_present else "DEEPSEEK_API_KEY is absent; live provider calls will fail"))
    if not api_key_present:
        warnings.append("api_key_absent")

    # --- 检查⑥：证据文件读取与汇总 ---
    usage_summary, evidence_check, evidence_warnings = evidence_summary(evidence)
    checks.append(evidence_check)
    warnings.extend(evidence_warnings)

    # ❓ 问：最终诊断报告的 ok 字段是怎么计算的？
    # 💡 答：ok = 所有 check 项中没有任何一项的 status 是 "fail"。
    #    注意：warn 状态不会让 ok 变成 False，只有 fail 才会。
    #    这意味着如果只是 Python 版本略低或 API Key 未设置（warn），
    #    系统仍然被认为是"总体上健康的"（ok=True）。
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not any(check["status"] == "fail" for check in checks),
        "checks": checks,
        "config_summary": config,
        "runtime": runtime,
        "diagnostics": {"session_store": str(session_store), "evidence_summary": usage_summary},
        "warnings": warnings,
    }
