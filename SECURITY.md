# Security Policy

DeepSeek Runtime is local-first. It includes safety primitives, but it is not a complete operating-system sandbox.

## Secret Handling

- Put the API key in `DEEPSEEK_API_KEY`.
- Do not put API keys in prompts, command arguments, session files, Git history, or public issue comments.
- `doctor`, release scripts, and live smoke output redacted summaries by default.
- `deepseek-runtime run --include-content` is intentionally unsafe for logs because it includes prompt and response text.

## Evidence Handling

Public release evidence should use:

- `RuntimeResult.to_safe_dict()`
- `deepseek-runtime doctor --json`
- `scripts/live_api_smoke.py`
- `scripts/release_drill.py`
- `scripts/release_gate_audit.py`

Do not publish raw provider response bodies, raw session checkpoints, or files containing `reasoning_content`.

## Workspace Safety

`WorkspaceSandbox` prevents path traversal outside the configured workspace and classifies commands by risk. `PermissionPolicy` can deny, allow, or ask for risky operations.

This is a runtime guardrail, not a replacement for OS sandboxing, containers, file permissions, or human review.

## Reporting Issues

For now, report issues in the GitHub repository:

https://github.com/7colorai/deepseek_runtime/issues
