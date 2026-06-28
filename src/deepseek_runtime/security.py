"""
安全层（Security Layer）—— 本地 Agent 怎么保护自己？

❓ 问：AI Agent 在本地运行，它可能做什么危险的事？
💡 答：Agent 能读文件、写文件、执行命令。如果没有任何限制，它可能：
   - 读取你的密码文件（/etc/passwd）
   - 删除重要数据（rm -rf /）
   - 执行危险的 Git 操作（git push --force）
   - 访问外部网络（curl 恶意网站）

❓ 问：那 security.py 做了什么来防止这些？
💡 答：它定义了三个安全机制——
   1. WorkspaceSandbox（工作区沙箱）：把 Agent 限制在指定的目录内
   2. PermissionPolicy（权限策略）：对每种操作决定"允许/拒绝/询问"
   3. ChangeManager（变更管理器）：追踪文件修改，支持回滚

参考 llm-harness-agent 论文 A1（Agent Harness Survey）中 Harness 六组件的
"安全/沙箱"层：Agent 不能随意操作文件系统，必须经过权限检查。
"""

from __future__ import annotations

import difflib  # 生成文件差异对比（diff）
import fnmatch  # 文件名模式匹配（类似于 *.txt 的 glob 模式）
import hashlib  # 哈希计算
import os
import subprocess  # 执行系统命令
import tempfile  # 临时文件
import time
import uuid  # 唯一 ID
from dataclasses import dataclass, field
from enum import Enum  # 枚举类型（有限个选项）
from pathlib import Path
from typing import Callable, Sequence


# ===== Risk（风险等级）=====

# ❓ 问：为什么要把操作分类成不同风险？
# 💡 答：就像过马路要看红绿灯一样——
#   绿灯（READ）= 安全，可以直接走
#   黄灯（SHELL_SAFE）= 需要注意
#   红灯（DELETE/SHELL_DANGEROUS）= 必须停下来检查
#   分类的目的是让 Agent 和安全策略能快速判断每个操作的危险程度。

class Risk(str, Enum):
    """操作的风险分类——决定了安全策略该如何应对"""
    READ = "read"  # 只读操作（读文件）。最安全
    WRITE = "write"  # 写操作（修改文件）。中等风险
    DELETE = "delete"  # 删除操作。高风险——数据可能丢失
    SHELL_SAFE = "shell-safe"  # 相对安全的 shell 命令
    SHELL_DANGEROUS = "shell-dangerous"  # 危险 shell 命令（rm、sudo 等）
    NETWORK = "network"  # 网络操作（curl、wget 等）
    GIT_MUTATING = "git-mutating"  # 修改 Git 仓库（commit、push 等）


# ===== Decision（权限决策结果）=====

class Decision(str, Enum):
    """权限策略的三种决策结果"""
    ALLOW = "allow"  # 绿灯：允许执行
    ASK = "ask"  # 黄灯：询问用户意见
    DENY = "deny"  # 红灯：拒绝执行


# ===== PermissionRequest（权限请求）=====

@dataclass(frozen=True)
class PermissionRequest:
    """一次权限请求——包含了"谁想做什么"的信息"""
    risk: Risk  # 操作的风险等级
    path: str | None = None  # 操作涉及的文件路径
    command: tuple[str, ...] = ()  # 要执行的命令


# ===== PermissionRule（权限规则）=====

# ❓ 问：一条权限规则是怎么工作的？
# 💡 答：它把"什么条件下允许/拒绝/询问"编码成一条规则。
#   比如："对所有 WRITE 操作，如果是 docs/* 目录就 ASK，
#   其他目录就 DENY"。规则按顺序检查，第一条匹配的生效。

@dataclass(frozen=True)
class PermissionRule:
    """一条权限规则——定义了在什么条件下采取什么决策"""
    risk: Risk  # 匹配的风险类型
    decision: Decision  # 匹配后的决策
    path_glob: str = "*"  # 文件路径通配符（默认匹配所有）
    command_prefix: tuple[str, ...] = ()  # 命令前缀匹配

    def matches(self, request: PermissionRequest) -> bool:
        """判断这条规则是否匹配给定的请求"""
        if request.risk != self.risk:
            return False
        if request.path is not None and not fnmatch.fnmatch(request.path, self.path_glob):
            return False
        if self.command_prefix and request.command[:len(self.command_prefix)] != self.command_prefix:
            return False
        return True


