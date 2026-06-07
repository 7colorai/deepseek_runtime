from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from deepseek_runtime.security import Decision, PermissionDenied, PermissionPolicy, PermissionRequest, PermissionRule, Risk, SandboxViolation, WorkspaceSandbox
from deepseek_runtime.session import SessionState, SessionStore, ToolCallRecord, resume_tool_calls


class SecuritySessionTests(unittest.TestCase):
    def test_sandbox_blocks_path_escape_and_network_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sandbox = WorkspaceSandbox(Path(directory))
            with self.assertRaises(SandboxViolation):
                sandbox.resolve("../outside")
            with self.assertRaises(PermissionDenied):
                sandbox.run(("curl", "https://example.com"))

    def test_permission_policy_redacts_command_secrets(self) -> None:
        policy = PermissionPolicy([PermissionRule(Risk.NETWORK, Decision.DENY)])
        decision = policy.decide(PermissionRequest(Risk.NETWORK, command=("curl", "--token", "secret")))
        self.assertEqual(decision, Decision.DENY)
        self.assertNotIn("secret", str(policy.audit_events))

    def test_session_store_round_trips_and_resume_does_not_repeat_completed_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SessionStore(Path(directory))
            state = SessionState(messages=[{"role": "user", "content": "keep local"}], tool_calls=[ToolCallRecord("work", {"value": 1}, True)])
            store.save(state)
            loaded = store.load(state.session_id)
            calls: list[int] = []

            def handler(arguments):
                calls.append(arguments["value"])
                return "done"

            resume_tool_calls(loaded, {"work": handler})
            resume_tool_calls(loaded, {"work": handler})
            self.assertEqual(calls, [1])
            self.assertEqual(loaded.tool_calls[0].status, "succeeded")


if __name__ == "__main__":
    unittest.main()
