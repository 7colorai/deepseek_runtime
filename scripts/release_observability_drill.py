#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deepseek_runtime.observability import summarize_observability

DEFAULT_PRICING = {
    "snapshot_date": "2026-06-07",
    "source": "https://api-docs.deepseek.com/quick_start/pricing",
    "unit_tokens": 1_000_000,
    "models": {
        "deepseek-v4-flash": {"cache_hit_input": 0.014, "cache_miss_input": 0.14, "output": 0.28},
        "deepseek-v4-pro": {"cache_hit_input": 0.14, "cache_miss_input": 1.4, "output": 2.8},
    },
}

FIXTURE_ROWS: tuple[dict[str, Any], ...] = (
    {"task_id": "OBS01", "model": "deepseek-v4-flash", "route_reason": "low-cost simple edit", "success": True, "first_completion": True, "tokens": {"prompt_cache_hit_tokens": 64, "prompt_cache_miss_tokens": 160, "completion_tokens": 40, "total_tokens": 264}},
    {"task_id": "OBS02", "model": "deepseek-v4-flash", "route_reason": "low-cost retry after failed test", "success": False, "first_completion": False, "tokens": {"prompt_cache_hit_tokens": 96, "prompt_cache_miss_tokens": 80, "completion_tokens": 24, "total_tokens": 200}},
    {"task_id": "OBS03", "model": "deepseek-v4-pro", "route_reason": "higher accuracy for rollback-sensitive edit", "success": True, "first_completion": False, "tokens": {"prompt_cache_hit_tokens": 128, "prompt_cache_miss_tokens": 220, "completion_tokens": 60, "total_tokens": 408}},
)


def _load_json_or_jsonl(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def run_observability_drill(evidence: Path | None = None, pricing_path: Path | None = None) -> dict[str, Any]:
    pricing = DEFAULT_PRICING if pricing_path is None else json.loads(pricing_path.read_text(encoding="utf-8"))
    data: Any = {"rows": list(FIXTURE_ROWS)} if evidence is None else _load_json_or_jsonl(evidence)
    source = "deterministic-fixture" if evidence is None else str(evidence)
    return summarize_observability(data, pricing, source)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic route/cache/usage/cost observability checks")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--pricing", type=Path)
    args = parser.parse_args()
    result = run_observability_drill(args.evidence, args.pricing)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
