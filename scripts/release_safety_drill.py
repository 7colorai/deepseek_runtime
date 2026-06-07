#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deepseek_runtime.security import ChangeManager, ChangeSet, Decision, FileChange, PermissionDenied, PermissionPolicy, PermissionRequest, PermissionRule, Risk, SandboxViolation, WorkspaceSandbox, content_sha256
from deepseek_runtime.session import SessionState, ToolCallRecord, resume_tool_calls


@dataclass
class DrillCheck:
    name: str
    ok: bool
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "evidence": self.evidence}


def _check(name: str, run: Callable[[], dict[str, Any]]) -> DrillCheck:
    try:
        return DrillCheck(name, True, run())
    except Exception as exc:
        return DrillCheck(name, False, {"error_class": type(exc).__name__, "error": str(exc)})


def _permission_check() -> dict[str, Any]:
    policy = PermissionPolicy([PermissionRule(Risk.WRITE, Decision.ASK, "docs/*"), PermissionRule(Risk.WRITE, Decision.ALLOW, "docs/approved.txt")])
    decisions = {
        "read": policy.decide(PermissionRequest(Risk.READ, "a.txt")).value,
        "write_default": policy.decide(PermissionRequest(Risk.WRITE, "src/a.py")).value,
        "write_ask": policy.decide(PermissionRequest(Risk.WRITE, "docs/plan.md")).value,
        "write_allowed": policy.decide(PermissionRequest(Risk.WRITE, "docs/approved.txt")).value,
    }
    policy.decide(PermissionRequest(Risk.NETWORK, command=("curl", "--token", "secret", "api_key=bad")))
    serialized = json.dumps(policy.audit_events, ensure_ascii=False)
    if "secret" in serialized or "api_key=bad" in serialized:
        raise AssertionError("permission audit leaked command secret")
    expected = {"read": "allow", "write_default": "deny", "write_ask": "ask", "write_allowed": "allow"}
    if decisions != expected:
        raise AssertionError(f"unexpected permission decisions: {decisions}")
    return {"decisions": decisions, "audit_events": len(policy.audit_events), "redacted_command_audit": True}


def _sandbox_check(workspace: Path) -> dict[str, Any]:
    policy = PermissionPolicy([PermissionRule(Risk.SHELL_SAFE, Decision.ALLOW, command_prefix=(sys.executable,))])
    sandbox = WorkspaceSandbox(workspace, policy)
    path_escape_denied = network_denied = string_shell_denied = False
    try:
        sandbox.resolve("../escape")
    except SandboxViolation:
        path_escape_denied = True
    try:
        sandbox.run(("curl", "https://example.com"))
    except PermissionDenied:
        network_denied = True
    try:
        sandbox.run("echo unsafe")
    except SandboxViolation:
        string_shell_denied = True
    result = sandbox.run((sys.executable, "-c", "print('ok')"), max_output=10)
    if not (path_escape_denied and network_denied and string_shell_denied and result.returncode == 0):
        raise AssertionError("sandbox checks did not all pass")
    return {"path_escape_denied": path_escape_denied, "network_denied": network_denied, "string_shell_denied": string_shell_denied, "safe_shell_returncode": result.returncode}


def _changeset_check(workspace: Path) -> dict[str, Any]:
    target = workspace / "notes.txt"
    target.write_text("old\n", encoding="utf-8")
    manager = ChangeManager(WorkspaceSandbox(workspace, PermissionPolicy([PermissionRule(Risk.WRITE, Decision.ALLOW)])))
    change_set = ChangeSet((FileChange("notes.txt", content_sha256(b"old\n"), "new\n"),))
    preview = manager.preview(change_set)
    if "-old" not in preview or "+new" not in preview:
        raise AssertionError("diff preview did not include expected change")
    token = manager.apply(change_set)
    manager.rollback(token)
    if target.read_text(encoding="utf-8") != "old\n":
        raise AssertionError("rollback failed")
    return {"diff_sha256": hashlib.sha256(preview.encode()).hexdigest(), "change_set_id": change_set.change_set_id, "rollback_consumed": token.consumed}


def _session_resume_check() -> dict[str, Any]:
    calls = 0
    checkpoints: list[str] = []

    def handler(arguments: dict[str, Any]) -> Any:
        nonlocal calls
        calls += 1
        return arguments["value"]

    state = SessionState(tool_calls=[ToolCallRecord("write", {"value": 1}, True, status="succeeded", result=1), ToolCallRecord("write", {"value": 2}, True)])
    resume_tool_calls(state, {"write": handler}, lambda value: checkpoints.append(value.tool_calls[1].status))
    if calls != 1 or [call.status for call in state.tool_calls] != ["succeeded", "succeeded"]:
        raise AssertionError("resume repeated a completed side effect or failed pending work")
    return {"executed_pending_calls": calls, "final_statuses": [call.status for call in state.tool_calls], "checkpoint_transitions": checkpoints}


def run_safety_drill() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="deepseek-runtime-safety-") as directory:
        workspace = Path(directory)
        checks = [
            _check("permission_policy", _permission_check),
            _check("workspace_sandbox", lambda: _sandbox_check(workspace)),
            _check("diff_apply_rollback", lambda: _changeset_check(workspace)),
            _check("session_resume", _session_resume_check),
        ]
    return {"schema_version": "1.0", "created_at": datetime.now(timezone.utc).isoformat(), "success": all(check.ok for check in checks), "checks": [check.to_dict() for check in checks], "warning": "Safety drill uses deterministic local fixtures, not full task coverage."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic release safety checks")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run_safety_drill()
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
