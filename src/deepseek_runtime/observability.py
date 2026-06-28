"""
可观测性层（Observability Layer）—— Agent 跑了多少任务？花了多少钱？

❓ 问：CEO/产品经理最关心什么问题？
💡 答：Agent 好用吗？花了多少钱？有没有优化空间？
   observability.py 就是回答这些问题的——它把 Agent 每次运行的"体检报告"
   汇总成结构化数据：成功了多少次、缓存命中了多少 token、大概花了多少钱。

参考 llm-harness-agent 论文 A1（Agent Harness Survey）中关于可观测性组件
的讨论：「缓存可见性和任务成功率、成本应该在同一证据流里，而不是孤立指标。」
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

# 敏感标记：如果字符串包含这些关键词，说明它可能是敏感信息，需要脱敏
SENSITIVE_MARKERS = ("authorization", "bearer", "password", "api_key", "token", "secret")


@dataclass
class Observation:
    """一条"观察记录"——代表一次 Agent 任务执行的结构化摘要。

    ❓ 问：类比一下，Observation 像什么？
    💡 答：像快递的物流单——记录了每个包裹（任务）的发货时间、谁送的、
       有没有送到、花了多少运费。把散乱的物流数据汇总就成了"运营报表"。

    参考 llm-harness-agent 论文 D1: Memory Mechanism Survey 中关于
    Agent 记忆结构化的讨论：原始日志需要被结构化为标准格式才能做分析。
    """
    task_id: str | None  # 任务 ID（相当于运单号）
    model: str | None  # 使用的模型（如 deepseek-v4-flash）
    route_reason: str | None  # 为什么选这个模型（路由原因）
    success: bool | None  # 任务是否成功
    first_completion: bool | None  # 是否一次成功（没有经过反思重试）
    prompt_cache_hit_tokens: int | None  # 缓存命中的 token 数（最便宜）
    prompt_cache_miss_tokens: int | None  # 缓存未命中的 token 数（正常价）
    completion_tokens: int | None  # 模型输出的 token 数（最贵）
    total_tokens: int | None  # 总 token 数
    estimated_cost_usd: float | None  # 预估美元成本

    def to_dict(self) -> dict[str, Any]:
        """把 Observation 转成普通字典，方便序列化成 JSON"""
        return self.__dict__.copy()


# ===== 辅助函数 =====

def _safe_string(value: Any) -> str | None:
    """安全字符串：如果包含敏感关键词则替换为 [redacted]"""
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        return "[redacted]"
    return value


def _int_or_none(value: Any) -> int | None:
    """把值安全转成整数（布尔值不转，字符串不转）"""
    if isinstance(value, bool):
        return None  # True/False 不算整数
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _float_or_none(value: Any) -> float | None:
    """把值安全转成浮点数"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _first_int(*values: Any) -> int | None:
    """从多个值中取第一个有效整数（兼容不同数据源的字段名差异）"""
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _iter_rows(data: Any) -> Iterable[tuple[dict[str, Any], str | None]]:
    """统一遍历各种格式的输入数据

    ❓ 问：为什么需要支持多种格式？
    💡 答：不同数据源的输出格式不同——
       格式 A：{"models": {"v4-flash": {"rows": [...]}}}
       格式 B：{"rows": [...]}
       格式 C：[...]（直接就是列表）
       格式 D：{...}（单个任务数据）
       这个函数接受任意格式，统一输出（行数据, 模型名）的迭代器。
    """
    # 格式 A：按模型分组的 rows
    if isinstance(data, dict) and isinstance(data.get("models"), dict):
        for model, result in data["models"].items():
            if isinstance(result, dict):
                for row in result.get("rows", []):
                    if isinstance(row, dict):
                        yield row, model
        return
    # 格式 B：带 rows 字段的字典
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        for row in data["rows"]:
            if isinstance(row, dict):
                yield row, None
        return
    # 格式 C：直接就是列表
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                yield row, None
        return
    # 格式 D：单个字典
    if isinstance(data, dict):
        yield data, None


def _usage_from(row: dict[str, Any]) -> dict[str, Any]:
    """从行数据中提取 token 用量信息（兼容 tokens 和 usage 两种字段名）"""
    tokens = row.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    usage = row.get("usage")
    if isinstance(usage, dict):
        return usage
    return {}


