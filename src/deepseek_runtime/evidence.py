from __future__ import annotations

import hashlib
import json
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = {"authorization", "api_key", "reasoning_content"}


def wire_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: Any) -> str:
    return sha256_bytes(wire_json(value))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: (REDACTED if key.lower() in SENSITIVE_KEYS else redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def response_evidence(body: dict[str, Any]) -> dict[str, Any]:
    choices = []
    for choice in body.get("choices", []):
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = message.get("content")
        content_bytes = wire_json(content) if content is not None else b""
        choices.append(
            {
                "finish_reason": choice.get("finish_reason"),
                "message_fields": sorted(message),
                "tool_names": [call.get("function", {}).get("name") for call in message.get("tool_calls") or []],
                "has_content": bool(message.get("content")),
                "content_sha256": sha256_bytes(content_bytes) if content is not None else None,
                "content_bytes": len(content_bytes),
                "has_reasoning_content": bool(message.get("reasoning_content")),
            }
        )
    return {"top_level_fields": sorted(body), "choices": choices}


def request_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    messages = []
    for message in payload.get("messages", []):
        content = message.get("content")
        content_bytes = wire_json(content) if content is not None else b""
        messages.append(
            {
                "role": message.get("role"),
                "fields": sorted(message),
                "content_sha256": sha256_bytes(content_bytes) if content is not None else None,
                "content_bytes": len(content_bytes),
                "has_reasoning_content": bool(message.get("reasoning_content")),
                "tool_names": [call.get("function", {}).get("name") for call in message.get("tool_calls") or []],
            }
        )
    return {
        "top_level_fields": sorted(payload),
        "model": payload.get("model"),
        "messages": messages,
        "tool_names": [tool.get("function", {}).get("name") for tool in payload.get("tools") or []],
        "thinking": payload.get("thinking"),
        "reasoning_effort": payload.get("reasoning_effort"),
        "stream": payload.get("stream", False),
    }