# ===== 命令脱敏 =====

def _sanitize_command(command: Sequence[str]) -> list[str]:
    """
    脱敏命令中的敏感参数（如 API Key、密码等）
    例：curl --token sk-123 → curl --token [REDACTED]
    """
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


# ===== PermissionPolicy（权限策略）=====

@dataclass
class PermissionPolicy:
    """
    权限策略的执行者。默认拒绝所有非只读操作，
    通过 rules 列表逐个覆盖默认行为。
    参考 llm-harness-agent 论文 A5 中关于 Agent 治理（Governance）的讨论。
    """
    rules: list[PermissionRule] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)

    def decide(self, request: PermissionRequest) -> Decision:
        """对一次权限请求做出决策，并记录审计日志"""
        decision = Decision.ALLOW if request.risk is Risk.READ else Decision.DENY
        for rule in self.rules:
            if rule.matches(request):
                decision = rule.decision
        self.audit_events.append({
            "event": "permission_decision",
            "timestamp_unix": int(time.time()),
            "risk": request.risk.value,
            "path": request.path,
            "command": _sanitize_command(request.command),
            "decision": decision.value,
        })
        return decision


# ===== 自定义异常 =====

class SandboxViolation(ValueError):
    """路径越过了工作区边界"""
    pass

class PermissionDenied(PermissionError):
    """权限策略拒绝了操作"""
    pass


# ===== CommandResult（命令执行结果）=====

@dataclass(frozen=True)
class CommandResult:
    """命令执行的结果封装"""
    returncode: int  # 退出码（0=成功）
    stdout: str  # 标准输出
    stderr: str  # 错误输出
    truncated: bool  # 是否被截断


# ===== WorkspaceSandbox（工作区沙箱）=====

# ❓ 问：沙箱（Sandbox）在计算机里是什么意思？
# 💡 答：就像儿童玩的沙箱——你可以在沙箱里尽情玩，
#   但你不能跑出沙箱的范围。沙箱是一种隔离机制，
#   限制 Agent 能做什么、能去哪里。

