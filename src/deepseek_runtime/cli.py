from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import DeepSeekClient, RuntimeSettings
from .diagnostics import build_diagnostics
from .runtime import DeepSeekRuntime, WorkspaceTools


def _doctor(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="deepseek-runtime doctor", description="Generate a redacted local diagnostics bundle")
    parser.add_argument("--json", action="store_true", dest="json_output", help="emit the stable JSON diagnostics schema")
    parser.add_argument("--out", type=Path, help="write the diagnostics JSON to this explicit path")
    parser.add_argument("--evidence", type=Path, help="summarize route/cache/usage/cost evidence from this JSON or JSONL file")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    if not args.json_output:
        parser.error("doctor currently supports only --json")
    bundle = build_diagnostics(args.workspace, args.evidence)
    text = json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if bundle["ok"] else 1


def _run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="deepseek-runtime run", description="Run a prompt through the DeepSeek runtime")
    parser.add_argument("prompt")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--no-tools", action="store_true")
    parser.add_argument("--include-content", action="store_true", help="include prompt and response text in JSON output; unsafe for logs")
    args = parser.parse_args(argv)
    tools = {} if args.no_tools else WorkspaceTools(args.workspace).catalog()
    runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
    result = runtime.run([{"role": "user", "content": args.prompt}], workspace=args.workspace, tools=tools)
    print(json.dumps(result.to_dict(include_content=args.include_content), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "doctor":
        raise SystemExit(_doctor(args_list[1:]))
    if args_list and args_list[0] == "run":
        raise SystemExit(_run(args_list[1:]))
    parser = argparse.ArgumentParser(description="DeepSeek-native Python runtime kernel")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("doctor", help="generate diagnostics")
    subcommands.add_parser("run", help="run a prompt")
    parser.print_help()
    raise SystemExit(0)


if __name__ == "__main__":
    main()
