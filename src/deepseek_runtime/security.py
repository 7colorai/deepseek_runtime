from __future__ import annotations

import difflib
import fnmatch
import hashlib
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence


class Risk(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SHELL_SAFE = "shell-safe"
    SHELL_DANGEROUS = "shell-dangerous"
    NETWORK = "network"
    GIT_MUTATING = "git-mutating"


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRequest:
    risk: Risk
    path: str | None = None
    command: tuple[str, ...] = ()


@dataclass(frozen=True)
class PermissionRule:
    risk: Risk
    decision: Decision
    path_glob: str = "*"
    command_prefix: tuple[str, ...] = ()

    def matches(self, request: PermissionRequest) -> bool:
        if request.risk != self.risk:
            return False
        if request.path is not None and not fnmatch.fnmatch(request.path, self.path_glob):
            return False
        return not self.command_prefix or request.command[: len(self.command_prefix)] == self.command_prefix


def _sanitize_command(command: Sequence[str]) -> list[str]:
    sanitized: list[str] = []
    hide_next = False
    for argument in command:
        lower = argument.lower()
        if hide_next:
            sanitized.append("[REDACTED]")
            hide_next = False
        elif lower in {"--token", "--api-key", "--password", "-p"}:
            sanitized.append(argument)
            hide_next = True
        elif any(marker in lower for marker in ("api_key=", "token=", "password=", "authorization=")):
            sanitized.append("[REDACTED]")
        else:
            sanitized.append(argument)
    return sanitized


@dataclass
class PermissionPolicy:
    rules: list[PermissionRule] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)

    def decide(self, request: PermissionRequest) -> Decision:
        decision = Decision.ALLOW if request.risk is Risk.READ else Decision.DENY
        for rule in self.rules:
            if rule.matches(request):
                decision = rule.decision
        self.audit_events.append(
            {
                "event": "permission_decision",
                "timestamp_unix": int(time.time()),
                "risk": request.risk.value,
                "path": request.path,
                "command": _sanitize_command(request.command),
                "decision": decision.value,
            }
        )
        return decision


class SandboxViolation(ValueError):
    pass


class PermissionDenied(PermissionError):
    pass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class WorkspaceSandbox:
    NETWORK_COMMANDS = {"curl", "wget", "nc", "ncat", "ssh", "scp", "sftp", "ftp", "telnet"}
    DANGEROUS_COMMANDS = {"rm", "dd", "mkfs", "mount", "umount", "shutdown", "reboot", "sudo", "su"}
    GIT_MUTATING = {"add", "am", "apply", "branch", "checkout", "cherry-pick", "clean", "commit", "merge", "mv", "rebase", "reset", "restore", "rm", "stash", "switch", "tag"}

    def __init__(self, root: Path, policy: PermissionPolicy | None = None):
        self.root = root.resolve()
        self.policy = policy or PermissionPolicy()

    def resolve(self, raw: str | Path) -> Path:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        if candidate.exists() or candidate.is_symlink():
            resolved = candidate.resolve()
        else:
            resolved = candidate.parent.resolve() / candidate.name
        if resolved != self.root and self.root not in resolved.parents:
            raise SandboxViolation(f"path escapes workspace: {raw}")
        return resolved

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def classify_command(self, command: Sequence[str]) -> Risk:
        if not command:
            raise SandboxViolation("command must not be empty")
        executable = Path(command[0]).name
        if executable in self.NETWORK_COMMANDS:
            return Risk.NETWORK
        if executable in self.DANGEROUS_COMMANDS:
            return Risk.SHELL_DANGEROUS
        if executable == "git" and len(command) > 1 and command[1] in self.GIT_MUTATING:
            return Risk.GIT_MUTATING
        return Risk.SHELL_SAFE

    def run(self, command: Sequence[str], *, cwd: str | Path = ".", timeout: float = 30.0, max_output: int = 100_000) -> CommandResult:
        if isinstance(command, (str, bytes)):
            raise SandboxViolation("shell commands must be an argument array")
        normalized = tuple(str(item) for item in command)
        risk = self.classify_command(normalized)
        resolved_cwd = self.resolve(cwd)
        decision = self.policy.decide(PermissionRequest(risk=risk, path=self.relative(resolved_cwd), command=normalized))
        if decision is not Decision.ALLOW:
            raise PermissionDenied(f"{risk.value} command requires {decision.value}")
        completed = subprocess.run(normalized, cwd=resolved_cwd, shell=False, capture_output=True, text=True, timeout=timeout, check=False)
        stdout = completed.stdout
        stderr = completed.stderr
        truncated = len(stdout) + len(stderr) > max_output
        if truncated:
            remaining = max_output
            stdout = stdout[:remaining]
            remaining -= len(stdout)
            stderr = stderr[: max(0, remaining)]
        return CommandResult(completed.returncode, stdout, stderr, truncated)


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class FileChange:
    path: str
    original_sha256: str | None
    new_content: str


