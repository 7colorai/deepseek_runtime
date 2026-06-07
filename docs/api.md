# API Reference

This document covers the public `0.1.1a0` API surface. Anything outside this list should be treated as internal.

## Settings

### `RuntimeSettings.from_env()`

Reads DeepSeek configuration from environment variables.

| Variable | Default | Notes |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | required | Required for live provider calls. Never logged. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Official OpenAI-compatible base URL. |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Use `deepseek-v4-pro` when higher reasoning quality is needed. |
| `DEEPSEEK_TIMEOUT` | `120` | Seconds. |
| `DEEPSEEK_MAX_TOKENS` | `512` | Applied when the payload does not override generation length. |

## Client

### `DeepSeekClient.chat(payload)`

Calls `POST /chat/completions`. The client merges `model` and `max_tokens` defaults with the provided payload.

Returns `ProviderResult`:

| Field | Meaning |
| --- | --- |
| `status` | HTTP status or `0` for transport failure. |
| `elapsed_ms` | Request duration. |
| `body` | Parsed provider JSON. May include raw content; do not log directly. |
| `request_fingerprint` | sha256 of the wire JSON request body. |
| `usage` | Provider usage object when available. |
| `request_id` | Provider request ID header when available. |
| `error` / `error_class` | Redacted failure summary. |

### `DeepSeekClient.chat_stream(payload)`

Calls `POST /chat/completions` with `stream: true`. It returns structural stream evidence, including event count, first event latency, delta fields, finish reasons, content presence, reasoning-content presence, and tool names.

### `DeepSeekClient.models()`

Calls `GET /models` and returns a `ProviderResult`.

## Runtime

### `DeepSeekRuntime.run(messages, workspace, tools=None)`

Runs a bounded agent loop:

1. Sends messages to DeepSeek with thinking enabled.
2. Records request and response structural evidence.
3. Parses DeepSeek function tool calls.
4. Executes matching local handlers from `tools`.
5. Appends tool results and repeats until final content, provider error, malformed response, or `max_steps`.

`tools` is a dictionary from function name to `Callable[[dict], str]`.

Returns `RuntimeResult`.

Important methods:

| Method | Output |
| --- | --- |
| `to_safe_dict()` | Safe for logs. Contains hashes, byte counts, message evidence, diagnostics, and usage. |
| `to_dict()` | Same as `to_safe_dict()` by default. |
| `to_dict(include_content=True)` | Includes prompt and response text. Use only for local trusted flows. |

## Diagnostics

### `build_diagnostics(workspace, evidence=None)`

Builds a redacted local diagnostics bundle. It checks Python version, workspace existence, session-store writability, CLI entrypoint availability, API key presence, and optional route/cache/usage/cost evidence.

## Observability

### `summarize_observability(data, pricing, source)`

Summarizes task-level model route, cache hit/miss tokens, total tokens, estimated cost, success rate, first-completion rate, tokens per success, and cost per success.

## Safety And Session

### `WorkspaceSandbox`

Constrains file paths to a workspace root and classifies local commands by risk.

### `PermissionPolicy`

Applies ordered permission rules and records redacted audit events.

### `SessionState`

Stores resumable messages, tool calls, approvals, change sets, usage, and evidence.

Session persistence may contain prompt and response text because it is intended for local resume. Do not upload session files as public evidence.
