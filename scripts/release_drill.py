#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _run(command: list[str], *, env: dict[str, str], timeout: int = 180) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout, check=False)
    stdout = completed.stdout.encode("utf-8")
    stderr = completed.stderr.encode("utf-8")
    return {
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }


def run_release_drill(skip_tests: bool = False) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    commands = []
    if not skip_tests:
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    commands.extend(
        [
            [sys.executable, "-m", "deepseek_runtime.cli", "doctor", "--json"],
            [sys.executable, "scripts/release_safety_drill.py"],
            [sys.executable, "scripts/release_observability_drill.py"],
        ]
    )
    checks = [_run(command, env=env) for command in commands]
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),
        "checks": checks,
        "warning": "Release drill records command fingerprints and byte counts, not command stdout bodies.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local release checks without writing prompt or response text")
    parser.add_argument("--out", type=Path, default=Path("release-drill.json"))
    parser.add_argument("--skip-tests", action="store_true", help="skip unittest discovery; intended only for unit tests of this script")
    args = parser.parse_args()
    result = run_release_drill(skip_tests=args.skip_tests)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