class WorkspaceSandbox:
    """
    ❓ 问：WorkspaceSandbox 提供了哪些保护？
    💡 答：三个保护——
       1. 路径隔离（resolve()）：确保文件路径不会越界
       2. 命令分类（classify_command()）：判断命令的危险等级
       3. 命令执行（run()）：在沙箱内安全执行命令

    参考 llm-harness-agent 论文 C3: OpenHands ——
    沙箱化执行环境是 Harness 安全层的参考实现。
    """
    NETWORK_COMMANDS = {"curl", "wget", "nc", "ncat", "ssh", "scp", "sftp", "ftp", "telnet"}
    DANGEROUS_COMMANDS = {"rm", "dd", "mkfs", "mount", "umount", "shutdown", "reboot", "sudo", "su"}
    GIT_MUTATING = {
        "add", "am", "apply", "branch", "checkout", "cherry-pick",
        "clean", "commit", "merge", "mv", "rebase", "reset",
        "restore", "rm", "stash", "switch", "tag",
    }

    def __init__(self, root: Path, policy: PermissionPolicy | None = None):
        """初始化沙箱：指定工作区根目录和权限策略"""
        self.root = root.resolve()
        self.policy = policy or PermissionPolicy()

    def resolve(self, raw: str | Path) -> Path:
        """将路径解析为绝对路径，并检查是否在沙箱内。越界则抛出异常。"""
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
        """返回相对于工作区的路径（用于审计日志，避免暴露绝对路径）"""
        return str(path.relative_to(self.root))

    def classify_command(self, command: Sequence[str]) -> Risk:
        """根据可执行文件名判断命令的风险等级"""
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

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path = ".",
        timeout: float = 30.0,
        max_output: int = 100_000,
    ) -> CommandResult:
        """在沙箱内安全执行命令（禁止字符串命令防注入）"""
        if isinstance(command, (str, bytes)):
            raise SandboxViolation("shell commands must be an argument array")
        normalized = tuple(str(item) for item in command)
        risk = self.classify_command(normalized)
        resolved_cwd = self.resolve(cwd)
        decision = self.policy.decide(
            PermissionRequest(risk=risk, path=self.relative(resolved_cwd), command=normalized)
        )
        if decision is not Decision.ALLOW:
            raise PermissionDenied(f"{risk.value} command requires {decision.value}")
        completed = subprocess.run(
            normalized, cwd=resolved_cwd, shell=False,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        truncated = len(stdout) + len(stderr) > max_output
        if truncated:
            remaining = max_output
            stdout = stdout[:remaining]
            remaining -= len(stdout)
            stderr = stderr[:max(0, remaining)]
        return CommandResult(completed.returncode, stdout, stderr, truncated)


# ===== content_sha256（文件内容哈希）=====

def content_sha256(content: bytes) -> str:
    """计算文件内容的 SHA-256 指纹，用于验证文件在修改前未被其他操作改动"""
    return hashlib.sha256(content).hexdigest()


# ===== FileChange / ChangeSet / RollbackToken =====

@dataclass(frozen=True)
class FileChange:
    """一次文件修改的描述：路径、修改前的哈希（验证用）、新内容"""
    path: str
    original_sha256: str | None  # None = 创建新文件
    new_content: str

@dataclass(frozen=True)
class ChangeSet:
    """一组原子化的文件修改。要么全部成功，要么全部回滚。"""
    changes: tuple[FileChange, ...]
    change_set_id: str = field(default_factory=lambda: uuid.uuid4().hex)

@dataclass
class RollbackToken:
    """回滚令牌：保存了修改前的原始内容，用于撤销修改。每个令牌只能使用一次。"""
    change_set_id: str
    originals: dict[Path, bytes | None]
    consumed: bool = False


# ===== ChangeManager（变更管理器）=====

# ❓ 问：ChangeManager 的核心职责是什么？
# 💡 答：协调文件修改的完整生命周期——
#   1. preview() —— 生成 diff 差异对比（给用户审批）
#   2. apply() —— 原子写入+自动回滚（事务性提交）
#   3. rollback() —— 撤销修改，恢复原始内容

class ChangeManager:
    """文件变更管理器：预览 → 应用（原子写入）→ 回滚"""
    def __init__(
        self,
        sandbox: WorkspaceSandbox,
        policy: PermissionPolicy | None = None,
        replace: Callable[[str | os.PathLike[str], str | os.PathLike[str]], None] = os.replace,
    ):
        self.sandbox = sandbox
        self.policy = policy or sandbox.policy
        self.replace = replace
        self.audit_events: list[dict[str, object]] = []

    def _current(self, path: Path) -> bytes | None:
        """读取文件的当前内容（文件不存在则返回 None）"""
        return path.read_bytes() if path.exists() else None

    def _validate(self, change: FileChange) -> tuple[Path, bytes | None]:
        """验证修改的合法性：路径在沙箱内、哈希匹配、有写入权限"""
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
        """生成 unified diff，展示给用户看修改前后对比"""
        chunks: list[str] = []
        for change in change_set.changes:
            path = self.sandbox.resolve(change.path)
            current = self._current(path)
            before = (current or b"").decode("utf-8", errors="replace").splitlines(keepends=True)
            after = change.new_content.splitlines(keepends=True)
            chunks.extend(difflib.unified_diff(before, after, fromfile=f"a/{change.path}", tofile=f"b/{change.path}"))
        return "".join(chunks)

    def apply(self, change_set: ChangeSet) -> RollbackToken:
        """
        原子应用修改：先验证全部 → 再逐个写入 → 失败则自动回滚
        参考 llm-harness-agent 论文 A1 中关于事务性 Agent 操作的讨论。
        """
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
        """恢复文件到指定内容（None = 删除文件）"""
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
        """回滚：恢复到修改前的内容。每个令牌只能回滚一次（幂等性保护）"""
        if token.consumed:
            raise ValueError("rollback token already consumed")
        self._restore(token.originals)
        token.consumed = True
        self.audit_events.append({"event": "changeset_rolled_back", "change_set_id": token.change_set_id})
