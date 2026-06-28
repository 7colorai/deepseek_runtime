# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 shebang（释伴行），告诉操作系统用 python3 解释器来运行这个脚本。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是做什么的？
# 💡 让类型注解延迟求值，提升运行性能并支持前向引用。
from __future__ import annotations

# ❓ 这里导入的标准库各有什么用？
# 💡 - argparse：解析命令行参数（--out, --manifest）
#    - fnmatch：文件名通配符匹配（类似 .gitignore 的模式匹配）
#    - hashlib：计算 SHA-256 哈希值（用于构建清单）
#    - json：序列化发布清单到 JSON 格式
#    - tarfile：创建 tar.gz 压缩归档包
#    - datetime/timezone：生成 UTC 时间戳
#    - pathlib.Path：面向对象路径操作
#    - typing.Any：动态类型注解
import argparse
import fnmatch
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ❓ ROOT 是做什么的？
# 💡 项目根目录——当前脚本的父目录的父目录。
#    所有文件的相对路径都基于此。
ROOT = Path(__file__).resolve().parents[1]
# ❓ VERSION 常量是做什么的？
# 💡 当前发布版本号 "0.1.1a1"（语义化版本号格式：主版本.次版本.补丁-预发布标识）。
#    "a1" 表示 alpha 1 版本，是早期测试版。
VERSION = "0.1.1a1"
# ❓ ARCHIVE_BASENAME 是怎么生成的？
# 💡 使用 f-string（格式化字符串），把 VERSION 嵌入到归档包的基础文件名中。
#    例如：VERSION = "0.1.1a1" → "deepseek-runtime-0.1.1a1-source"
#    这样每个版本的归档包有唯一的文件名。
ARCHIVE_BASENAME = f"deepseek-runtime-{VERSION}-source"

# ❓ EXCLUDE_GLOBS 是什么？
# 💡 一个元组，包含通配符模式（glob patterns），指定哪些文件和目录应该
#    从发布归档包中排除。这类似于 .gitignore 的机制。
#    排除的内容：
#    - .git/*：Git 版本历史目录
#    - .venv/*：Python 虚拟环境
#    - __pycache__/*：Python 字节码缓存
#    - *.pyc：编译后的 Python 文件
#    - .pytest_cache/*：pytest 测试缓存
#    - dist/*：构建输出目录（避免重复归档）
#    - release-drill.json：上次发布的演练结果
#    - release-gate-audit.json：上次发布的审计报告
#    - live-smoke.json：上次烟雾测试的结果
#    参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于构件管理的最佳实践。
EXCLUDE_GLOBS = (
    ".git/*",
    ".venv/*",
    "__pycache__/*",
    "*.pyc",
    ".pytest_cache/*",
    "dist/*",
    "release-drill.json",
    "release-gate-audit.json",
    "live-smoke.json",
)


# ❓ _excluded 函数是做什么的？
# 💡 检查一个相对文件路径是否与任何排除模式匹配。
#    如果匹配任意一个模式，返回 True（应排除），否则返回 False（应包含）。
# ❓ fnmatch.fnmatch 是怎么工作的？
# 💡 fnmatch.fnmatch(relative, pattern) 把 relative 路径与 pattern 模式进行通配符匹配。
#    例如：fnmatch("src/__pycache__/cache.py", "__pycache__/*") → False
#         因为 "src/__pycache__/cache.py" 不匹配 "__pycache__/*"。
#         但 fnmatch(".git/HEAD", ".git/*") → True。
#    注意：这需要使用相对路径（相对于项目根目录）来判断。
def _excluded(relative: str) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in EXCLUDE_GLOBS)


