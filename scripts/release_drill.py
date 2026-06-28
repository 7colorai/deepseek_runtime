# ❓ 第一行 #!/usr/bin/env python3 是做什么的？
# 💡 这叫 shebang（释伴行），告诉 Unix/Linux 操作系统：
#    "用环境中的 python3 解释器来运行这个脚本"。
#    在终端里直接执行 ./release_drill.py 时，系统就靠这行找到 Python。
#!/usr/bin/env python3
# ❓ from __future__ import annotations 是什么意思？
# 💡 这是一个"未来导入"指令，让 Python 把类型注解（type annotations）
#    当作字符串延迟求值，而不是在运行时计算。
#    好处是：普通代码跑得更快，而且支持前向引用（在类型还没定义时就引用它）。
#    这是 Python 3.7+ 的惯例，也是现代 Python 项目常见的写法。
from __future__ import annotations

# ❓ 为什么这里导入这么多标准库模块？
# 💡 每个模块负责一件具体的事：
#    - argparse：解析命令行参数（比如 --out、--skip-tests）
#    - hashlib：计算 SHA-256 哈希值，用来"指纹"命令输出（而不是记录敏感内容）
#    - json：把结果序列化成 JSON 格式输出
#    - os：访问操作系统环境变量（PYTHONPATH）
#    - subprocess：启动子进程来跑其他命令（单元测试、doctor 等）
#    - sys：获取当前 Python 解释器路径（sys.executable）
# 整个发布脚本的理念是：记录指纹和字节数，不记录原始文本，确保安全性。
# 参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中关于安全日志记录的建议。
import argparse
import hashlib
import json
import os
import subprocess
import sys
# ❓ 为什么导入 datetime 和 timezone？
# 💡 用来生成 ISO 8601 格式的时间戳（UTC 时区），标记每次检查是什么时候跑的。
#    这样审计回溯时可以精确知道每项检查的执行时间。
from datetime import datetime, timezone
# ❓ Path 比普通字符串路径好在哪？
# 💡 pathlib.Path 是 Python 3 推荐的面向对象路径操作方式。
#    它比 os.path.join() 更直观：path / "subdir" 就能拼接路径，
#    而且跨平台（Windows 和 macOS/Linux 都支持）。
from pathlib import Path
# ❓ typing.Any 又是什么？
# 💡 Any 是一个类型注解（type hint），表示"可以是任何类型"。
#    它告诉阅读代码的人和静态类型检查工具：
#    "这个变量的类型是动态的，不用严格检查它"。
#    在发布脚本这类工具代码中，返回混合类型的字典是很常见的用法。
from typing import Any

# ❓ ROOT 和 SRC 是怎么确定的？
# 💡 Path(__file__) 获取当前脚本的文件路径。
#    .resolve() 把符号链接（软链接）解析成真实路径。
#    .parents[1] 表示"当前文件的父目录的父目录"——即项目根目录。
#    例如：如果脚本在 /project/scripts/release_drill.py，
#    ROOT = /project，SRC = /project/src。
#    这样写的好处是：不管脚本从哪里被调用，路径始终相对于脚本自身的位置。
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


# ❓ 为什么 _run 函数的名字前面有下划线？
# 💡 在 Python 中，下划线开头的函数是"内部使用"的约定。
#    它告诉其他开发者："这是一个私有辅助函数，不要从模块外部直接调用它。"
#    或者说："如果你要用它，请通过 run_release_drill() 间接使用。"
# ❓ 参数 list[str] 是什么意思？
# 💡 这是类型注解，表示 command 参数应该是一个字符串列表。
#    例如：["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
# ❓ env: dict[str, str] 表示什么？
# 💡 env 是一个字典（键值对），键和值都是字符串，用来设置子进程的环境变量。
# ❓ -> dict[str, Any] 表示函数返回什么？
# 💡 箭头后面是返回类型注解——这个函数返回一个字典，键是字符串，值可以是任意类型。
def _run(command: list[str], *, env: dict[str, str], timeout: int = 180) -> dict[str, Any]:
    # ❓ subprocess.run 在做什么？
    # 💡 它在启动一个子进程来运行 command 列表里指定的命令。
    #    cwd=ROOT：在工作目录 ROOT（项目根目录）下运行这个命令。
    #    env=env：使用传入的环境变量字典。
    #    text=True：让输出以文本（而非字节）形式返回。
    #    capture_output=True：捕获 stdout（标准输出）和 stderr（标准错误），
    #      不打印到终端。
    #    timeout=timeout：超时时间，默认 180 秒（3 分钟），防止命令卡死。
    #    check=False：即使命令返回非零退出码，也不抛异常——让调用方自行处理错误。
    # 参考 llm-harness-agent 论文 C3 (OpenHands) 中关于沙箱化执行和超时管理的讨论。
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    # ❓ 为什么要对 stdout/stderr 做 .encode("utf-8")？
    # 💡 因为 hashlib.sha256() 需要字节数据（bytes）而不是字符串（str）。
    #    我们先把文本编码成 UTF-8 字节序列，然后计算 SHA-256 哈希。
    #    这样做的目的是：记录命令输出的"指纹"，而不是记录命令输出的原文。
    #    看——我们不保存返回的文本内容，只保存它的哈希值和长度。
    #    这是一种安全/隐私保护设计（脱敏记录）。
    stdout = completed.stdout.encode("utf-8")
    stderr = completed.stderr.encode("utf-8")
    # ❓ 返回的字典里每项都是什么？
    # 💡 返回一个记录命令执行结果的摘要信息：
    #    - "command": 执行的命令本身
    #    - "returncode": 退出码（0=成功，非0=出错）
    #    - "ok": 布尔值，退出码是否为 0
    #    - "stdout_sha256": 标准输出的 SHA-256 哈希值（脱敏指纹）
    #    - "stderr_sha256": 标准错误的 SHA-256 哈希值（脱敏指纹）
    #    - "stdout_bytes": 标准输出的字节数
    #    - "stderr_bytes": 标准错误的字节数
    return {
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }


