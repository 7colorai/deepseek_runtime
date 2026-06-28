# DeepSeek Runtime

[English](README_en.md) | [简体中文](README.md)

DeepSeek Runtime is a fork-ready Python runtime kernel for building local agents on the official DeepSeek API.

It is not a cache-only wrapper. The project focuses on DeepSeek physical traits that affect agent correctness, evidence, safety, diagnostics, and cost visibility.

Research lineage:

- Runtime repository target: [7colorai/deepseek_runtime](https://github.com/7colorai/deepseek_runtime)
- Parent product line: [yuanchenglu/deepseekagent](https://github.com/yuanchenglu/deepseekagent)
- Harness research archive: [yuanchenglu/llm-harness-agent](https://github.com/yuanchenglu/llm-harness-agent)
- Official DeepSeek API docs: [api-docs.deepseek.com](https://api-docs.deepseek.com/)

## Value Matrix

| Layer | DeepSeek physical trait or local-agent problem | What this runtime ships | Why it is beyond cache hit rate |
| --- | --- | --- | --- |
| Native chat contract | DeepSeek exposes OpenAI-compatible `/chat/completions` with V4 model IDs, thinking mode, tool calls, stream chunks, and usage fields. | `DeepSeekClient.chat()`, `chat_stream()`, `models()`, and `RuntimeSettings.from_env()`. | The runtime preserves DeepSeek-specific request fields instead of hiding them behind a generic provider shim. |
| Thinking mode control | DeepSeek V4 has explicit `thinking` and `reasoning_effort` controls. | `DeepSeekRuntime.run()` enables thinking by default and live smoke verifies the official endpoint accepts the native shape. | Cache-only runtimes do not model reasoning-mode controls as first-class runtime behavior. |
| Reasoning-content hygiene | Thinking responses may include `reasoning_content`; this must not be written into release evidence or logs. | Evidence records presence, fields, byte counts, and hashes, never raw `reasoning_content`. | This protects chain-of-thought-like data while still proving the model response shape. |
| Wire evidence | Protocol experiments and cache behavior depend on exact request bytes. | Stable JSON wire encoding and request sha256 fingerprints. | It lets maintainers compare runtime behavior without storing prompt text. |
| Function tool loop | DeepSeek tool-call responses carry function names and JSON argument strings. | Bounded tool loop, JSON argument parsing, tool result messages, max-step stop. | Agent correctness depends on loop semantics, not only provider connectivity. |
| Prefix-cache observability | DeepSeek usage can expose cache hit/miss token fields. | Diagnostics and observability summarize hit tokens, miss tokens, total tokens, success rate, and estimated cost. | Cache visibility is connected to task success and cost, not treated as a single isolated metric. |
| Local safety | Local agents need workspace boundaries, permission decisions, previews, rollback, and resumable side effects. | `WorkspaceSandbox`, `PermissionPolicy`, change-set rollback primitives, `SessionState`, and deterministic safety drill. | This is runtime infrastructure for local agents, not an API cache. |
| Release evidence | Fork users need to prove installability, diagnostics, artifact checksums, and live API compatibility. | `doctor`, `release_drill.py`, `build_release_artifact.py`, `release_gate_audit.py`, and `live_api_smoke.py`. | A release is accepted only with executable evidence and redaction checks. |

## Scope

Version `0.1.1a1` is a Runtime Kernel Open Alpha.

Included:

- Python package distribution: `deepseek-runtime`
- Import namespace: `deepseek_runtime`
- CLI: `deepseek-runtime doctor --json` and `deepseek-runtime run`
- Real DeepSeek official API smoke through `DEEPSEEK_API_KEY`
- Local safety, session, diagnostics, evidence, and observability primitives

Not included:

- Hosted API service
- Desktop GUI
- Mobile app
- Enterprise policy center
- Plugin marketplace

## Install

```bash
git clone https://github.com/7colorai/deepseek_runtime.git
cd deepseek_runtime
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
deepseek-runtime doctor --json
```

`doctor --json` does not call the live DeepSeek API. It reports local health, redacted config, entrypoint availability, workspace writability, session-store writability, and optional evidence summaries.

## Run

```bash
export DEEPSEEK_API_KEY=...
deepseek-runtime run --workspace . "Summarize this repository structure."
```

By default, CLI JSON output is safe for logs: it emits fingerprints, byte counts, message structure, usage, and diagnostics, but not prompt or response text. Use `--include-content` only for local interactive debugging.

## Python API

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools

settings = RuntimeSettings.from_env()
client = DeepSeekClient(settings)
runtime = DeepSeekRuntime(client)
tools = WorkspaceTools(".").catalog()

result = runtime.run(
    [{"role": "user", "content": "List the files in this workspace."}],
    workspace=".",
    tools=tools,
)

print(result.ok)
print(result.final_text)
print(result.to_safe_dict())
```

## Live API Smoke

```bash
export DEEPSEEK_API_KEY=...
python3 scripts/live_api_smoke.py --out live-smoke.json
```

The smoke writes only redacted structural evidence:

- request fingerprint
- request/response field summaries
- token usage
- response content hash and byte count
- reasoning-content presence/hash/byte count
- leak checks for API key, prompt text, response text, and reasoning text

## Release Verification

```bash
python3 -m unittest discover -s tests -v
deepseek-runtime doctor --json
python3 scripts/release_drill.py
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

## Documentation

- [API Reference](docs/api.md)
- [Integration Guide](docs/integration-guide.md)
- [Physical Traits](docs/physical-traits.md)
- [Known Unknowns](docs/known-unknowns.md)
- [Hosting Roadmap](docs/hosting-roadmap.md)
- [Security](SECURITY.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
