#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deepseek_runtime.client import DeepSeekClient, RuntimeSettings
from deepseek_runtime.evidence import request_evidence, response_evidence, sha256_bytes, wire_json


SMOKE_PROMPT = "DeepSeek runtime live smoke: return one concise sentence confirming the official chat endpoint responded."


def _choice_message(body: dict[str, Any]) -> dict[str, Any]:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {}
    return message if isinstance(message, dict) else {}


def _text_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {"present": False, "sha256": None, "bytes": 0}
    raw = wire_json(value)
    return {"present": True, "sha256": sha256_bytes(raw), "bytes": len(raw)}


def run_live_smoke() -> dict[str, Any]:
    settings = RuntimeSettings.from_env()
    client = DeepSeekClient(settings)
    payload = {
        "messages": [
            {"role": "system", "content": "You are validating a runtime integration. Do not echo secrets."},
            {"role": "user", "content": SMOKE_PROMPT},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": os.getenv("DEEPSEEK_REASONING_EFFORT", "high"),
        "stream": False,
    }
    result = client.chat(payload)
    message = _choice_message(result.body)
    content = message.get("content")
    reasoning_content = message.get("reasoning_content")
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
    rendered = json.dumps(safe_output, ensure_ascii=False)
    api_key = settings.api_key
    leaks = {
        "api_key_absent": not api_key or api_key not in rendered,
        "prompt_absent": SMOKE_PROMPT not in rendered,
        "response_content_absent": not isinstance(content, str) or content not in rendered,
        "reasoning_content_absent": not isinstance(reasoning_content, str) or reasoning_content not in rendered,
    }
    safe_output["leak_checks"] = leaks
    safe_output["success"] = bool(safe_output["success"] and all(leaks.values()))
    return safe_output


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the official DeepSeek API once and write only redacted structural evidence")
    parser.add_argument("--out", type=Path, default=Path("live-smoke.json"))
    args = parser.parse_args()
    result = run_live_smoke()
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
