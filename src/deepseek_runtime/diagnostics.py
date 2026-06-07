from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
RUNTIME_VERSION = "0.1.1a0"


def _check(name: str, status: str, message: str, **fields: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, **fields}


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        normalized = _int_or_none(value)
        if normalized is not None:
            return normalized
    return None


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


def _extract_usage(value: dict[str, Any]) -> dict[str, Any] | None:
    usage = value.get("usage")
    if isinstance(usage, dict):
        return usage
    tokens = value.get("tokens")
    if isinstance(tokens, dict):
        return tokens
    return None


def _extract_cache(value: dict[str, Any], usage: dict[str, Any] | None) -> dict[str, Any]:
    cache = value.get("cache")
    if isinstance(cache, dict):
        return cache
    details = (usage or {}).get("prompt_tokens_details")
    return details if isinstance(details, dict) else {}


def _cache_hit_tokens(usage: dict[str, Any] | None, cache: dict[str, Any]) -> int | None:
    usage = usage or {}
    return _first_int(usage.get("prompt_cache_hit_tokens"), usage.get("cache_hit_tokens"), cache.get("prompt_cache_hit_tokens"), cache.get("hit_tokens"), cache.get("cached_tokens"))


def _cache_miss_tokens(usage: dict[str, Any] | None, cache: dict[str, Any]) -> int | None:
    usage = usage or {}
    return _first_int(usage.get("prompt_cache_miss_tokens"), usage.get("cache_miss_tokens"), cache.get("prompt_cache_miss_tokens"), cache.get("miss_tokens"))


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


def _config_summary(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "deepseek_api_key": "present" if env.get("DEEPSEEK_API_KEY") else "absent",
        "base_url": "configured" if env.get("DEEPSEEK_BASE_URL") else "default",
        "model": env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "timeout": env.get("DEEPSEEK_TIMEOUT", "120"),
        "max_tokens": env.get("DEEPSEEK_MAX_TOKENS", "512"),
    }


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


def build_diagnostics(workspace: Path, evidence: Path | None = None, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    config = _config_summary(env)
    runtime = _runtime_summary(workspace)
    python_ok = sys.version_info >= (3, 11)
    checks.append(_check("python_version", "pass" if python_ok else "warn", "Python >= 3.11 required", version=runtime["python"]))
    if not python_ok:
        warnings.append("python_below_supported_version")
    if not workspace.exists() or not workspace.is_dir():
        checks.append(_check("workspace", "fail", "workspace path must exist and be a directory", path=str(workspace)))
    else:
        checks.append(_check("workspace", "pass", "workspace exists", path=str(workspace.resolve())))
    session_store = workspace / ".deepseek-runtime" / "sessions"
    writable_target = session_store if session_store.exists() else session_store.parent if session_store.parent.exists() else workspace
    session_writable = workspace.exists() and os.access(writable_target, os.W_OK)
    checks.append(_check("session_store_writable", "pass" if session_writable else "fail", "session store parent is writable" if session_writable else "session store parent is not writable", path=str(session_store)))
    checks.append(_check("entrypoints", "pass" if runtime["entrypoints"]["deepseek-runtime"] else "warn", "deepseek-runtime entrypoint is available" if runtime["entrypoints"]["deepseek-runtime"] else "deepseek-runtime entrypoint is not on PATH", entrypoints=runtime["entrypoints"]))
    api_key_present = config["deepseek_api_key"] == "present"
    checks.append(_check("api_key", "pass" if api_key_present else "warn", "DEEPSEEK_API_KEY is present" if api_key_present else "DEEPSEEK_API_KEY is absent; live provider calls will fail"))
    if not api_key_present:
        warnings.append("api_key_absent")
    usage_summary, evidence_check, evidence_warnings = evidence_summary(evidence)
    checks.append(evidence_check)
    warnings.extend(evidence_warnings)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not any(check["status"] == "fail" for check in checks),
        "checks": checks,
        "config_summary": config,
        "runtime": runtime,
        "diagnostics": {"session_store": str(session_store), "evidence_summary": usage_summary},
        "warnings": warnings,
    }
