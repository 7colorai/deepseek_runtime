# DeepSeek Runtime 产品需求文档（PRD）

> 文档版本：1.0
> 产品阶段：Open-source Alpha Hardening
> 适用基线：`develop@0e1e435`
> 唯一目标：以最少新增功能，把项目做到可以真实、可信、可持续地开源。

## 0. 文档规则

- 本 PRD 是产品范围、优先级和验收标准的唯一事实源。
- `P0`：不满足则禁止公开发布。
- `P1`：首个公开 Alpha 必须满足。
- `P2`：可在 Alpha 后迭代，不阻塞首次开源。
- 状态：`Implemented`、`Partial`、`Planned`、`Blocked`。
- “实现存在”不等于“验收通过”；只有自动化测试和发布报告才能标记 `Verified`。

## 1. 背景

直接调用 DeepSeek API 不能自动解决 Agent 产品所需的工具治理、状态恢复、文件变更、证据隐私、成本控制和发布验证。

当前仓库已实现多个基础原语，但存在三类根本问题：

1. 模块未形成端到端执行闭环；
2. 安全和恢复语义存在可绕过或不确定行为；
3. 产品承诺、测试证据和代码实现未统一。

## 2. 产品目标

### G-01：可运行

开发者在 5 分钟内完成安装、doctor 和无网络单元测试。

### G-02：可控

每次工具执行都经过参数验证、权限决策、超时和输出预算。

### G-03：可恢复

任务中断后能够恢复；对不确定副作用不盲目重复执行。

### G-04：可审计

默认输出不泄露 API Key、prompt、response 和 reasoning 正文。

### G-05：可贡献

贡献者能通过单一命令运行 lint、type check、tests 和 release checks。

### G-06：可发布

发布构件来源明确、可复现、经过 secret scan 和自动化门禁。

## 3. 非目标

- 不开发完整桌面端、IDE、TUI。
- 不开发云端多租户。
- 不开发账号、计费、组织权限。
- 不开发通用插件市场。
- 不承诺任意外部系统 exactly-once。
- 不使用 Python 命令黑名单宣称内核级隔离。
- 不在首个 Alpha 增加 Memory/RAG/MCP/Multi-Agent 等新能力。

## 4. 用户与场景

### Persona A：Runtime 集成开发者

需要稳定 Python API，把 Agent loop 嵌入自己的产品。

### Persona B：Tool 开发者

需要声明工具 schema、风险、副作用、超时和恢复策略。

### Persona C：本地最终用户

需要看到回答、审批高风险动作、恢复中断任务。

### Persona D：Maintainer/安全审查者

需要确定性 CI、对抗测试、证据和发布门禁。

## 5. 核心用户故事

- US-001：作为集成开发者，我能用 Fake Provider 离线测试完整多轮 tool loop。
- US-002：作为 Tool 开发者，我提交错误参数时 Runtime 在 handler 之前拒绝。
- US-003：作为用户，我能批准或拒绝 ASK 操作。
- US-004：作为用户，我能知道工具执行失败、超时或结果不确定。
- US-005：作为用户，我能恢复会话而不重复已确认成功的副作用。
- US-006：作为维护者，我能分享诊断报告而不泄露正文和密钥。
- US-007：作为维护者，我能证明发布包没有包含 `.env` 或 checkpoint。
- US-008：作为用户，我默认能看到最终回答，而安全报告单独输出。

## 6. 功能需求

### 6.1 安装、配置与版本

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| CFG-001 | P1 | 支持 Python 3.11–3.13 | 三版本 CI 全通过 | Partial |
| CFG-002 | P1 | 包版本只有一个真源 | package、diagnostics、artifact 一致 | Blocked |
| CFG-003 | P1 | API Key 仅从显式配置/环境读取 | repr、日志、doctor 不出现值 | Partial |
| CFG-004 | P1 | 环境配置解析有类型和范围校验 | 非法 timeout/max_tokens 返回 CONFIG_INVALID | Planned |
| CFG-005 | P1 | 显式传入空 env 不回退宿主环境 | `env={}` 测试通过 | Blocked |
| CFG-006 | P2 | 支持配置对象覆盖环境变量 | 优先级文档和测试明确 | Partial |

