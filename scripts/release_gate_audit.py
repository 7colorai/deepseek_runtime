# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 shebang（释伴行），告诉操作系统用 python3 解释器来运行这个脚本。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是做什么的？
# 💡 让类型注解延迟求值，提升运行性能并支持前向引用。
from __future__ import annotations

# ❓ 这里导入的标准库各有什么用？
# 💡 - argparse：解析命令行参数（--release-drill-result, --live-smoke-result, --manifest, --out）
#    - json：从文件加载 JSON 数据、序列化审计结果
#    - datetime/timezone：生成 UTC 时间戳
#    - pathlib.Path：面向对象路径操作
#    - typing.Any：动态类型注解
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ❓ ROOT 是做什么的？
# 💡 项目根目录——当前脚本的父目录的父目录。
#    用于后续检查项目根目录下必需的文件是否存在。
ROOT = Path(__file__).resolve().parents[1]

# ❓ REQUIRED_DOCS 是什么？
# 💡 一个元组（不可变列表），列出了每次发布前必须存在的文档文件。
#    发布门禁会检查这些文件是否都存在。
#    - README.md: 项目说明文档
#    - docs/api.md: API 使用文档
#    - docs/integration-guide.md: 集成指南
#    - docs/physical-traits.md: 物理特性文档
#    - docs/known-unknowns.md: 已知问题清单
#    - docs/hosting-roadmap.md: 托管路线图
#    - SECURITY.md: 安全策略文档
#    - TROUBLESHOOTING.md: 故障排除指南
#    参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于发布门禁（release gates）
#    的讨论：发布前必须满足一系列自动检查条件，包括文档完整性。
REQUIRED_DOCS = (
    "README.md",
    "docs/api.md",
    "docs/integration-guide.md",
    "docs/physical-traits.md",
    "docs/known-unknowns.md",
    "docs/hosting-roadmap.md",
    "SECURITY.md",
    "TROUBLESHOOTING.md",
)


# ❓ _load 辅助函数是做什么的？
# 💡 从指定路径读取 JSON 文件并解析，确保返回的是一个字典（JSON 对象）。
#    如果文件不包含 JSON 对象（比如是一个 JSON 数组或字符串），则抛出错误。
def _load(path: Path) -> dict[str, Any]:
    # ❓ read_text + json.loads 在做什么？
    # 💡 先用 read_text 读取文件的全部内容为字符串，
    #    再用 json.loads 解析为 Python 对象。
    value = json.loads(path.read_text(encoding="utf-8"))
    # ❓ 为什么要检查 isinstance(value, dict)？
    # 💡 JSON 文件可以包含多种顶层结构：对象（{}）、数组（[]）、字符串、数字等。
    #    这里的期望是顶层结构必须是字典（对象），否则说明文件格式不对。
    #    例如如果 JSON 文件是 [1, 2, 3]（数组），这里就会抛 ValueError。
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


# ❓ _check 辅助函数在做什么？
# 💡 创建一个标准的审计检查项字典，包含三个字段：
#    - name: 检查名称（如 "release_drill_success"）
#    - ok: 布尔值，检查是否通过
#    - evidence: 与该检查相关的证据数据字典
#    这个函数简化了创建检查项的重复代码。
def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


