from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

SENSITIVE_MARKERS = ("authorization", "bearer", "password", "api_key", "token", "secret")


@dataclass
class Observation:
    task_id: str | None
    model: str | None
    route_reason: str | None
    success: bool | None
    first_completion: bool | None
    prompt_cache_hit_tokens: int | None
    prompt_cache_miss_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _safe_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        return "[redacted]"
    return value


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _iter_rows(data: Any) -> Iterable[tuple[dict[str, Any], str | None]]:
    if isinstance(data, dict) and isinstance(data.get("models"), dict):
        for model, result in data["models"].items():
            if isinstance(result, dict):
                for row in result.get("rows", []):
                    if isinstance(row, dict):
                        yield row, model
        return
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        for row in data["rows"]:
            if isinstance(row, dict):
                yield row, None
        return
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                yield row, None
        return
    if isinstance(data, dict):
        yield data, None


def _usage_from(row: dict[str, Any]) -> dict[str, Any]:
    tokens = row.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    usage = row.get("usage")
    if isinstance(usage, dict):
        return usage
    return {}


def _cache_from(row: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    cache = row.get("cache")
    if isinstance(cache, dict):
        return cache
    details = usage.get("prompt_tokens_details")
    return details if isinstance(details, dict) else {}


def _model_from(row: dict[str, Any], group_model: str | None) -> str | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    request = row.get("request_evidence") if isinstance(row.get("request_evidence"), dict) else {}
    return _safe_string(row.get("model") or metadata.get("model") or request.get("model") or group_model)


def _route_reason_from(row: dict[str, Any]) -> str | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    return _safe_string(row.get("route_reason") or metadata.get("route_reason"))


def _success_from(row: dict[str, Any]) -> bool | None:
    if isinstance(row.get("success"), bool):
        return row["success"]
    status = _int_or_none(row.get("status"))
    if status is not None:
        return 200 <= status < 300 and not row.get("error")
    return None


def _estimated_cost(usage: dict[str, Any], cache: dict[str, Any], model: str | None, pricing: dict[str, Any], explicit_cost: Any) -> float | None:
    provided = _float_or_none(explicit_cost)
    if provided is not None:
        return provided
    if not model:
        return None
    model_prices = pricing.get("models", {}).get(model)
    if not isinstance(model_prices, dict):
        return None
    unit = _int_or_none(pricing.get("unit_tokens")) or 1_000_000
    hit = _first_int(usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"), cache.get("cached_tokens"), cache.get("hit_tokens"), 0)
    miss = _first_int(usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"), cache.get("miss_tokens"), 0)
    output = _first_int(usage.get("completion_tokens"), usage.get("output_tokens"), 0)
    total = (hit * float(model_prices["cache_hit_input"]) + miss * float(model_prices["cache_miss_input"]) + output * float(model_prices["output"])) / unit
    return round(total, 12)


def _observation_from(row: dict[str, Any], group_model: str | None, pricing: dict[str, Any]) -> Observation:
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
        prompt_cache_hit_tokens=_first_int(usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"), cache.get("cached_tokens"), cache.get("hit_tokens")),
        prompt_cache_miss_tokens=_first_int(usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"), cache.get("miss_tokens")),
        completion_tokens=_first_int(usage.get("completion_tokens"), usage.get("output_tokens")),
        total_tokens=_first_int(usage.get("total_tokens")),
        estimated_cost_usd=cost,
    )


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


def summarize_observability(data: Any, pricing: dict[str, Any], source: str) -> dict[str, Any]:
    observations = [_observation_from(row, group_model, pricing) for row, group_model in _iter_rows(data)]
    successes = sum(1 for item in observations if item.success is True)
    known_success = sum(1 for item in observations if item.success is not None)
    cost_total = round(sum(item.estimated_cost_usd or 0.0 for item in observations), 12)
    summary = {
        "source": source,
        "task_count": len(observations),
        "successes": successes,
        "failures": sum(1 for item in observations if item.success is False),
        "success_rate": round(successes / known_success, 6) if known_success else None,
        "first_completion_rate": round(sum(1 for item in observations if item.first_completion is True) / len(observations), 6) if observations else None,
        "models": sorted({item.model for item in observations if item.model}),
        "route_reasons": sorted({item.route_reason for item in observations if item.route_reason}),
        "prompt_cache_hit_tokens": sum(item.prompt_cache_hit_tokens or 0 for item in observations),
        "prompt_cache_miss_tokens": sum(item.prompt_cache_miss_tokens or 0 for item in observations),
        "completion_tokens": sum(item.completion_tokens or 0 for item in observations),
        "total_tokens": sum(item.total_tokens or 0 for item in observations),
        "estimated_cost_usd": cost_total,
        "tokens_per_success": round(sum(item.total_tokens or 0 for item in observations) / successes, 6) if successes else None,
        "cost_per_success_usd": round(cost_total / successes, 12) if successes else None,
        "pricing_snapshot_date": pricing.get("snapshot_date"),
        "pricing_source": pricing.get("source"),
    }
    checks = [
        _check("route_visible", bool(observations) and all(item.model and item.route_reason for item in observations), {"models": len(summary["models"]), "route_reasons": len(summary["route_reasons"])}),
        _check("usage_visible", bool(observations) and all(item.total_tokens is not None for item in observations), {"total_tokens": summary["total_tokens"]}),
        _check("cache_usage_visible", bool(observations) and all(item.prompt_cache_hit_tokens is not None and item.prompt_cache_miss_tokens is not None for item in observations), {"hit_tokens": summary["prompt_cache_hit_tokens"], "miss_tokens": summary["prompt_cache_miss_tokens"]}),
        _check("cost_estimated", bool(observations) and all(item.estimated_cost_usd is not None for item in observations), {"estimated_cost_usd": summary["estimated_cost_usd"]}),
        _check("success_rate_visible", summary["success_rate"] is not None, {"success_rate": summary["success_rate"]}),
        _check("tokens_per_success_visible", summary["tokens_per_success"] is not None, {"tokens_per_success": summary["tokens_per_success"]}),
        _check("cost_per_success_visible", summary["cost_per_success_usd"] is not None, {"cost_per_success_usd": summary["cost_per_success_usd"]}),
    ]
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),
        "summary": summary,
        "observations": [item.to_dict() for item in observations],
        "checks": checks,
        "warning": "Observability uses supplied or deterministic evidence. It proves metric visibility, not live model quality or actual billing.",
    }