# ❓ _sha256 函数是做什么的？
# 💡 计算一个文件的 SHA-256 哈希值（加密哈希/指纹）。
#    哈希值是一个 64 字符的十六进制字符串，可以唯一标识文件内容。
#    任何文件内容的微小变化都会导致完全不同的哈希值。
#    发布清单中会记录每个构件的 SHA-256，供用户验证下载文件的完整性。
# ❓ 为什么要分块读取（chunk）而不是一次性读完整个文件？
# 💡 大文件（比如几百 MB）如果一次性读入内存，可能导致内存不足。
#    这里以 1MB（1024*1024 字节）为单位分块读取，逐块更新哈希。
#    无论文件多大，内存占用始终可控。
def _sha256(path: Path) -> str:
    # ❓ hashlib.sha256() 创建了什么？
    # 💡 创建一个 SHA-256 哈希计算器对象。它有一个内部状态，
    #    update() 方法向其中添加数据，hexdigest() 输出最终的哈希字符串。
    digest = hashlib.sha256()
    # ❓ with path.open("rb") as handle 是做什么的？
    # 💡 以二进制只读模式（"rb"）打开文件。
    #    with 语句确保文件使用完毕后自动关闭。
    with path.open("rb") as handle:
        # ❓ iter(lambda: handle.read(1024 * 1024), b"") 是什么技巧？
        # 💡 一个巧妙的"迭代器技巧"：
        #    - handle.read(1024 * 1024) 每次读取最多 1MB 数据
        #    - lambda: handle.read(...) 把这个读操作包装成一个可调用的函数
        #    - iter(callable, sentinel) 反复调用 callable，直到它返回 sentinel（b""）
        #    - 当文件读取完毕，read() 返回空字节串 b""，迭代终止
        #    这是 Python 中"循环读取大文件"的惯用写法。
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            # ❓ digest.update(chunk) 是做什么的？
            # 💡 把当前块的数据"喂"给哈希计算器。
            #    逐块 update，最终 hexdigest() 输出的哈希值等价于一次性读取整个文件。
            digest.update(chunk)
    # ❓ hexdigest() 返回什么？
    # 💡 返回 SHA-256 哈希的十六进制表示，一个 64 字符的字符串。
    #    例如："e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    return digest.hexdigest()


# ❓ _iter_files 函数是做什么的？
# 💡 遍历项目根目录下的所有文件，排除匹配 EXCLUDE_GLOBS 模式的文件，
#    返回一个经过排序的文件路径列表。
#    这个列表会被打包进发布归档包，保证文件顺序是确定性的。
def _iter_files() -> list[Path]:
    # ❓ 为什么先创建一个空列表？
    # 💡 用显式的 for 循环收集文件，而不是用列表推导式，因为逻辑中有 continue 分支。
    files: list[Path] = []
    # ❓ ROOT.rglob("*") 是做什么的？
    # 💡 rglob("*") 递归遍历 ROOT 目录下的所有条目（文件和目录）。
    #    "rglob" 中的 "r" 表示 recursive（递归）。
    for path in ROOT.rglob("*"):
        # ❓ 跳过目录，只处理文件
        # 💡 path.is_file() 检查路径是否是一个普通文件（而非目录）。
        #    目录不需要单独打包——tar 归档会自动包含所需的目录结构。
        if not path.is_file():
            continue
        # ❓ 计算相对路径
        # 💡 path.relative_to(ROOT) 把绝对路径转为相对于项目根目录的路径。
        #    .as_posix() 把路径中的反斜杠（Windows）统一为正斜杠（POSIX）。
        #    例如：/project/src/main.py → "src/main.py"
        relative = path.relative_to(ROOT).as_posix()
        # ❓ 匹配排除模式
        # 💡 如果文件路径匹配任何排除模式，就跳过它。
        if _excluded(relative):
            continue
        files.append(path)
    # ❓ 为什么要排序？
    # 💡 sorted() 确保文件列表按路径字典序排列。
    #    排序键（key）是相对于 ROOT 的路径。
    #    这样做的好处是：每次构建归档包时，文件在归档中的顺序完全一致，
    #    从而保证归档包的 SHA-256 哈希值可复现。
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