# ❓ audit 是核心审计函数吗？
# 💡 是的。它汇总所有发布门禁检查，生成一个完整的审计报告。
#    它会检查：
#    1. 发布演练（release drill）结果是否成功
#    2. 实时 API 烟雾测试（live smoke）是否成功且状态码为 200
#    3. 烟雾测试是否成功脱敏（没有泄露敏感信息）
#    4. 所有必需文档是否存在
#    5. 发布清单（manifest）中所有构件的 SHA-256 是否有效（如果提供了清单文件）
# ❓ 参数说明：
# 💡 - release_drill_result: 发布演练输出的 JSON 文件路径
#    - live_smoke_result: 烟雾测试输出的 JSON 文件路径
#    - manifest: 发布清单文件路径（可选，为 None 时跳过构件检查）
def audit(release_drill_result: Path, live_smoke_result: Path, manifest: Path | None = None) -> dict[str, Any]:
    # ❓ checks 列表用来做什么？
    # 💡 一个列表，收集所有检查项的结果。初始为空，逐个添加。
    checks: list[dict[str, Any]] = []
    # ❓ 加载两个结果文件
    # 💡 用 _load 函数分别读取发布演练和烟雾测试的 JSON 输出。
    #    这两个文件是前面步骤生成的。
    release = _load(release_drill_result)
    live = _load(live_smoke_result)
    # ❓ 检查 1：发布演练是否成功
    # 💡 release.get("success") is True 确保了：
    #    - 键 "success" 存在
    #    - 值确实是 True（而不是 1、"true" 等其他真值）
    checks.append(_check("release_drill_success", release.get("success") is True, {"path": str(release_drill_result)}))
    # ❓ 检查 2：烟雾测试是否成功且 HTTP 状态码是 200
    # 💡 同时验证两件事：success 为 True 且 provider_status 为 200。
    #    这确保 API 不仅"返回了成功"（可能只是不抛异常），而且确实是 HTTP 200 响应。
    checks.append(_check("live_smoke_success", live.get("success") is True and live.get("provider_status") == 200, {"path": str(live_smoke_result), "provider_status": live.get("provider_status")}))
    # ❓ 检查 3：烟雾测试的脱敏检查是否通过
    # 💡 从 live 结果中提取 "leak_checks"（泄露检查结果），
    #    首先确保 leaks 确实是一个字典（isinstance check），
    #    然后检查 bool(leaks)（非空）和 all(leaks.values())（所有检查都通过）。
    #    leaks.values() 的每项是 True（未泄露）或 False（泄露了）。
    leaks = live.get("leak_checks") if isinstance(live.get("leak_checks"), dict) else {}
    checks.append(_check("live_smoke_redacted", bool(leaks) and all(leaks.values()), {"leak_checks": leaks}))
    # ❓ 检查 4：必需文档是否存在
    # 💡 遍历 REQUIRED_DOCS，检查每个文件在项目根目录下是否存在。
    #    (ROOT / path).exists() 是 pathlib 的文件存在性检查。
    #    将所有不存在的文件路径收集到 missing_docs 列表中。
    missing_docs = [path for path in REQUIRED_DOCS if not (ROOT / path).exists()]
    # ❓ 如果 missing_docs 为空（所有文档都存在），检查通过。
    # 💡 not missing_docs 在列表为空时为 True（所有文档都存在）。
    checks.append(_check("public_docs_present", not missing_docs, {"missing": missing_docs, "required": list(REQUIRED_DOCS)}))
    # ❓ 检查 5：发布清单中的 SHA-256（如果提供了清单文件）
    # 💡 manifest 参数是可选的（默认为 None）。只有提供了才进行此检查。
    if manifest is not None:
        # ❓ 加载清单文件
        manifest_data = _load(manifest)
        # ❓ 获取 artifacts 字段
        artifacts = manifest_data.get("artifacts")
        # ❓ 复杂的条件判断在检查什么？
        # 💡 sha_ok 为 True 需要满足所有条件：
        #    1. artifacts 是列表（isinstance(item, list)）
        #    2. artifacts 非空（bool(artifacts)）
        #    3. 每个构件都是字典
        #    4. 每个构件的 sha256 字段是长度为 64 的字符串（SHA-256 十六进制表示）
        sha_ok = isinstance(artifacts, list) and bool(artifacts) and all(isinstance(item, dict) and len(str(item.get("sha256", ""))) == 64 for item in artifacts)
        checks.append(_check("release_manifest_sha256", sha_ok, {"path": str(manifest), "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0}))
    # ❓ 返回完整的审计报告
    # 💡 - schema_version: 数据格式版本号 "1.0"
    #    - created_at: 执行时间戳（UTC）
    #    - success: 所有检查是否都通过（all() 检查 checks 列表中每个 check["ok"]）
    #    - checks: 各项检查的详细结果列表
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),
        "checks": checks,
    }


# ❓ main() 函数做什么？
# 💡 命令行入口点——解析参数、运行审计、输出结果、返回退出码。
def main() -> None:
    # ❓ 四个命令行参数：
    # 💡 --release-drill-result (必需): 发布演练输出的 JSON 文件
    #    --live-smoke-result (必需): 烟雾测试输出的 JSON 文件
    #    --manifest (可选): 发布清单文件路径
    #    --out (可选，有默认值): 审计报告输出路径，默认 "release-gate-audit.json"
    parser = argparse.ArgumentParser(description="Audit release drill, live smoke, docs, and artifact manifest evidence")
    parser.add_argument("--release-drill-result", type=Path, required=True)
    parser.add_argument("--live-smoke-result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out", type=Path, default=Path("release-gate-audit.json"))
    args = parser.parse_args()
    # ❓ 调用核心审计逻辑
    # 💡 关注点分离——audit() 处理业务逻辑，main() 处理 I/O。
    result = audit(args.release_drill_result, args.live_smoke_result, args.manifest)
    # ❓ 序列化审计结果
    # 💡 ensure_ascii=False：允许非 ASCII 字符
    #    indent=2：缩进 2 空格
    #    + "\n"：末尾换行符
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # ❓ 写入输出文件
    # 💡 注意：这里 --out 有默认值，所以 args.out 始终非 None，不需要 if 检查。
    #    write_text 直接把字符串写入文件，encoding="utf-8" 确保编码正确。
    args.out.write_text(text, encoding="utf-8")
    # ❓ 同时打印到控制台
    # 💡 end="" 因为 text 末尾已有 \n
    print(text, end="")
    # ❓ 退出码
    # 💡 0 = 所有审计检查通过（符合发布门禁条件）
    #    1 = 至少一项检查未通过（发布被阻止）
    raise SystemExit(0 if result["success"] else 1)


# ❓ if __name__ == "__main__": 的作用？
# 💡 Python 惯例：直接运行脚本时执行 main()，被 import 时不自动执行。
if __name__ == "__main__":
    main()
