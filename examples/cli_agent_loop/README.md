# CLI Agent Loop Example

Run a prompt with workspace tools:

```bash
export DEEPSEEK_API_KEY=...
deepseek-runtime run --workspace . "Search for RuntimeSettings and summarize how configuration works."
```

Default output is safe for logs and does not include prompt or response text.

For trusted local debugging only:

```bash
deepseek-runtime run --include-content --workspace . "Search for RuntimeSettings and summarize how configuration works."
```
