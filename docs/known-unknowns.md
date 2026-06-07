# Known Unknowns

These items are intentionally explicit for `0.1.1a0`.

| Area | Status | Next check |
| --- | --- | --- |
| Full DeepSeek V4 physical-trait coverage | Not claimed. Only verified or modeled traits are documented. | Expand matrix after additional protocol and benchmark evidence. |
| Real billing accuracy | Not claimed. Cost is estimated from a pricing snapshot or explicit evidence. | Compare against provider billing exports when available. |
| Hosted multi-tenant safety | Not included. Runtime is local-first. | See hosting roadmap. |
| Complete shell sandboxing | Not claimed. The sandbox is a runtime primitive, not a kernel-level security boundary. | Add OS-level sandbox guidance before hosted use. |
| Long-running stream stability | Partially modeled. Stream parser records event structure, not full production stress behavior. | Add live stream soak tests. |
| Prompt privacy under user code | Runtime safe outputs redact by default, but integrations can still log raw `result.final_text` or messages. | Add integration lint checks and logging adapters. |
| Tool argument hallucination | Runtime parses JSON and routes known tools, but business validation belongs to each tool handler. | Add schema validation examples for production tools. |
| Model naming drift | Official docs can change. | Keep live smoke and README model references synchronized with official docs before each tag. |
