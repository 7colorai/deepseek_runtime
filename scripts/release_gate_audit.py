#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _check(name: str, ok: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "ok": ok, "evidence": evidence}


def audit(release_drill_result: Path, live_smoke_result: Path, manifest: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    release = _load(release_drill_result)
    live = _load(live_smoke_result)
    checks.append(_check("release_drill_success", release.get("success") is True, {"path": str(release_drill_result)}))
    checks.append(_check("live_smoke_success", live.get("success") is True and live.get("provider_status") == 200, {"path": str(live_smoke_result), "provider_status": live.get("provider_status")}))
    leaks = live.get("leak_checks") if isinstance(live.get("leak_checks"), dict) else {}
    checks.append(_check("live_smoke_redacted", bool(leaks) and all(leaks.values()), {"leak_checks": leaks}))
    missing_docs = [path for path in REQUIRED_DOCS if not (ROOT / path).exists()]
    checks.append(_check("public_docs_present", not missing_docs, {"missing": missing_docs, "required": list(REQUIRED_DOCS)}))
    if manifest is not None:
        manifest_data = _load(manifest)
        artifacts = manifest_data.get("artifacts")
        sha_ok = isinstance(artifacts, list) and bool(artifacts) and all(isinstance(item, dict) and len(str(item.get("sha256", ""))) == 64 for item in artifacts)
        checks.append(_check("release_manifest_sha256", sha_ok, {"path": str(manifest), "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0}))
    return {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "success": all(check["ok"] for check in checks),
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit release drill, live smoke, docs, and artifact manifest evidence")
    parser.add_argument("--release-drill-result", type=Path, required=True)
    parser.add_argument("--live-smoke-result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out", type=Path, default=Path("release-gate-audit.json"))
    args = parser.parse_args()
    result = audit(args.release_drill_result, args.live_smoke_result, args.manifest)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
