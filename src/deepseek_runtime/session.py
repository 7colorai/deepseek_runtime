from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .evidence import redact

SESSION_SCHEMA_VERSION = "1.0"
TOOL_STATES = {"pending", "running", "succeeded", "failed"}


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    side_effect: bool
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "pending"
    result: Any = None
    error: str | None = None

    def validate(self) -> None:
        if self.status not in TOOL_STATES:
            raise ValueError(f"unknown tool status: {self.status}")


@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    schema_version: str = SESSION_SCHEMA_VERSION
    step: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    change_sets: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        if self.schema_version != SESSION_SCHEMA_VERSION:
            raise ValueError(f"unsupported session schema version: {self.schema_version}")
        if self.step < 0:
            raise ValueError("session step must be non-negative")
        for call in self.tool_calls:
            call.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return redact(asdict(self))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SessionState":
        if value.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise ValueError(f"unsupported session schema version: {value.get('schema_version')}")
        state = cls(
            session_id=str(value["session_id"]),
            schema_version=str(value["schema_version"]),
            step=int(value.get("step", 0)),
            messages=list(value.get("messages", [])),
            tool_calls=[ToolCallRecord(**call) for call in value.get("tool_calls", [])],
            approvals=list(value.get("approvals", [])),
            change_sets=list(value.get("change_sets", [])),
            usage=dict(value.get("usage", {})),
            evidence=list(value.get("evidence", [])),
        )
        state.validate()
        return state


class SessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, session_id: str) -> Path:
        if not session_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in session_id):
            raise ValueError("invalid session id")
        return self.root / f"{session_id}.json"

    def save(self, state: SessionState) -> Path:
        destination = self.path(state.session_id)
        payload = json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            Path(temp_name).unlink(missing_ok=True)
        return destination

    def load(self, session_id: str) -> SessionState:
        try:
            value = json.loads(self.path(session_id).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupt session checkpoint: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError("corrupt session checkpoint: root must be an object")
        return SessionState.from_dict(value)


def resume_tool_calls(state: SessionState, handlers: dict[str, Callable[[dict[str, Any]], Any]], save: Callable[[SessionState], object] | None = None) -> SessionState:
    for call in state.tool_calls:
        call.validate()
        if call.status == "succeeded":
            continue
        call.status = "running"
        if save:
            save(state)
        try:
            call.result = handlers[call.name](call.arguments)
            call.error = None
            call.status = "succeeded"
        except Exception as exc:
            call.error = f"{type(exc).__name__}: {exc}"
            call.status = "failed"
        if save:
            save(state)
    return state
