from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class CliAndScriptsTests(unittest.TestCase):
    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env

    def test_cli_doctor_json(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "deepseek_runtime.cli", "doctor", "--json", "--workspace", str(ROOT)],
            cwd=ROOT,
            env=self._env(),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        bundle = json.loads(completed.stdout)
        self.assertIn("checks", bundle)
        self.assertEqual(bundle["config_summary"]["deepseek_api_key"], "absent")

    def test_release_scripts_without_live_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            release = subprocess.run(
                [sys.executable, "scripts/release_drill.py", "--skip-tests", "--out", str(out / "release-drill.json")],
                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(release.returncode, 0, release.stderr)
            artifact = subprocess.run(
                [sys.executable, "scripts/build_release_artifact.py", "--out", str(out / "dist"), "--manifest", str(out / "manifest.json")],
                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(artifact.returncode, 0, artifact.stderr)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["success"])
            self.assertEqual(len(manifest["artifacts"][0]["sha256"]), 64)

    def test_release_gate_audit_with_fixture_live_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            release = out / "release.json"
            live = out / "live.json"
            manifest = out / "manifest.json"
            release.write_text(json.dumps({"success": True}), encoding="utf-8")
            live.write_text(json.dumps({"success": True, "provider_status": 200, "leak_checks": {"api_key_absent": True, "prompt_absent": True, "response_content_absent": True, "reasoning_content_absent": True}}), encoding="utf-8")
            manifest.write_text(json.dumps({"artifacts": [{"sha256": "a" * 64}]}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/release_gate_audit.py",
                    "--release-drill-result",
                    str(release),
                    "--live-smoke-result",
                    str(live),
                    "--manifest",
                    str(manifest),
                    "--out",
                    str(out / "audit.json"),
                ],
                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(json.loads(completed.stdout)["success"])


if __name__ == "__main__":
    unittest.main()
