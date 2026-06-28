# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 shebang（释伴行），告诉操作系统用 python3 解释器来运行这个脚本。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是做什么的？
# 💡 让类型注解延迟求值，提升性能并支持前向引用。
from __future__ import annotations

# ❓ 这里导入的标准库是做什么的？
# 💡 - argparse：解析命令行参数（--out, --evidence, --pricing）
#    - json：序列化结果到 JSON，或从文件加载定价数据
#    - sys：获取当前 Python 解释器路径
#    - pathlib.Path：面向对象路径操作
#    - typing.Any：动态类型注解
import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ❓ ROOT 和 SRC 路径设置？
# 💡 ROOT 是项目根目录，SRC 是 src 子目录。
#    如果 SRC 不在 Python 的模块搜索路径中，就插入到最前面，
#    以便 import deepseek_runtime 包。
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ❓ from deepseek_runtime.observability import ... 是做什么的？
# 💡 导入可观测性摘要函数 summarize_observability，
#    它负责汇总和分析路由/缓存/Token使用/成本等数据。
#    参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于可观测性度量的讨论。
from deepseek_runtime.observability import summarize_observability

# ❓ DEFAULT_PRICING 常量里有什么？
# 💡 一个硬编码的定价表，包含 DeepSeek 两个模型的价格信息：
#    - snapshot_date: 数据快照日期（2026-06-07）
#    - source: 数据来源链接（DeepSeek 官方定价页）
#    - unit_tokens: 计价单位（每 1,000,000 个 token）
#    - models: 两个模型的定价
#      - deepseek-v4-flash: 轻量快速模型
#        - cache_hit_input: 缓存命中的输入价格（$0.014/百万token）
#        - cache_miss_input: 缓存未命中的输入价格（$0.14/百万token）
#        - output: 输出价格（$0.28/百万token）
#      - deepseek-v4-pro: 高性能专业模型
#        - 价格约为 flash 版的 10 倍
#    注意：这是一个静态测试用数据，来自文档中公布的公开价格。
#    参考 llm-harness-agent 论文 A1 中关于成本跟踪和 Token 计量的建议。
DEFAULT_PRICING = {
    "snapshot_date": "2026-06-07",
    "source": "https://api-docs.deepseek.com/quick_start/pricing",
    "unit_tokens": 1_000_000,
    "models": {
        "deepseek-v4-flash": {"cache_hit_input": 0.014, "cache_miss_input": 0.14, "output": 0.28},
        "deepseek-v4-pro": {"cache_hit_input": 0.14, "cache_miss_input": 1.4, "output": 2.8},
    },
}

# ❓ FIXTURE_ROWS 是什么？
# 💡 一个元组（tuple，不可变列表），包含三条模拟的请求日志记录。
#    每条记录代表一次 API 调用，包含完整的可观测性数据：
#    - task_id: 任务标识符
#    - model: 使用的模型
#    - route_reason: 路由决策原因（为什么选这个模型）
#    - success: 请求是否成功
#    - first_completion: 是否是首次完成（非重试/重试后成功）
#    - tokens: Token 使用量明细
#      - prompt_cache_hit_tokens: 缓存命中的提示词 token 数
#      - prompt_cache_miss_tokens: 缓存未命中的提示词 token 数
#      - completion_tokens: 生成的输出 token 数
#      - total_tokens: 总 token 数
# 这三条记录模拟了三种不同的使用场景：
# 1. OBS01: 低成本快速编辑（flash 模型，成功，首次完成，缓存命中率高）
# 2. OBS02: 低成本重试（flash 模型，失败，不是首次完成）
# 3. OBS03: 高精度需求（pro 模型，成功，不是首次完成）
FIXTURE_ROWS: tuple[dict[str, Any], ...] = (
    {"task_id": "OBS01", "model": "deepseek-v4-flash", "route_reason": "low-cost simple edit", "success": True, "first_completion": True, "tokens": {"prompt_cache_hit_tokens": 64, "prompt_cache_miss_tokens": 160, "completion_tokens": 40, "total_tokens": 264}},
    {"task_id": "OBS02", "model": "deepseek-v4-flash", "route_reason": "low-cost retry after failed test", "success": False, "first_completion": False, "tokens": {"prompt_cache_hit_tokens": 96, "prompt_cache_miss_tokens": 80, "completion_tokens": 24, "total_tokens": 200}},
    {"task_id": "OBS03", "model": "deepseek-v4-pro", "route_reason": "higher accuracy for rollback-sensitive edit", "success": True, "first_completion": False, "tokens": {"prompt_cache_hit_tokens": 128, "prompt_cache_miss_tokens": 220, "completion_tokens": 60, "total_tokens": 408}},
)


