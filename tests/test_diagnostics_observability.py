from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deepseek_runtime.diagnostics import build_diagnostics
from scripts.release_observability_drill import run_observability_drill


class DiagnosticsObservabilityTests(unittest.TestCase):
    def test_diagnostics_are_redacted_and_do_not_require_live_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = build_diagnostics(Path(directory), env={})
        self.assertTrue(bundle["ok"])
        self.assertEqual(bundle["config_summary"]["deepseek_api_key"], "absent")
        self.assertIn("api_key_absent", bundle["warnings"])

    def test_observability_drill_exposes_route_cache_usage_cost(self) -> None:
        result = run_observability_drill()
        self.assertTrue(result["success"])
        summary = result["summary"]
        self.assertEqual(summary["task_count"], 3)
        self.assertIn("deepseek-v4-flash", summary["models"])
        self.assertGreater(summary["prompt_cache_hit_tokens"], 0)
        self.assertGreater(summary["estimated_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