### 6.2 Provider Client

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| PROV-001 | P1 | 请求 method/url/header/body 正确 | Mock transport 测试 | Implemented |
| PROV-002 | P1 | 任意 Provider JSON 根不会使 Client 崩溃 | fuzz/property test 返回结构化错误 | Blocked |
| PROV-003 | P1 | 校验 choices/message/tool_calls shape | malformed fixtures 全部结构化失败 | Planned |
| PROV-004 | P1 | 区分 auth/rate-limit/timeout/transport/5xx | error code 测试 | Partial |
| PROV-005 | P1 | 429/5xx 可配置 retry/backoff | fake clock 测试重试次数和 delay | Planned |
| PROV-006 | P1 | 限制最大响应体 | 超限返回 PROVIDER_RESPONSE_TOO_LARGE | Planned |
| PROV-007 | P1 | Request identity 包含 provider/method/endpoint/body | canonical identity 测试 | Blocked |
| PROV-008 | P1 | SSE 支持任意 chunk boundary | split-byte 和 multiline tests | Blocked |
| PROV-009 | P1 | Stream 提供 iterator/callback 和最终聚合 | 消费者逐事件收到内容 | Blocked |
| PROV-010 | P2 | Provider adapter 可扩展 | 不修改 Runtime 可替换 adapter | Partial |

### 6.3 Runtime Loop

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| RUN-001 | P1 | 支持 text-only 完成 | 一步返回 final result | Implemented |
| RUN-002 | P1 | 支持多轮 tool call | fake provider 3 轮测试 | Partial |
| RUN-003 | P1 | 所有工具调用必须经 ToolRegistry | 无裸 handler 路径 | Blocked |
| RUN-004 | P1 | 所有状态转换可 checkpoint | 生命周期事件测试 | Planned |
| RUN-005 | P1 | max_steps 是明确预算 | 超限返回 BUDGET_STEP_EXCEEDED | Partial |
| RUN-006 | P1 | 支持 cancellation | provider/tool 执行可取消 | Planned |
| RUN-007 | P1 | 支持 token/cost/context budget | 达阈值停止并给证据 | Planned |
| RUN-008 | P1 | Tool error 返回模型或终止策略可配置 | policy tests | Partial |
| RUN-009 | P1 | 非字符串工具结果被规范化或拒绝 | JSON/object/binary tests | Blocked |
| RUN-010 | P1 | malformed Provider 不抛未处理异常 | 全部 fixture 返回 RuntimeResult | Blocked |
| RUN-011 | P2 | 支持生命周期 hook | hook 顺序稳定 | Planned |

### 6.4 Tool Contract

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| TOOL-001 | P1 | ToolSpec 声明 name/description/schema/handler | API 测试 | Planned |
| TOOL-002 | P1 | Registry 拒绝重复 tool name | 单元测试 | Planned |
| TOOL-003 | P1 | 参数在 handler 前按 JSON Schema 校验 | invalid fixtures 不调用 handler | Planned |
| TOOL-004 | P1 | Tool 声明 risk 和 side_effect | 缺失声明不能注册 | Planned |
| TOOL-005 | P1 | Tool 声明 timeout/output limit | 超限结构化失败 | Planned |
| TOOL-006 | P1 | Tool 声明 recovery policy | side-effect 工具必须配置 | Planned |
| TOOL-007 | P1 | 未知工具返回 TOOL_NOT_FOUND | handler 不执行 | Partial |
| TOOL-008 | P2 | Provider tool schema 从 ToolSpec 自动生成 | schema snapshot test | Planned |

### 6.5 Workspace Tools

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| WS-001 | P0 | read_file 不能越出工作区 | traversal/symlink tests | Partial |
| WS-002 | P0 | search 不能跟随外部 symlink | adversarial test | Blocked |
| WS-003 | P1 | read_file 有字节上限且标注截断 | UTF-8/大文件测试 | Partial |
| WS-004 | P1 | search 有文件数、字节、时间预算 | 大仓库 fixture | Planned |
| WS-005 | P1 | 二进制/权限/IO 错误结构化返回 | fixtures | Partial |
| WS-006 | P2 | `.git`、runtime state 和用户 exclude 可配置 | config tests | Partial |

### 6.6 Policy、Approval 与 Sandbox

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| SEC-001 | P1 | 非 READ 默认 DENY | 单元测试 | Implemented |
| SEC-002 | P1 | 规则优先级明确且文档化 | overlap rule tests | Partial |
| SEC-003 | P1 | ASK 有 ApprovalProvider | approve/deny/timeout tests | Blocked |
| SEC-004 | P1 | Runtime 强制所有工具走 policy | integration test | Blocked |
| SEC-005 | P1 | 命令 Gate 不宣称隔离 | 文档和类型命名一致 | Blocked |
| SEC-006 | P1 | 子进程最小环境变量 | child 无 API Key 测试 | Blocked |
| SEC-007 | P1 | 命令 timeout 杀死进程树 | child-process test | Planned |
| SEC-008 | P1 | 可插拔 SandboxAdapter | fake + local adapter tests | Planned |
| SEC-009 | P1 | 审计日志不泄露参数 secret | marker/结构化 secret tests | Partial |
| SEC-010 | P2 | 提供 Docker/Podman 参考 adapter | example integration test | Planned |