def _cache_from(row: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    """从行数据中提取缓存信息（兼容不同位置和字段名）"""
    cache = row.get("cache")
    if isinstance(cache, dict):
        return cache
    details = usage.get("prompt_tokens_details")
    return details if isinstance(details, dict) else {}


def _model_from(row: dict[str, Any], group_model: str | None) -> str | None:
    """从行数据中提取模型名称（兼容不同嵌套位置）"""
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    request = row.get("request_evidence") if isinstance(row.get("request_evidence"), dict) else {}
    return _safe_string(row.get("model") or metadata.get("model") or request.get("model") or group_model)


def _route_reason_from(row: dict[str, Any]) -> str | None:
    """从行数据中提取路由原因"""
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return _safe_string(row.get("route_reason") or metadata.get("route_reason"))


def _success_from(row: dict[str, Any]) -> bool | None:
    """从行数据中推断任务是否成功"""
    if isinstance(row.get("success"), bool):
        return row["success"]
    status = _int_or_none(row.get("status"))
    if status is not None:
        return 200 <= status < 300 and not row.get("error")
    return None


def _estimated_cost(
    usage: dict[str, Any], cache: dict[str, Any],
    model: str | None, pricing: dict[str, Any], explicit_cost: Any
) -> float | None:
    """预估成本：使用定价表 × token 用量计算，或直接使用显式提供的成本

    ❓ 问：成本是怎么估算的？
    💡 答：公式 = (缓存命中token × 缓存命中单价 + 缓存未中token × 输入单价
       + 输出token × 输出单价) ÷ 计价单位(通常100万)
       
    参考 llm-harness-agent 论文 D1 中关于 Token 管理和成本估算的讨论。
    """
    provided = _float_or_none(explicit_cost)
    if provided is not None:
        return provided  # 显式提供的成本优先
    if not model:
        return None
    model_prices = pricing.get("models", {}).get(model)
    if not isinstance(model_prices, dict):
        return None
    unit = _int_or_none(pricing.get("unit_tokens")) or 1_000_000
    hit = _first_int(
        usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"),
        cache.get("cached_tokens"), cache.get("hit_tokens"), 0,
    )
    miss = _first_int(
        usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"),
        cache.get("miss_tokens"), 0,
    )
    output = _first_int(usage.get("completion_tokens"), usage.get("output_tokens"), 0)
    total = (
        hit * float(model_prices["cache_hit_input"])
        + miss * float(model_prices["cache_miss_input"])
        + output * float(model_prices["output"])
    ) / unit
    return round(total, 12)


def _observation_from(
    row: dict[str, Any], group_model: str | None, pricing: dict[str, Any]
) -> Observation:
    """从一行原始数据中组装出一条结构化的 Observation

    参考 llm-harness-agent 论文 B4: Reflexion 中关于 Agent 反思机制
    的讨论——"首次完成率"是衡量反思机制有效性的关键指标。
    """
    usage = _usage_from(row)
    cache = _cache_from(row, usage)
    model = _model_from(row, group_model)
    cost = _estimated_cost(usage, cache, model, pricing, row.get("estimated_cost", row.get("cost")))
    return Observation(
        task_id=_safe_string(row.get("task_id") or row.get("experiment")),
        model=model,
        route_reason=_route_reason_from(row),
        success=_success_from(row),
        first_completion=row.get("first_completion") if isinstance(row.get("first_completion"), bool) else None,
        prompt_cache_hit_tokens=_first_int(
            usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"),
            cache.get("cached_tokens"), cache.get("hit_tokens"),
        ),
        prompt_cache_miss_tokens=_first_int(
            usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"),
            cache.get("miss_tokens"),
        ),
        completion_tokens=_first_int(usage.get("completion_tokens"), usage.get("output_tokens")),
        total_tokens=_first_int(usage.get("total_tokens")),
        estimated_cost_usd=cost,
    )


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    """生成一条检查结果"""
    return {"name": name, "ok": ok, "evidence": evidence}


# ===== 主函数 =====

def summarize_observability(data: Any, pricing: dict[str, Any], source: str) -> dict[str, Any]:
    """汇总所有任务的可观测性数据，生成结构化报告

    ❓ 问：这个函数是做什么的？
    💡 答：它接受原始的 Agent 执行日志（data），配合定价表（pricing），
       生成一份完整的"运营报表"——包含任务数量、成功率、token 用量、
       缓存命中率、预估成本、每次成功的成本效率等。

    参考 llm-harness-agent 论文 A1 中关于可观测性组件的定义：
    「可观测性组件（Observability）是 Harness 六组件的核心输出层，
    负责汇总各层级的运行数据。」
    """
    # 从原始数据中提取所有 Observation
    observations = [_observation_from(row, group_model, pricing) for row, group_model in _iter_rows(data)]

    # 统计
    successes = sum(1 for item in observations if item.success is True)
    known_success = sum(1 for item in observations if item.success is not None)
    cost_total = round(sum(item.estimated_cost_usd or 0.0 for item in observations), 12)

    # 汇总摘要
    summary = {
        "source": source,  # 数据来源
        "task_count": len(observations),  # 总任务数
        "successes": successes,  # 成功数
        "failures": sum(1 for item in observations if item.success is False),  # 失败数
        "success_rate": round(successes / known_success, 6) if known_success else None,  # 成功率
        "first_completion_rate": round(
            sum(1 for item in observations if item.first_completion is True) / len(observations), 6
        ) if observations else None,  # 首次完成率（无需反思重试的比例）
        "models": sorted({item.model for item in observations if item.model}),  # 用到的模型列表
        "route_reasons": sorted({item.route_reason for item in observations if item.route_reason}),  # 路由原因
        "prompt_cache_hit_tokens": sum(item.prompt_cache_hit_tokens or 0 for item in observations),  # 缓存命中
        "prompt_cache_miss_tokens": sum(item.prompt_cache_miss_tokens or 0 for item in observations),  # 缓存未命中
        "completion_tokens": sum(item.completion_tokens or 0 for item in observations),  # 输出 token
        "total_tokens": sum(item.total_tokens or 0 for item in observations),  # 总 token
        "estimated_cost_usd": cost_total,  # 预估总成本
        "tokens_per_success": round(
            sum(item.total_tokens or 0 for item in observations) / successes, 6
        ) if successes else None,  # 每次成功消耗的 token
        "cost_per_success_usd": round(cost_total / successes, 12) if successes else None,  # 每次成功花费
        "pricing_snapshot_date": pricing.get("snapshot_date"),  # 定价表日期
        "pricing_source": pricing.get("source"),  # 定价表来源
    }

    # 数据质量检查清单
    checks = [
        _check("route_visible", bool(observations) and all(item.model and item.route_reason for item in observations),
               {"models": len(summary["models"]), "route_reasons": len(summary["route_reasons"])}),
        _check("usage_visible", bool(observations) and all(item.total_tokens is not None for item in observations),
               {"total_tokens": summary["total_tokens"]}),
        _check("cache_usage_visible", bool(observations) and all(
            item.prompt_cache_hit_tokens is not None and item.prompt_cache_miss_tokens is not None
            for item in observations),
               {"hit_tokens": summary["prompt_cache_hit_tokens"], "miss_tokens": summary["prompt_cache_miss_tokens"]}),
        _check("cost_estimated", bool(observations) and all(item.estimated_cost_usd is not None for item in observations),
               {"estimated_cost_usd": summary["estimated_cost_usd"]}),
        _check("success_rate_visible", summary["success_rate"] is not None,
               {"success_rate": summary["success_rate"]}),
        _check("tokens_per_success_visible", summary["tokens_per_success"] is not None,
               {"tokens_per_success": summary["tokens_per_success"]}),
        _check("cost_per_success_visible", summary["cost_per_success_usd"] is not None,
               {"cost_per_success_usd": summary["cost_per_success_usd"]}),
    ]

    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),  # 所有检查通过才算成功
        "summary": summary,
        "observations": [item.to_dict() for item in observations],
        "checks": checks,
        "warning": "本报告基于规则推导（状态码判断成功、定价表估算成本），不代表实际账单。",
    }
