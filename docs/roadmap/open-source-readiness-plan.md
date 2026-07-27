# DeepSeek Runtime 开源就绪迭代计划

> 核心原则：不横向扩功能，只把现有承诺做到真实、稳定、可验证。
> 目标终点：首个可信的 Open-source Alpha，而不是功能最多的 Agent Framework。

## 1. 不做清单

在首次公开 Alpha 前，不新增：

- MCP；
- Skills；
- Multi-Agent；
- RAG/Vector Memory；
- IDE/TUI/Desktop；
- Hosted API；
- Plugin marketplace；
- 多 Provider 大扩张；
- Workflow DSL；
- Browser/Computer Use。

这些功能会扩大攻击面和测试矩阵，不解决当前核心问题。

## 2. 里程碑总览

| 里程碑 | 目标 | Exit Gate |
| --- | --- | --- |
| M0 文档冻结 | 产品范围和验收单一真源 | PRD/架构/测试/路线图合入 |
| M1 P0 安全修复 | 关闭 workspace/rollback 越界 | P0 adversarial 100% |
| M2 Runtime 闭环 | ToolSpec + policy + approval + lifecycle | 所有工具不可绕过 |
| M3 恢复正确性 | checkpoint/evidence 分离，uncertain side effect | recovery tests 100% |
| M4 工程化 | CI、类型、coverage、release allowlist | 多平台全绿 |
| M5 Release Candidate | 文档、安装、live smoke、构件验证 | Release Gate 全通过 |

## 3. M0：文档与范围冻结

### 工作项

- 合入本资料包；
- README 改为引用 PRD 和架构；
- 为现有能力标注 Implemented/Partial/Planned；
- 建立 requirement → test traceability；
- 冻结 Alpha 非目标。

### 验收

- 所有开发讨论以 PRD ID 为依据；
- 不再通过 README 隐式新增需求；
- 路线图无新增大功能。

## 4. M1：P0 安全边界

### 4.1 Rollback

- Opaque rollback handle；
- Manager 私有 state；
- sandbox/policy revalidation；
- post-change hash conflict；
- forged/external/stale tests。

### 4.2 Workspace Symlink

- search/read 统一 containment；
- skip symlink 默认策略；
- resource budget；
- POSIX/Windows tests。

### 验收

- TC-CHG-001/002、TC-WS-001/002/003 全通过；
- 无 S0 缺陷；
- 更新 SECURITY 和 Known Unknowns。

## 5. M2：Runtime 执行闭环

### 最小新增抽象

仅新增：

- `ToolSpec`
- `ToolRegistry`
- `ToolExecutionResult`
- `ApprovalProvider`
- `RuntimeBudget`
- lifecycle event

### 改造

- Runtime 不再接收裸 handler dict；
- 参数 JSON Schema 校验；
- policy/approval 强制执行；
- timeout/output limit；
- tool error code；
- CLI 默认输出最终答案，安全报告分离。

### 验收

- 完整 3 轮 fake tool loop；
- 未知/非法工具不调用 handler；
- ASK approve/deny/timeout；
- 所有工具均有 policy event；
- RuntimeResult 不因任意 Provider JSON 未处理崩溃。

## 6. M3：Checkpoint 与恢复

### 工作项

- `RecoverableCheckpoint` 与 `PublishableEvidence` 分离；
- provider continuation 完整保存；
- 可选 checkpoint encryption；
- tool receipt/idempotency key；
- `TOOL_UNCERTAIN` 状态；
- retry budget；
- schema migration；
- file lock/corruption detection。

### 验收

- crash-before-effect、after-effect-before-save、after-save 三窗口测试；
- succeeded 不重复；
- running side effect 不自动重试；
- thinking tool-call 可恢复；
- 磁盘 checkpoint 无 Key，开启 encryption 后无 prompt 明文。

## 7. M4：工程化与发布

### CI

- Ubuntu/macOS/Windows；
- Python 3.11/3.12/3.13；
- Ruff；
- Pyright/Mypy 二选一；
- coverage；
- property/adversarial；
- package build/install。

### Release

- 从 Git tracked allowlist 构建；
- wheel + sdist；
- secret scan；
- 重算 SHA-256；
- reproducible metadata；
- release manifest；
- live smoke；
- release gate。

### Open-source Governance

只补必须文件：

- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- issue/PR templates
- changelog/release process
- support policy
- security scope

不建立复杂社区流程。

## 8. M5：Release Candidate

### RC 检查

- README quick start 逐行执行；
- API examples 逐行执行；
- clean machine install；
- fake provider E2E；
- live DeepSeek smoke；
- test report；
- known limitations；
- version/tag/artifact 一致；
- License/notice；
- 依赖和供应链审查。

### Release 标准

必须全部满足：

- P0/P1 = 0；
- CI 全绿；
- flaky = 0；
- 安全用例全绿；
- live smoke 全绿；
- artifact digest verified；
- README claim traceability 100%。

## 9. 建议迭代批次

### Batch A：安全边界

- CR-P0-001；
- CR-P0-002；
- CFG env bug；
- malformed response totality。

### Batch B：执行合同

- ToolSpec/Registry；
- Policy/Approval；
- Runtime lifecycle；
- CLI output。

### Batch C：恢复合同

- checkpoint/evidence；
- receipts；
- uncertain state；
- migration/encryption。

### Batch D：开源交付

- CI；
- tests；
- packaging；
- governance docs；
- RC report。

每个 Batch 都必须独立可测试、可 review，不做超大合并。

## 10. 资源分配原则

建议优先级：

- 40% 安全与恢复；
- 30% 自动化测试；
- 20% Runtime 集成；
- 10% 文档和发布。

禁止把时间投入新的展示型功能来掩盖基础缺陷。

## 11. 风险

| 风险 | 应对 |
| --- | --- |
| 为追求“生产级”引入过多抽象 | 只增加 ToolSpec/Registry/Approval/Budget 最小集合 |
| 沙箱目标失控 | 首版明确 local trusted；隔离交给 adapter |
| Provider 协议快速变化 | adapter + live smoke，不把模型名写死在多处 |
| 恢复语义过度承诺 | 明确 at-least-once/uncertain，不承诺通用 exactly-once |
| 测试数量多但无价值 | P0/P1 threat model 驱动测试 |
| 文档再次漂移 | PRD ID + test ID + release traceability |

## 12. 最终产品形态

首个开源版本应是：

> 一个小而可信的 DeepSeek Agent Runtime Kernel：能跑、多步可控、状态可恢复、证据可分享、边界不夸大、任何贡献者都能验证。

它不需要成为功能最全的 Agent 产品；只需要成为同类中产品边界最清楚、执行合同最严谨、最容易 fork 的基础内核。