# ❓ build_release_artifact 是核心函数吗？
# 💡 是的。它执行构建发布归档包的整体流程：
#    1. 确保输出目录存在
#    2. 创建 tar.gz 压缩归档
#    3. 计算归档文件的 SHA-256
#    4. 生成发布清单 JSON
#    5. 写入清单文件
#    6. 返回完整的发布数据字典
# ❓ out 和 manifest 参数是什么？
# 💡 - out: 输出目录路径（归档包会放在这个目录中）
#    - manifest: 清单文件的输出路径（.json 文件）
def build_release_artifact(out: Path, manifest: Path) -> dict[str, Any]:
    # ❓ 确保输出目录存在
    # 💡 mkdir(parents=True) 创建多级目录（类似 mkdir -p），
    #    exist_ok=True 表示目录已存在时不报错。
    out.mkdir(parents=True, exist_ok=True)
    # ❓ 构建归档文件完整路径
    # 💡 out / f"{ARCHIVE_BASENAME}.tar.gz" 拼接出完整路径，如：
    #    "dist/deepseek-runtime-0.1.1a1-source.tar.gz"
    archive = out / f"{ARCHIVE_BASENAME}.tar.gz"
    # ❓ 获取要打包的文件列表
    files = _iter_files()
    # ❓ 创建 tar.gz 归档
    # 💡 tarfile.open(archive, "w:gz") 以 GZip 压缩写入模式打开 tar 文件。
    #    "w:gz" 表示写入（write）+ GZip 压缩（gz）。
    with tarfile.open(archive, "w:gz") as handle:
        # ❓ 遍历所有需要打包的文件
        for path in files:
            # ❓ arcname 是什么？
            # 💡 文件在归档中的路径名。例如：
            #    真实路径：/project/src/main.py
            #    arcname："deepseek-runtime-0.1.1a1-source/src/main.py"
            #    这样当用户解压时，所有文件都在一个以版本号命名的顶级目录下。
            arcname = f"{ARCHIVE_BASENAME}/{path.relative_to(ROOT).as_posix()}"
            # ❓ handle.add(path, arcname=arcname, recursive=False)
            # 💡 把文件添加到归档中。
            #    path：源文件的真实路径
            #    arcname：归档中的路径名
            #    recursive=False：不递归添加（因为我们已经自己遍历了所有文件）
            handle.add(path, arcname=arcname, recursive=False)
    # ❓ data 字典包含什么？
    # 💡 这就是发布清单（manifest）的内容：
    #    - schema_version: 数据格式版本号
    #    - created_at: 构建时间戳（UTC）
    #    - success: 构建成功标志
    #    - version: 发布版本号
    #    - artifacts: 构件列表（每个构件包含路径、文件名、SHA-256、文件大小）
    #    - included_files: 所有被包含的文件路径列表（从项目根目录开始的相对路径）
    # 参考 llm-harness-agent 论文 A1 中关于构件签名和完整性验证的讨论。
    data = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": True,
        "version": VERSION,
        "artifacts": [
            {
                "path": str(archive),
                "filename": archive.name,
                "sha256": _sha256(archive),
                "bytes": archive.stat().st_size,
            }
        ],
        "included_files": [path.relative_to(ROOT).as_posix() for path in files],
    }
    # ❓ 写入清单文件
    # 💡 先确保清单文件的父目录存在，然后写入格式化的 JSON 内容。
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # ❓ 返回构建数据
    # 💡 调用方可以继续使用这个字典（例如打印到控制台或进一步处理）。
    return data


# ❓ main() 函数做什么？
# 💡 命令行入口点——解析参数、构建发布归档、输出结果。
def main() -> None:
    # ❓ 两个可选参数：
    # 💡 --out：输出目录，默认为 "dist"
    #    --manifest：清单文件路径，默认为 "dist/release-manifest.json"
    parser = argparse.ArgumentParser(description="Build a local source release artifact and sha256 manifest")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--manifest", type=Path, default=Path("dist/release-manifest.json"))
    args = parser.parse_args()
    # ❓ 调用核心构建逻辑
    # 💡 关注点分离——build_release_artifact 处理业务逻辑，main 仅做参数传递和输出。
    result = build_release_artifact(args.out, args.manifest)
    # ❓ 打印构建结果（JSON 格式）
    # 💡 使用 print 把结果字典以 JSON 格式输出到控制台。
    #    注意：这个输出不写入文件（清单文件已经在 build_release_artifact 中写过了）。
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # ❓ 注意：这个 main() 没有设置 SystemExit 退出码
    # 💡 与前面的脚本不同，这个构建脚本即使失败也不会主动返回非零退出码。
    #    只要 build_release_artifact 没有抛出异常，它总是返回 success=True。
    #    如果发生异常，由 Python 默认的异常处理机制返回非零退出码。


# ❓ if __name__ == "__main__": 的作用？
# 💡 Python 惯例：直接运行脚本时执行 main()，被 import 时不自动执行。
if __name__ == "__main__":
    main()
