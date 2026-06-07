from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .client import DeepSeekClient
from .diagnostics import build_diagnostics
from .evidence import redact, request_evidence, response_evidence, sha256_bytes, wire_json

ToolHandler = Callable[[dict[str, Any]], str]


@dataclass
class RuntimeResult:
    ok: bool
    final_text: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_class: str | None = None
    status: int | None = None
    step: int = 0

    def _text_summary(self, value: str | None) -> dict[str, Any]:
        if not value:
            return {"present": False, "sha256": None, "bytes": 0}
        raw = wire_json(value)
        return {"present": True, "sha256": sha256_bytes(raw), "bytes": len(raw)}

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "final_text": self._text_summary(self.final_text),
            "message_count": len(self.messages),
            "message_evidence": request_evidence({"messages": self.messages})["messages"],
            "usage": self.usage,
            "evidence": redact(self.evidence),
            "diagnostics": redact(self.diagnostics),
            "error": self.error,
            "error_class": self.error_class,
            "status": self.status,
            "step": self.step,
        }

    def to_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        if include_content:
            return redact(asdict(self))
        return self.to_safe_dict()


@dataclass
class DeepSeekRuntime:
    client: DeepSeekClient
    max_steps: int = 8

    def run(
        self,
        messages: list[dict[str, Any]],
        workspace: str | Path = ".",
        tools: dict[str, ToolHandler] | None = None,
    ) -> RuntimeResult:
        workspace_path = Path(workspace)
        active_messages = [dict(message) for message in messages]
        active_tools = tools or {}
        tool_specs = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Run {name}",
                    "parameters": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]},
                },
            }
            for name in sorted(active_tools)
        ]
        total_usage: dict[str, int] = {}
        evidence: list[dict[str, Any]] = []
        diagnostics = build_diagnostics(workspace_path)
        for step in range(1, self.max_steps + 1):
            payload: dict[str, Any] = {"messages": active_messages, "thinking": {"type": "enabled"}}
            if tool_specs:
                payload["tools"] = tool_specs
            result = self.client.chat(payload)
            for key, value in result.usage.items():
                if isinstance(value, int):
                    total_usage[key] = total_usage.get(key, 0) + value
            evidence.append(
                {
                    "step": step,
                    "status": result.status,
                    "elapsed_ms": result.elapsed_ms,
                    "request_fingerprint": result.request_fingerprint,
                    "request_id": result.request_id,
                    "usage": result.usage,
                    "request_evidence": request_evidence(result.request_payload or payload),
                    "response_evidence": response_evidence(result.body),
                    "error": result.error,
                    "error_class": result.error_class,
                }
            )
            if result.status != 200:
                return RuntimeResult(False, messages=active_messages, usage=total_usage, evidence=evidence, diagnostics=diagnostics, error=result.error, error_class=result.error_class, status=result.status, step=step)
            try:
                message = result.body["choices"][0]["message"]
            except (KeyError, IndexError, TypeError):
                return RuntimeResult(False, messages=active_messages, usage=total_usage, evidence=evidence, diagnostics=diagnostics, error="malformed provider response", step=step)
            active_messages.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                return RuntimeResult(True, final_text=message.get("content", ""), messages=active_messages, usage=total_usage, evidence=evidence, diagnostics=diagnostics, step=step)
            for call in calls:
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                    output = active_tools[name](arguments)
                except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
                    output = f"Tool error: {type(exc).__name__}: {exc}"
                active_messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": output})
        return RuntimeResult(False, messages=active_messages, usage=total_usage, evidence=evidence, diagnostics=diagnostics, error="maximum steps reached", step=self.max_steps)


@dataclass
class WorkspaceTools:
    root: str | Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    def _path(self, raw: str) -> Path:
        candidate = (self.root / raw).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("path escapes workspace")
        return candidate

    def read_file(self, args: dict[str, Any]) -> str:
        return self._path(str(args.get("input", ""))).read_text(encoding="utf-8")[:20_000]

    def search(self, args: dict[str, Any]) -> str:
        needle = str(args.get("input", ""))
        if not needle:
            raise ValueError("search input must not be empty")
        matches = []
        for path in self.root.rglob("*"):
            if path.is_file() and ".git" not in path.parts and path.stat().st_size < 1_000_000:
                try:
                    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if needle in line:
                            matches.append(f"{path.relative_to(self.root)}:{number}:{line[:200]}")
                            if len(matches) >= 100:
                                return "\n".join(matches)
                except (UnicodeDecodeError, OSError):
                    pass
        return "\n".join(matches) or "No matches"

    def catalog(self) -> dict[str, ToolHandler]:
        return {"read_file": self.read_file, "search": self.search}
