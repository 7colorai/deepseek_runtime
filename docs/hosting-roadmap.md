# Hosting Roadmap

Hosted service support is out of scope for `0.1.1a1`.

The current release is a local Python runtime kernel. It can be used by a hosted service later, but it does not ship:

- multi-tenant API server
- request queue
- tenant isolation
- cloud secret manager integration
- hosted billing
- web dashboard
- enterprise policy center

## Future Hosted Shape

| Phase | Work |
| --- | --- |
| H1 | Define hosted threat model, tenant boundaries, secret storage, audit retention, and rate-limit policy. |
| H2 | Add service adapter around `DeepSeekRuntime` without changing the kernel API. |
| H3 | Add OS/container sandboxing around workspace tools. |
| H4 | Add hosted observability exports and billing reconciliation. |
| H5 | Add public API docs and compatibility tests for the service layer. |

## Current Guidance

For now, keep hosted code outside this repository or in a separate service package. This prevents the runtime kernel from being coupled to deployment choices too early.