### 6.7 文件变更与回滚

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| CHG-001 | P0 | Rollback handle 不可伪造 | forged token test | Blocked |
| CHG-002 | P0 | rollback 路径重新过 sandbox | external path test | Blocked |
| CHG-003 | P1 | apply 拒绝重复路径 | duplicate fixture | Planned |
| CHG-004 | P1 | validate/write 受 workspace lock 保护 | concurrent test | Planned |
| CHG-005 | P1 | rollback 不覆盖后续外部修改 | stale rollback test | Blocked |
| CHG-006 | P1 | 文件 mode/metadata 按策略保留 | platform tests | Planned |
| CHG-007 | P1 | 文件和父目录持久化语义明确 | fsync fault-injection test | Partial |
| CHG-008 | P1 | 审计包含 changeset、路径、结果，不含正文 | evidence test | Partial |
| CHG-009 | P2 | 明确 best-effort 多文件事务语义 | 文档验收 | Blocked |

### 6.8 Session 与恢复

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| SES-001 | P1 | Checkpoint 和 Evidence schema 分离 | 类型/API 测试 | Blocked |
| SES-002 | P1 | Checkpoint 保留 Provider continuation 语义 | thinking tool-resume fixture | Blocked |
| SES-003 | P1 | Checkpoint 可选加密 at rest | key injection/roundtrip test | Planned |
| SES-004 | P1 | 原子写入并检测损坏 | crash/corrupt tests | Partial |
| SES-005 | P1 | schema migration/unsupported version 明确 | fixture tests | Partial |
| SES-006 | P1 | succeeded 副作用不重复 | resume test | Implemented |
| SES-007 | P0 | running 副作用不默认重试 | uncertain-state test | Blocked |
| SES-008 | P1 | handler missing 不导致无上下文 KeyError | TOOL_NOT_FOUND | Blocked |
| SES-009 | P1 | retry budget 和 backoff | fake clock tests | Planned |
| SES-010 | P1 | 保存 approvals、budgets、receipts | roundtrip test | Planned |

### 6.9 Evidence 与隐私

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| EVD-001 | P1 | 公开 evidence 无 API Key | leak test | Implemented/Partial |
| EVD-002 | P1 | 公开 evidence 无 prompt/response/reasoning 正文 | leak test | Implemented |
| EVD-003 | P1 | evidence 对任意 JSON 输入是 total function | property test | Blocked |
| EVD-004 | P1 | canonical JSON 稳定 | key-order test | Blocked |
| EVD-005 | P1 | 低熵敏感文本不使用可猜裸 hash | threat-model test | Planned |
| EVD-006 | P1 | evidence schema 版本化 | schema snapshot | Partial |
| EVD-007 | P1 | debug content 只能显式开启 | CLI/API test | Partial |
| EVD-008 | P1 | error 字段也经过 secret redaction | exception-secret test | Blocked |

### 6.10 Observability 与预算

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| OBS-001 | P1 | 统计 provider/tool/step latency | fake clock test | Partial |
| OBS-002 | P1 | 统计 token/cache/cost | fixture tests | Implemented/Partial |
| OBS-003 | P1 | 未知成本保持 unknown | missing-field test | Blocked |
| OBS-004 | P1 | 输入 Token 无拆分时不漏算 | provider fixture | Blocked |
| OBS-005 | P1 | 负数/非法价格拒绝 | validation test | Planned |
| OBS-006 | P1 | success/first-completion 分母只用已知值 | partial-data test | Blocked |
| OBS-007 | P1 | Runtime 可执行预算停止 | integration tests | Planned |
| OBS-008 | P2 | 输出稳定 JSON schema | snapshot | Partial |

### 6.11 CLI 与诊断

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| CLI-001 | P1 | `doctor --json` 无 Key可运行 | subprocess test | Implemented |
| CLI-002 | P1 | `run` 默认输出最终回答 | golden test | Blocked |
| CLI-003 | P1 | safe report 可用独立 `--report` 输出 | file/stdout test | Planned |
| CLI-004 | P1 | debug 明文需要明显危险开关 | help/golden test | Partial |
| CLI-005 | P1 | 退出码与 error code 对应 | subprocess matrix | Partial |
| CLI-006 | P1 | workspace 不存在时友好失败 | test | Partial |
| CLI-007 | P2 | 支持 resume session id | end-to-end test | Planned |
| DOC-001 | P1 | doctor 区分“诊断成功”和“可在线运行” | report semantics test | Partial |

### 6.12 开源与发布

