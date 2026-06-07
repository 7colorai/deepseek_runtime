from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .evidence import sha256_bytes, wire_json


@dataclass(frozen=True)
class RuntimeSettings:
    api_key: str = field(repr=False)
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    timeout: float = 120.0
    max_tokens: int = 512

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is required for live DeepSeek requests")
        return cls(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "120")),
            max_tokens=int(os.getenv("DEEPSEEK_MAX_TOKENS", "512")),
        )


@dataclass
class ProviderResult:
    status: int
    elapsed_ms: int
    body: dict[str, Any]
    request_fingerprint: str
    error: str | None = None
    error_class: str | None = None
    request_id: str | None = None
    request_payload: dict[str, Any] | None = None

    @property
    def usage(self) -> dict[str, Any]:
        return self.body.get("usage", {}) if isinstance(self.body, dict) else {}


class Transport(Protocol):
    def __call__(self, method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float) -> tuple[int, dict[str, str], bytes]: ...


class StreamTransport(Protocol):
    def __call__(self, method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float) -> tuple[int, dict[str, str], list[tuple[int, bytes]]]: ...


def urllib_transport(method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def urllib_stream_transport(method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float) -> tuple[int, dict[str, str], list[tuple[int, bytes]]]:
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunks = [(round((time.monotonic() - started) * 1000), line) for line in response]
            return response.status, dict(response.headers.items()), chunks
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), [(round((time.monotonic() - started) * 1000), exc.read())]


class DeepSeekClient:
    def __init__(
        self,
        settings: RuntimeSettings,
        transport: Transport = urllib_transport,
        stream_transport: StreamTransport = urllib_stream_transport,
    ):
        self.settings = settings
        self.transport = transport
        self.stream_transport = stream_transport

    def models(self) -> ProviderResult:
        return self._request("GET", "/models", None)

    def chat(self, payload: dict[str, Any]) -> ProviderResult:
        complete = {"model": self.settings.model, "max_tokens": self.settings.max_tokens, **payload}
        return self._request("POST", "/chat/completions", complete)

    def chat_stream(self, payload: dict[str, Any]) -> ProviderResult:
        complete = {"model": self.settings.model, "max_tokens": self.settings.max_tokens, **payload, "stream": True}
        data = wire_json(complete)
        request_hash = sha256_bytes(data)
        started = time.monotonic()
        try:
            status, headers, chunks = self.stream_transport(
                "POST",
                self.settings.base_url + "/chat/completions",
                {
                    "Authorization": f"Bearer {self.settings.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                data,
                self.settings.timeout,
            )
            events: list[dict[str, Any]] = []
            first_event_ms = None
            for offset_ms, raw in chunks:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    continue
                try:
                    import json

                    event = json.loads(value)
                except ValueError:
                    continue
                first_event_ms = offset_ms if first_event_ms is None else first_event_ms
                events.append(event)
            usage = next((event.get("usage", {}) for event in reversed(events) if event.get("usage")), {})
            choices = [choice for event in events for choice in event.get("choices", []) if isinstance(choice, dict)]
            deltas = [choice.get("delta", {}) for choice in choices if isinstance(choice.get("delta", {}), dict)]
            body = {
                "usage": usage,
                "stream_evidence": {
                    "event_count": len(events),
                    "first_event_ms": first_event_ms,
                    "top_level_fields": sorted({key for event in events for key in event}),
                    "delta_fields": sorted({key for delta in deltas for key in delta}),
                    "finish_reasons": sorted({str(choice.get("finish_reason")) for choice in choices if choice.get("finish_reason") is not None}),
                    "has_content": any(bool(delta.get("content")) for delta in deltas),
                    "has_reasoning_content": any(bool(delta.get("reasoning_content")) for delta in deltas),
                    "tool_names": sorted(
                        {
                            str(call.get("function", {}).get("name"))
                            for delta in deltas
                            for call in delta.get("tool_calls") or []
                            if call.get("function", {}).get("name")
                        }
                    ),
                },
            }
            error = None if status < 400 else "stream request failed"
            error_class = None if status < 400 else "http"
            request_id = headers.get("x-request-id") or headers.get("X-Request-Id")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status, body, error, error_class, request_id = 0, {"error": {"message": str(exc)}}, str(exc), "transport", None
        return ProviderResult(status, round((time.monotonic() - started) * 1000), body, request_hash, error, error_class, request_id, complete)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None) -> ProviderResult:
        import json

        data = wire_json(payload) if payload is not None else None
        request_hash = sha256_bytes(data or b"")
        started = time.monotonic()
        try:
            status, headers, raw = self.transport(
                method,
                self.settings.base_url + path,
                {"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json", "Accept": "application/json"},
                data,
                self.settings.timeout,
            )
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"error": {"message": raw.decode(errors="replace")}}
            error = body.get("error", {}).get("message") if status >= 400 else None
            error_class = "http" if status >= 400 else None
            request_id = headers.get("x-request-id") or headers.get("X-Request-Id")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            status, body, error, error_class, request_id = 0, {"error": {"message": str(exc)}}, str(exc), "transport", None
        return ProviderResult(status, round((time.monotonic() - started) * 1000), body, request_hash, error, error_class, request_id, payload)