# ❓ run_release_drill 是做什么的？
# 💡 这是整个发布演练的主函数。它按顺序执行一组检查命令，
#    收集每项检查的结果，最后汇总成一个报告字典。
# ❓ skip_tests: bool = False 为什么有默认值？
# 💡 默认情况下会跑单元测试。只有测试本脚本自己时才跳过单元测试（--skip-tests）。
#    这是一种灵活设计：正常发布时必须跑测试，开发调试时可以跳过以节省时间。
def run_release_drill(skip_tests: bool = False) -> dict[str, Any]:
    # ❓ dict(os.environ) 是做什么的？
    # 💡 os.environ 是当前进程的全部环境变量（一个类似字典的对象）。
    #    dict(os.environ) 复制一份到 env 变量中，这样我们修改 env 不会影响真实的系统环境。
    env = dict(os.environ)
    # ❓ 下面这行复杂赋值在做什么？
    # 💡 把 SRC（项目 src 目录）添加到 PYTHONPATH 环境变量的最前面。
    #    PYTHONPATH 告诉 Python 解释器去哪里找模块。
    #    如果已经有 PYTHONPATH 了，就用 os.pathsep（冒号 :）拼接；
    #    如果没有，就直接设成 SRC 的路径。
    #    这样脚本就能 import deepseek_runtime 包里的模块了。
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    # ❓ commands 列表是做什么的？
    # 💡 它是一个命令列表，每个命令后续会被 _run() 执行。初始为空，逐步添加。
    commands = []
    # ❓ 为什么用 if not skip_tests 来判断？
    # 💡 如果 skip_tests 是 False（默认值），说明要跑测试，就添加 unittest 发现测试的命令。
    #    如果 skip_tests 是 True，就跳过测试——这是给脚本开发者自己调试时用的选项。
    if not skip_tests:
        # ❓ sys.executable 是什么？
        # 💡 sys.executable 是当前 Python 解释器的完整路径。
        #    例如 "/usr/local/bin/python3"。
        #    用 sys.executable 而不是直接写 "python3" 是为了确保使用正确的解释器
        #    （比如在虚拟环境中时）。
        # ❓ -m unittest discover -s tests -v 是什么？
        # 💡 -m unittest：运行 Python 自带的单元测试模块。
        #    discover：自动发现测试用例。
        #    -s tests：在 tests 目录下搜索测试文件。
        #    -v：详细模式（verbose），输出每个测试的名称和结果。
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    # ❓ commands.extend 是做什么的？
    # 💡 extend 把一个列表的元素逐个添加到另一个列表末尾。
    #    这里添加三个命令：
    #    1. deepseek_runtime 的 doctor 命令（检查运行时健康状态，输出 JSON）
    #    2. 安全演练脚本
    #    3. 可观测性演练脚本
    #    这三个命令与单元测试一起，构成了发布前的完整检查集。
    commands.extend(
        [
            [sys.executable, "-m", "deepseek_runtime.cli", "doctor", "--json"],
            [sys.executable, "scripts/release_safety_drill.py"],
            [sys.executable, "scripts/release_observability_drill.py"],
        ]
    )
    # ❓ 这行列表推导式在做什么？
    # 💡 [_run(command, env=env) for command in commands]
    #    遍历 commands 列表里每个命令，对每个命令调用 _run() 函数，
    #    把结果收集到一个新的列表 checks 中。
    #    这是一行 Python 的"列表推导式"（list comprehension）——优雅、简洁。
    checks = [_run(command, env=env) for command in commands]
    # ❓ 返回的字典结构是什么？
    # 💡 返回一个完整的发布演练报告：
    #    - schema_version: 数据结构版本号，"1.0"
    #    - created_at: 当前 UTC 时间的 ISO 8601 格式字符串
    #    - success: 所有检查是否都通过了（all() 检查列表中每个 check["ok"] 是否为 True）
    #    - checks: 各项检查的详细结果列表
    #    - warning: 一条警告说明——"发布演练记录命令指纹和字节数，不记录命令输出原文"
    # 参考 llm-harness-agent 论文 A1 中关于发布门禁（release gates）的设计讨论。
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),
        "checks": checks,
        "warning": "Release drill records command fingerprints and byte counts, not command stdout bodies.",
    }


