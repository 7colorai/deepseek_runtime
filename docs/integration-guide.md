# Integration Guide

Use this runtime as the kernel underneath a CLI, desktop app, web workbench, or another local agent.

## Minimal Integration

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings

runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
result = runtime.run(
    [{"role": "user", "content": "Explain this repository in one paragraph."}],
    workspace=".",
)

if result.ok:
    print(result.final_text)
else:
    print(result.error_class, result.error)
```

## Tool Integration

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools

runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
tools = WorkspaceTools(".").catalog()

result = runtime.run(
    [{"role": "user", "content": "Search for RuntimeSettings and summarize it."}],
    workspace=".",
    tools=tools,
)
```

The built-in `WorkspaceTools` example exposes:

- `read_file`
- `search`

Production integrations should wrap tools with their own approval and permission policy before executing side effects.

## Evidence Boundary

For UI or public logs, display `result.to_safe_dict()`.

For trusted local application flows, use `result.final_text` or `result.to_dict(include_content=True)`.

Do not publish:

- raw prompt text
- raw response text
- API keys
- `reasoning_content`
- session checkpoints that include private messages

## Recommended UI Mapping

| Runtime field | UI use |
| --- | --- |
| `ok` | Final status indicator. |
| `final_text` | Main answer, only in trusted local UI. |
| `usage` | Token counters and budget view. |
| `evidence[].request_fingerprint` | Debug copy ID. |
| `evidence[].request_evidence` | Request structure inspector. |
| `evidence[].response_evidence` | Response structure inspector. |
| `diagnostics` | Doctor panel. |
| `error_class` / `error` | Error banner. |

## Release Integration

Before building on this runtime, run:

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

The hosted service path is intentionally out of `0.1.1a0`; see [Hosting Roadmap](hosting-roadmap.md).