| ID | P | 需求 | 验收标准 | 当前 |
| --- | --- | --- | --- | --- |
| OSS-001 | P1 | GitHub Actions 自动运行质量门禁 | 每个 PR 有 checks | Blocked |
| OSS-002 | P1 | Linux/macOS/Windows 测试 | matrix green | Planned |
| OSS-003 | P1 | Ruff + type checker | CI green | Planned |
| OSS-004 | P1 | Coverage 阈值，关键模块分支覆盖 | ≥85%，P0 路径 100% | Planned |
| OSS-005 | P1 | Secret scan | 故意 secret fixture 被拦截 | Planned |
| OSS-006 | P1 | 构件基于 allowlist/git tracked files | `.env` 不进入包 | Blocked |
| OSS-007 | P1 | 构件 digest 实际重新计算 | tampered artifact 门禁失败 | Blocked |
| OSS-008 | P1 | wheel 和 sdist 可安装 | clean env smoke | Planned |
| OSS-009 | P1 | CONTRIBUTING/CODE_OF_CONDUCT/issue templates | 文件和链接有效 | Planned |
| OSS-010 | P1 | 安全报告流程 | SECURITY 中有范围和 SLA | Partial |
| OSS-011 | P1 | README 所有能力有 PRD/测试证据 | traceability audit | Blocked |
| OSS-012 | P2 | SBOM/依赖清单 | artifact 包含 | Planned |

## 7. 非功能需求

### NFR-SEC：安全

- 模型输出视为不可信。
- 所有 tool 参数必须在 handler 前验证。
- 默认日志不能包含正文和 secret。
- 公开 Alpha 前 P0/P1 安全用例 100% 通过。
- Runtime 不得把命令分类器描述为隔离沙箱。

### NFR-REL：可靠性

- Runtime 的公开入口不因任意 JSON-compatible Provider 响应抛未处理异常。
- checkpoint 损坏必须结构化失败。
- side-effect uncertain 状态不能自动当作 pending。
- retry 必须有上限。

### NFR-PERF：性能与资源

- Workspace search 默认 ≤10,000 文件、≤100MB 扫描、≤5 秒，可配置。
- Tool output 默认 ≤100KB，可配置。
- Provider response 默认有最大字节限制。
- 每次任务有 step/token/cost/time budget。

### NFR-COMP：兼容性

- Python 3.11–3.13。
- Linux、macOS、Windows。
- 文件系统特性差异必须在测试报告标注。

### NFR-MAINT：可维护性

- 公共 API 有 type hints 和最小示例。
- 版本单一真源。
- 教学注释移到 docs。
- error code 和 schema 有兼容策略。

## 8. 产品交互要求

### 默认 CLI 输出

```text
stdout: 最终回答
stderr: 进度/警告（可关闭）
--report path.json: 安全证据
--json: 机器可读结果
--unsafe-debug-content: 明文调试，需要显式确认
```

### 审批

审批信息至少包含：

- 工具；
- 风险；
- 规范化路径/命令；
- 参数安全摘要；
- 可能副作用；
- allow once / allow session / deny。

## 9. 数据与隐私

| 数据 | 默认存储 | 可公开 | 恢复必需 |
| --- | --- | --- | --- |
| API Key | 不存 | 否 | 否 |
| Prompt/response | checkpoint 可选加密 | 否 | 是 |
| reasoning continuation | checkpoint 可选加密 | 否 | 可能是 |
| Tool arguments/results | checkpoint 可选加密 | 默认否 | 是 |
| Structural evidence | JSON | 是 | 否 |
| Usage/cost | JSON | 是 | 否 |
| Approval/receipt | checkpoint | 可脱敏摘要 | 是 |

## 10. 发布门禁

首个 Open-source Alpha 必须同时满足：

1. 所有 P0/P1 安全缺陷关闭；
2. CI 多平台、多 Python 版本全绿；
3. 测试计划中的 P0/P1 用例通过；
4. 无 active known P0/P1；
5. README 与 PRD traceability 检查通过；
6. wheel/sdist 在干净环境安装成功；
7. release artifact 通过 secret scan；
8. manifest 重新计算 digest 后匹配；
9. live API smoke 通过且无泄漏；
10. `docs/testing/test-report-*.md` 给出明确 Release/No Release 结论。

## 11. 里程碑

- M0：文档与范围冻结；
- M1：P0 安全边界修复；
- M2：ToolSpec + Runtime 生命周期闭环；
- M3：Checkpoint/Recovery 正确性；
- M4：CI、测试、发布工程；
- M5：Open-source Alpha Release Candidate。

具体迭代见 `docs/roadmap/open-source-readiness-plan.md`。
