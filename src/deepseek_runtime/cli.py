"""
CLI 层（Command Line Interface）—— 怎么在终端中使用 Runtime？

❓ 问：普通用户怎么使用 DeepSeek Runtime？
💡 答：通过两个 CLI 命令——
   1. deepseek-runtime doctor --json
      检查本地环境是否正常（相当于"体检"）
   2. deepseek-runtime run "你的问题"
      运行一个 AI Agent 任务

❓ 问：为什么用 CLI 而不是直接写 Python 代码？
💡 答：CLI 让不熟悉 Python 的用户也能使用 Runtime。
   你只需要在终端里敲一行命令，不需要写 import、不需要处理异常。
"""

from __future__ import annotations

import argparse  # 命令行参数解析器
import json
import sys
from pathlib import Path

from .client import DeepSeekClient, RuntimeSettings
from .diagnostics import build_diagnostics
from .runtime import DeepSeekRuntime, WorkspaceTools


def _doctor(argv: list[str]) -> int:
    """
    "体检"命令：生成本地诊断报告。

    用法：deepseek-runtime doctor --json [--out path] [--evidence path] [--workspace path]
    
    输出包含：Python 版本、工作区状态、Session 存储可写性、API Key 配置等。
    参考 llm-harness-agent 论文 A1 中关于 Harness 诊断能力的要求。
    """
    parser = argparse.ArgumentParser(
        prog="deepseek-runtime doctor",
        description="生成脱敏后的本地诊断报告",
    )
    parser.add_argument("--json", action="store_true", dest="json_output", help="以 JSON 格式输出诊断信息")
    parser.add_argument("--out", type=Path, help="把诊断结果写入指定文件")
    parser.add_argument("--evidence", type=Path, help="对指定 JSON/JSONL 文件中的路由/缓存/用量/成本证据做摘要")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    if not args.json_output:
        parser.error("当前 doctor 只支持 --json 输出模式")

    # 生成诊断报告
    bundle = build_diagnostics(args.workspace, args.evidence)
    text = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"

    # 如果指定了输出文件，写入文件
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")

    # 同时输出到终端
    print(text, end="")
    return 0 if bundle["ok"] else 1


def _run(argv: list[str]) -> int:
    """
    "运行"命令：执行一个 AI Agent 任务。

    用法：deepseek-runtime run "你的问题" [--workspace path] [--no-tools] [--include-content]
    
    --include-content 参数会把 prompt 和 response 原文包含在输出中，
    这只应该在本地可信调试时使用，不适用于发布或日志记录。
    
    参考 llm-harness-agent 论文 B1: ReAct 中的推理-行动循环。
    """
    parser = argparse.ArgumentParser(
        prog="deepseek-runtime run",
        description="通过 DeepSeek 运行时执行一个 prompt",
    )
    parser.add_argument("prompt")  # 用户的问题
    parser.add_argument("--workspace", type=Path, default=Path.cwd())  # 工作区
    parser.add_argument("--no-tools", action="store_true")  # 不允许使用工具
    parser.add_argument("--include-content", action="store_true", help="包含 prompt 和 response 原文（不安全，不适合日志）")
    args = parser.parse_args(argv)

    # 默认启用工作区工具（read_file, search）
    tools = {} if args.no_tools else WorkspaceTools(args.workspace).catalog()

    # 创建运行时并执行
    runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
    result = runtime.run(
        [{"role": "user", "content": args.prompt}],
        workspace=args.workspace,
        tools=tools,
    )

    # 输出结果（默认安全模式，不包含原文）
    print(json.dumps(result.to_dict(include_content=args.include_content), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> None:
    """
    主入口：解析命令行参数，分发到对应的子命令。

    支持两个子命令：
    - doctor：诊断
    - run：运行
    """
    args_list = list(sys.argv[1:] if argv is None else argv)

    if args_list and args_list[0] == "doctor":
        raise SystemExit(_doctor(args_list[1:]))
    if args_list and args_list[0] == "run":
        raise SystemExit(_run(args_list[1:]))

    # 没有合法子命令时显示帮助信息
    parser = argparse.ArgumentParser(description="DeepSeek-native Python runtime kernel")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("doctor", help="生成诊断报告")
    subcommands.add_parser("run", help="执行 prompt")
    parser.print_help()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