# ❓ _load_json_or_jsonl 是做什么的？
# 💡 一个灵活的 JSON/JSONL（JSON Lines）文件加载函数。
#    它先尝试用 json.loads 解析整个文件（标准 JSON），
#    如果失败，就按行解析——每行作为一个独立的 JSON 对象（JSONL 格式）。
# ❓ -> Any 是什么意思？
# 💡 返回类型可以是任何类型——可能是字典（标准 JSON）或列表（JSONL）。
def _load_json_or_jsonl(path: Path) -> Any:
    # ❓ read_text 读入了什么？
    # 💡 读取文件的全部内容作为字符串。
    raw = path.read_text(encoding="utf-8")
    try:
        # ❓ 先尝试标准 JSON 解析
        # 💡 如果文件是一个标准的 JSON 对象（以 { 开头），json.loads 可以解析它。
        #    成功就直接返回解析后的 Python 对象。
        return json.loads(raw)
    except json.JSONDecodeError:
        # ❓ JSON 解析失败怎么办？
        # 💡 可能是 JSONL 格式（每行一个 JSON 对象）。
        #    按换行符分割，过滤掉空行，逐行解析。
        #    返回一个列表，每项是一条解析后的 JSON 记录。
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


# ❓ run_observability_drill 是核心函数吗？
# 💡 是的。它聚合可观测性数据并生成摘要报告：
#    - 使用测试定价数据（默认）或从文件加载外部定价
#    - 使用测试数据（FIXTURE_ROWS）或从文件加载外部证据
#    - 调用 summarize_observability 生成结构化报告
# ❓ evidence 和 pricing_path 为什么都是 Optional？
# 💡 两个参数默认都是 None，表示使用硬编码的测试数据（FIXTURE_ROWS 和 DEFAULT_PRICING）。
#    如果提供了路径，就从外部文件加载真实数据。
#    这种设计支持两种模式：确定性测试（默认）和真实数据分析（提供文件路径）。
def run_observability_drill(evidence: Path | None = None, pricing_path: Path | None = None) -> dict[str, Any]:
    # ❓ 定价数据从哪里来？
    # 💡 如果 pricing_path 是 None（未指定定价文件），使用 DEFAULT_PRICING（硬编码测试数据）。
    #    如果指定了，就从文件读取并解析 JSON。
    pricing = DEFAULT_PRICING if pricing_path is None else json.loads(pricing_path.read_text(encoding="utf-8"))
    # ❓ 数据从哪里来？
    # 💡 如果 evidence 是 None（未指定证据文件），使用 FIXTURE_ROWS（硬编码测试数据）。
    #    如果指定了，就用 _load_json_or_jsonl 从文件加载。
    #    data 采用 Any 类型标注，因为可能返回字典或列表，由下游函数统一处理。
    data: Any = {"rows": list(FIXTURE_ROWS)} if evidence is None else _load_json_or_jsonl(evidence)
    # ❓ source 是什么？
    # 💡 数据来源的描述文字——如果使用默认测试数据，标注为 "deterministic-fixture"；
    #    如果使用外部文件，标注为文件路径。
    source = "deterministic-fixture" if evidence is None else str(evidence)
    # ❓ summarize_observability 返回什么？
    # 💡 返回一个结构化的可观测性摘要字典，包含：
    #    - 路由统计：什么请求被路由到了哪个模型
    #    - 缓存效率：缓存命中 vs 未命中比例
    #    - Token 使用：描述性统计
    #    - 成本分析：基于定价数据计算的预估成本
    #    - 成功/失败比例
    #    参考 llm-harness-agent 论文 A1 中关于持续集成可观测性指标的讨论。
    return summarize_observability(data, pricing, source)


# ❓ main() 函数做什么？
# 💡 命令行入口点——解析参数、运行可观测性演练、输出结果、返回退出码。
def main() -> None:
    # ❓ 三个可选参数的作用？
    # 💡 --out: 输出 JSON 文件路径（可选）
    #    --evidence: 可观测性数据文件路径（可选，默认使用内建测试数据）
    #    --pricing: 定价配置文件路径（可选，默认使用内建定价表）
    parser = argparse.ArgumentParser(description="Run deterministic route/cache/usage/cost observability checks")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--pricing", type=Path)
    args = parser.parse_args()
    # ❓ 为什么单独调用 run_observability_drill？
    # 💡 关注点分离——核心逻辑在 run_observability_drill 中，main 只处理 I/O。
    result = run_observability_drill(args.evidence, args.pricing)
    # ❓ json.dumps 参数？
    # 💡 ensure_ascii=False 允许输出非 ASCII 字符
    #    indent=2 缩进 2 空格
    #    + "\n" 末尾换行符
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # ❓ if args.out 是做什么的？
    # 💡 --out 是可选的，如果用户没指定，args.out 是 None，只打印到控制台。
    if args.out:
        # ❓ mkdir 确保父目录存在
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    # ❓ print(text, end="") 为什么 end=""？
    # 💡 text 末尾已有 \n，防止 print 多输出一个空行。
    print(text, end="")
    # ❓ SystemExit 退出码？
    # 💡 0 = 成功，1 = 失败。
    #    这里 result["success"] 由 summarize_observability 决定。
    raise SystemExit(0 if result["success"] else 1)


# ❓ if __name__ == "__main__": 的作用？
# 💡 Python 惯例：直接运行脚本时执行 main()，被 import 时不自动执行。
if __name__ == "__main__":
    main()
