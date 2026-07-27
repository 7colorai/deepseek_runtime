# DeepSeek Runtime 测试计划

> 版本：1.0
> 基线：`develop@0e1e435`
> 目标：证明 Open-source Alpha 的功能、边界、安全和发布过程，而不是只证明 Happy Path。

## 1. 测试目标

1. 验证 PRD 中所有 P0/P1 要求。
2. 验证模型、Provider、文件系统和 Tool 均可输入恶意或异常数据。
3. 验证中断恢复不会盲目重复副作用。
4. 验证默认输出和发布构件不泄露敏感内容。
5. 建立任何贡献者都能复现的 CI 证据。

## 2. 测试层级

| 层级 | 范围 | 比例目标 |
| --- | --- | ---: |
| Unit | 纯函数、状态机、schema、policy | 60% |
| Component | Client、Registry、Store、ChangeManager | 25% |
| Integration | Runtime + fake provider + fake tools | 10% |
| E2E | CLI、安装、live API、release artifact | 5% |
| Property/Fuzz | arbitrary JSON、路径、SSE chunks | 持续 |
| Security Adversarial | traversal、symlink、token forge、secret leak | 发布门禁 |

## 3. 环境矩阵

- Python：3.11、3.12、3.13；
- OS：Ubuntu、macOS、Windows；
- 文件系统：默认 runner FS；POSIX symlink；Windows junction/reparse point；
- Provider：
  - deterministic fake provider；
  - malformed provider fixtures；
  - rate-limit/timeout fake transport；
  - 最少一次真实 DeepSeek smoke；
- Sandbox：
  - no-isolation fake；
  - restricted subprocess；
  - 可选 Docker/Podman。

## 4. 测试数据原则

- 不使用真实用户 prompt。
- 不在 fixture 保存真实 API Key。
- Secret fixture 使用显眼假值：`sk-test-do-not-use`。
- 所有 Provider 响应使用最小结构化 fixture。
- Side-effect 测试只操作临时目录或内存 fake。
- Live smoke 只生成无业务内容的固定短句。

## 5. 测试范围

### Provider

- request merge；
- response normalization；
- arbitrary JSON root；
- error mapping；
- retry/backoff；
- response-size limit；
- request identity；
- SSE framing/chunking/cancellation。

### Runtime

- text only；
- one/multiple tool calls；
- parallel calls（若支持）；
- unknown tool；
- invalid arguments；
- tool timeout/error/output overflow；
- max step/token/cost/time；
- cancellation；
- lifecycle events；
- malformed provider。

### Tool/Security

- schema validation；
- duplicate registry；
- default deny；
- rule conflict；
- approval；
- path traversal；
- symlink；
- command wrapper bypass；
- environment secret inheritance；
- process tree timeout。

### Change/Session

- apply/rollback；
- forged token；
- stale hash；
- duplicate path；
- concurrent writes；
- metadata；
- crash injection；
- corrupt checkpoint；
- schema migration；
- uncertain side effects；
- receipt/idempotency。

### Evidence/Observability

- no secret/content；
- error secret redaction；
- canonical identity；
- arbitrary JSON；
- unknown cost；
- partial metrics；
- budget evidence。

### CLI/Release

- doctor；
- run output；
- report file；
- exit codes；
- clean install；
- wheel/sdist；
- tracked-file allowlist；
- secret scan；
- digest verification；
- reproducibility；
- docs traceability。

## 6. 测试技术

- `unittest` 可继续使用；允许引入 `pytest` 需单独决策。
- Property test 建议使用 Hypothesis。
- Clock、random、transport、approval、filesystem adapter 必须可注入。
- Fault injection 点：
  - after effect before checkpoint；
  - after temp write before replace；
  - after first file replace；
  - checkpoint partial/corrupt；
  - SSE byte split。
- Snapshot 仅用于稳定 schema，避免把业务逻辑完全写进 snapshot。

## 7. Coverage 要求

| 区域 | 最低要求 |
| --- | ---: |
| 总体 line coverage | 85% |
| 总体 branch coverage | 75% |
| P0 安全路径 | 100% |
| Runtime 状态转换 | 95% |
| Session recovery | 95% |
| Provider error normalization | 90% |
| Release gate | 90% |

Coverage 不是发布充分条件；P0 adversarial 用例必须独立全部通过。

## 8. CI Pipeline

```text
lint
→ type-check
→ unit/property tests
→ integration tests
→ security adversarial tests
→ package build
→ clean install smoke
→ secret scan
→ manifest verification
→ docs traceability
→ optional live smoke
```

PR 不执行真实付费 API；live smoke 在受保护环境、手动发布流程或定时任务执行。

## 9. 准入标准

进入 RC 测试前：

- PRD 范围冻结；
- P0 修复代码合入；
- error/schema 稳定；
- 测试 fixture 已评审；
- 无已知数据泄漏；
- CI workflow 可运行。

## 10. 退出标准

- P0/P1 用例 100% 通过；
- 无未关闭 P0/P1；
- 多平台矩阵全绿；
- flaky rate < 1%，不得通过重跑掩盖；
- live smoke 通过；
- artifact 可验证且 secret scan 通过；
- Test Report 给出 Release。

## 11. 缺陷等级

- S0：可越界写/删、泄露密钥、重复高价值副作用；
- S1：核心流程不可用、状态损坏、错误恢复错误；
- S2：部分功能错误、指标不准、UX 严重偏差；
- S3：文档、可维护性、低影响兼容性。

S0/S1 均阻断发布。

## 12. Traceability

每个测试用例必须标注：

- Test Case ID；
- PRD Requirement ID；
- 层级；
- 优先级；
- 前置条件；
- 输入；
- 预期；
- 自动化状态；
- 最后执行证据。
