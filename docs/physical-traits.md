# DeepSeek Physical Traits

This runtime does not claim complete coverage of every DeepSeek V4 behavior. It supports the traits that are verified or modeled enough to affect local-agent execution.

## Support Matrix

| Trait | Runtime support | Evidence |
| --- | --- | --- |
| Official OpenAI-compatible endpoint | `RuntimeSettings` defaults to `https://api.deepseek.com`; `DeepSeekClient` calls `/chat/completions`. | Official docs and live smoke. |
| V4 model IDs | Default model is `deepseek-v4-flash`; `DEEPSEEK_MODEL` can select `deepseek-v4-pro`. | Settings and diagnostics. |
| Thinking mode | Runtime sends `thinking: {"type": "enabled"}` in agent loop and live smoke. | Request evidence records the field. |
| Reasoning effort | Live smoke uses `DEEPSEEK_REASONING_EFFORT` or `high`. | Request evidence records the field. |
| Reasoning-content field | Response evidence records field presence, hash, and bytes, not raw text. | `response_evidence()` and live smoke leak checks. |
| Function tool calls | Runtime accepts DeepSeek function tool calls and appends `tool` role results. | Unit tests and agent loop. |
| Streaming chunks | `chat_stream()` parses SSE events, delta fields, finish reasons, tool names, and reasoning-content presence. | Stream evidence. |
| Prefix/cache tokens | Diagnostics and observability parse `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, `cache_hit_tokens`, `cache_miss_tokens`, and `prompt_tokens_details.cached_tokens`. | Observability drill. |
| Usage economics | Observability computes success rate, first-completion rate, token totals, estimated cost, and cost per success. | Observability drill. |
| Redacted release evidence | CLI and smoke scripts write fingerprints and structural evidence by default. | Release gate audit. |
| Local workspace safety | Sandbox, permission policy, diff preview, rollback, and session resume are included as runtime primitives. | Safety drill. |

## Why This Matters

Many provider wrappers stop at connection, response parsing, and optional cache statistics. A local agent runtime needs more:

- It must expose reasoning mode decisions because they change quality, cost, and latency.
- It must keep `reasoning_content` out of public evidence while still proving whether the field exists.
- It must preserve tool-loop semantics because local side effects depend on correct call ordering.
- It must show cache and cost in the same evidence stream as success/failure.
- It must provide sandbox and rollback primitives because local agents touch files.

## Official API References

- [DeepSeek API quick start](https://api-docs.deepseek.com/)
- [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion)
