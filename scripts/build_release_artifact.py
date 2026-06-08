#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1a1"
ARCHIVE_BASENAME = f"deepseek-runtime-{VERSION}-source"

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


def _excluded(relative: str) -> bool:
    return any(fnmatch.fnmatch(relative, pattern) for pattern in EXCLUDE_GLOBS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if _excluded(relative):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def build_release_artifact(out: Path, manifest: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"{ARCHIVE_BASENAME}.tar.gz"
    files = _iter_files()
    with tarfile.open(archive, "w:gz") as handle:
        for path in files:
            arcname = f"{ARCHIVE_BASENAME}/{path.relative_to(ROOT).as_posix()}"
            handle.add(path, arcname=arcname, recursive=False)
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
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local source release artifact and sha256 manifest")
    parser.add_argument("--out", type=Path, default=Path("dist"))
    parser.add_argument("--manifest", type=Path, default=Path("dist/release-manifest.json"))
    args = parser.parse_args()
    result = build_release_artifact(args.out, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