# ❓ main() 函数是做什么的？
# 💡 main() 是命令行入口点。当你从终端运行这个脚本时，main() 负责：
#    1. 解析命令行参数
#    2. 调用核心逻辑 run_release_drill()
#    3. 把结果输出到文件和控制台
#    4. 根据成功/失败返回合适的退出码
def main() -> None:
    # ❓ ArgumentParser 是怎么工作的？
    # 💡 argparse 创建一个命令行参数解析器。
    #    description 是帮助信息中显示的文字。
    #    然后通过 add_argument() 定义脚本支持的参数。
    #    最后 parse_args() 从命令行参数（sys.argv）中解析出参数对象。
    parser = argparse.ArgumentParser(description="Run local release checks without writing prompt or response text")
    # ❓ --out 参数是用来做什么的？
    # 💡 指定结果输出文件的路径。默认值是 Path("release-drill.json")。
    #    type=Path 表示 argparse 会自动把字符串转成 pathlib.Path 对象。
    #    用户可以用 --out /path/to/output.json 指定不同的输出位置。
    parser.add_argument("--out", type=Path, default=Path("release-drill.json"))
    # ❓ --skip-tests 是怎么工作的？
    # 💡 action="store_true" 表示：如果命令中出现了 --skip-tests，就把这个参数设为 True。
    #    如果没出现，默认为 False。help 是为 --help 命令提供的说明文字。
    parser.add_argument("--skip-tests", action="store_true", help="skip unittest discovery; intended only for unit tests of this script")
    # ❓ parse_args() 返回什么？
    # 💡 返回一个 Namespace 对象，args.out 和 args.skip_tests 分别是上面两个参数的值。
    args = parser.parse_args()
    # ❓ 这里为什么调用 run_release_drill 而不是直接写逻辑？
    # 💡 这是一种关注点分离（separation of concerns）设计：
    #    run_release_drill() 负责业务逻辑（执行检查），
    #    main() 只负责"管线"工作（解析参数、输出结果）。
    #    这样 run_release_drill() 也可以在单元测试中被直接调用，不需要经过命令行。
    result = run_release_drill(skip_tests=args.skip_tests)
    # ❓ json.dumps 的三个参数分别做什么？
    # 💡 result：要序列化的 Python 字典。
    #    ensure_ascii=False：允许输出非 ASCII 字符（比如中文）。
    #    indent=2：缩进 2 个空格，让 JSON 更可读。
    #    + "\n"：在文件末尾加一个换行符，符合 UNIX 文本文件规范。
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    # ❓ write_text 是做什么的？
    # 💡 pathlib.Path 的 write_text() 方法：把字符串写入文件。
    #    encoding="utf-8"：用 UTF-8 编码写入，支持所有 Unicode 字符。
    args.out.write_text(text, encoding="utf-8")
    # ❓ print(text, end="") 为什么用 end=""？
    # 💡 因为 text 末尾已经有一个换行符 \n 了，end="" 防止 print 再加一个多余的换行。
    #    这样打印出来的内容和文件内容完全一致。
    print(text, end="")
    # ❓ raise SystemExit(0 if ... else 1) 是什么？
    # 💡 SystemExit 是一个特殊的异常，Python 解释器捕获它后会退出进程。
    #    退出码 0 表示成功，非零（这里是 1）表示失败。
    #    这很重要——CI/CD 系统（比如 GitHub Actions、Jenkins）就靠退出码判断脚本是否成功。
    #    如果所有检查都通过（result["success"] 为 True），退出码是 0；否则是 1。
    raise SystemExit(0 if result["success"] else 1)


# ❓ if __name__ == "__main__": 是用来做什么的？
# 💡 这是一个 Python 惯例。__name__ 是 Python 内部变量：
#    - 当脚本被直接运行时（python3 release_drill.py），__name__ 被设为 "__main__"
#    - 当脚本被导入时（import release_drill），__name__ 被设为模块名 "release_drill"
#    这个条件判断确保：只有直接运行脚本时才执行 main()，
#    导入模块时不会自动执行——这样其他脚本可以安全地 import 使用其中的函数。
if __name__ == "__main__":
    main()
