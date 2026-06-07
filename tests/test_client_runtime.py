from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from deepseek_runtime.client import DeepSeekClient, ProviderResult, RuntimeSettings
from deepseek_runtime.evidence import response_evidence
from deepseek_runtime.runtime import DeepSeekRuntime, WorkspaceTools


class ClientRuntimeTests(unittest.TestCase):
    def test_client_chat_builds_official_endpoint_request(self) -> None:
        calls: list[dict[str, Any]] = []

        def transport(method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float):
            calls.append({"method": method, "url": url, "headers": headers, "data": data, "timeout": timeout})
            body = {"choices": [{"message": {"role": "assistant", "content": "answer"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}}
            return 200, {"x-request-id": "req-1"}, json.dumps(body).encode()

        client = DeepSeekClient(RuntimeSettings(api_key="secret", base_url="https://api.deepseek.com", model="deepseek-v4-flash"), transport=transport)
        result = client.chat({"messages": [{"role": "user", "content": "hello"}]})

        self.assertEqual(result.status, 200)
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(calls[0]["method"], "POST")
        self.assertEqual(calls[0]["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret")
        payload = json.loads(calls[0]["data"])
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual(payload["messages"][0]["content"], "hello")

    def test_runtime_safe_dict_does_not_include_prompt_or_response_text(self) -> None:
        class FakeClient:
            def chat(self, payload: dict[str, Any]) -> ProviderResult:
                return ProviderResult(
                    status=200,
                    elapsed_ms=1,
                    body={"choices": [{"message": {"role": "assistant", "content": "private answer"}, "finish_reason": "stop"}], "usage": {"total_tokens": 7}},
                    request_fingerprint="abc",
                    request_payload=payload,
                )

        runtime = DeepSeekRuntime(FakeClient())  # type: ignore[arg-type]
        result = runtime.run([{"role": "user", "content": "private prompt"}], workspace=Path("."))
        safe = json.dumps(result.to_safe_dict(), ensure_ascii=False)
        raw = json.dumps(result.to_dict(include_content=True), ensure_ascii=False)

        self.assertTrue(result.ok)
        self.assertNotIn("private prompt", safe)
        self.assertNotIn("private answer", safe)
        self.assertIn("private prompt", raw)
        self.assertIn("private answer", raw)

    def test_runtime_reports_malformed_provider_response(self) -> None:
        class FakeClient:
            def chat(self, payload: dict[str, Any]) -> ProviderResult:
                return ProviderResult(status=200, elapsed_ms=1, body={"choices": []}, request_fingerprint="abc", request_payload=payload)

        result = DeepSeekRuntime(FakeClient()).run([{"role": "user", "content": "hello"}], workspace=Path("."))  # type: ignore[arg-type]
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "malformed provider response")

    def test_response_evidence_hides_reasoning_content(self) -> None:
        evidence = response_evidence(
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "visible", "reasoning_content": "hidden reasoning"},
                        "finish_reason": "stop",
                    }
                ]
            }
        )
        serialized = json.dumps(evidence, ensure_ascii=False)
        self.assertIn("has_reasoning_content", serialized)
        self.assertNotIn("hidden reasoning", serialized)
        self.assertNotIn("visible", serialized)

    def test_workspace_tools_accept_string_root(self) -> None:
        tools = WorkspaceTools(".").catalog()
        self.assertIn("read_file", tools)


if __name__ == "__main__":
    unittest.main()