@dataclass(frozen=True)
class ChangeSet:
    changes: tuple[FileChange, ...]
    change_set_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class RollbackToken:
    change_set_id: str
    originals: dict[Path, bytes | None]
    consumed: bool = False


class ChangeManager:
    def __init__(self, sandbox: WorkspaceSandbox, policy: PermissionPolicy | None = None, replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.replace):
        self.sandbox = sandbox
        self.policy = policy or sandbox.policy
        self.replace = replace
        self.audit_events: list[dict[str, object]] = []

    def _current(self, path: Path) -> bytes | None:
        return path.read_bytes() if path.exists() else None

    def _validate(self, change: FileChange) -> tuple[Path, bytes | None]:
        path = self.sandbox.resolve(change.path)
        current = self._current(path)
        if change.original_sha256 is None:
            if current is not None:
                raise ValueError(f"expected new file but path exists: {change.path}")
        elif current is None or content_sha256(current) != change.original_sha256:
            raise ValueError(f"stale original hash: {change.path}")
        decision = self.policy.decide(PermissionRequest(Risk.WRITE, self.sandbox.relative(path)))
        if decision is not Decision.ALLOW:
            raise PermissionDenied(f"write requires {decision.value}: {change.path}")
        return path, current

    def preview(self, change_set: ChangeSet) -> str:
        chunks: list[str] = []
        for change in change_set.changes:
            path = self.sandbox.resolve(change.path)
            current = self._current(path)
            before = (current or b"").decode("utf-8", errors="replace").splitlines(keepends=True)
            after = change.new_content.splitlines(keepends=True)
            chunks.extend(difflib.unified_diff(before, after, fromfile=f"a/{change.path}", tofile=f"b/{change.path}"))
        return "".join(chunks)

    def apply(self, change_set: ChangeSet) -> RollbackToken:
        validated = [(*self._validate(change), change) for change in change_set.changes]
        originals = {path: current for path, current, _ in validated}
        applied: list[Path] = []
        temps: list[Path] = []
        try:
            for path, _, change in validated:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
                temp = Path(temp_name)
                temps.append(temp)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(change.new_content)
                    handle.flush()
                    os.fsync(handle.fileno())
                self.replace(temp, path)
                applied.append(path)
            token = RollbackToken(change_set.change_set_id, originals)
            self.audit_events.append({"event": "changeset_applied", "change_set_id": change_set.change_set_id, "paths": [self.sandbox.relative(path) for path in applied]})
            return token
        except Exception:
            self._restore({path: originals[path] for path in applied})
            self.audit_events.append({"event": "changeset_apply_failed_rolled_back", "change_set_id": change_set.change_set_id, "paths": [self.sandbox.relative(path) for path in applied]})
            raise
        finally:
            for temp in temps:
                temp.unlink(missing_ok=True)

    def _restore(self, originals: dict[Path, bytes | None]) -> None:
        for path, content in originals.items():
            if content is None:
                path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.rollback.", dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)

    def rollback(self, token: RollbackToken) -> None:
        if token.consumed:
            raise ValueError("rollback token already consumed")
        self._restore(token.originals)
        token.consumed = True
        self.audit_events.append({"event": "changeset_rolled_back", "change_set_id": token.change_set_id})
