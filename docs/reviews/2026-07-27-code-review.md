# DeepSeek Runtime 完整 Code Review

> 审查日期：2026-07-27
> 基线：`develop@0e1e435`
> 范围：`src/deepseek_runtime/`、`tests/`、`scripts/`、打包配置与公开文档
> 方法：静态源码审查、测试设计审查、发布链路审查
> 说明：本报告不把未实际执行的测试声明为通过。

## 1. 执行结论

DeepSeek Runtime 已形成清晰的 Alpha 内核骨架，适合作为教学、研究验证和可信本地环境中的二次开发基础；但它尚不是可以承载不可信 Agent、高价值副作用或多租户服务的生产级 Runtime。

当前最核心的问题不是缺少模块，而是已有模块没有形成一个不可绕过的执行闭环：

```text
Provider Client
      ↓
Runtime Loop ─────────────→ Tool Handler
      ╳                       ╳
Session / Checkpoint       Policy / Approval / Sandbox
      ╳                       ╳
Change Transaction        Evidence / Observability Hooks
```

### 成熟度评估

| 维度 | 评分 | 判断 |
| --- | ---: | --- |
| 架构分层 | 7/10 | 模块边界清晰、易读、可 fork |
| 产品完整性 | 4/10 | README 承诺高于端到端实现 |
| 正确性与鲁棒性 | 4/10 | 异常 Provider、工具输出和恢复边界不足 |
| 安全性 | 2/10 | 当前是策略原语，不是真正隔离沙箱 |
| 测试成熟度 | 3/10 | 主要覆盖 Happy Path 和少量安全检查 |
| 开源就绪度 | 4/10 | 文档友好，但 CI、治理、发布可复现性不足 |

## 2. 应保留的设计

1. 客户端 Transport 依赖注入，便于 Mock。
2. Provider、Runtime、Session、Security、Evidence、Observability 分层。
3. 非 READ 操作默认拒绝的方向正确。
4. 请求和响应证据默认不保存正文。
5. 文件变更前使用原始哈希做乐观并发检查。
6. 单文件使用同目录临时文件、`fsync()` 和 `os.replace()`。
7. Known Unknowns 主动声明非内核级沙箱、托管多租户未覆盖和流式稳定性未验证。
8. 核心代码量较小，适合建立严格测试后继续演化。

## 3. P0：发布阻断缺陷

### CR-P0-001：RollbackToken 可伪造并越过工作区边界

**位置：** `security.py` 的 `RollbackToken`、`ChangeManager.rollback()`、`_restore()`。

Token 暴露 `dict[Path, bytes | None]`，调用方可构造任意绝对路径。回滚路径未重新经过：

- `WorkspaceSandbox.resolve()`；
- PermissionPolicy；
- Token 来源和签名校验；
- 当前文件版本冲突校验。

**风险：** 可在工作区外写文件；值为 `None` 时可删除文件。

**修复要求：**

- Token 必须是不可伪造、manager-issued 的 opaque handle；
- 原始内容保存在 Manager 私有注册表或签名/加密载荷；
- rollback 重新做 sandbox containment 和 policy 决策；
- rollback 前确认当前文件仍是本 ChangeSet 写出的版本；
- 增加 forged-token、external-path、stale-rollback 测试。

### CR-P0-002：WorkspaceTools.search 可通过符号链接读取工作区外文件

**位置：** `runtime.py` 的 `WorkspaceTools.search()`。

`read_file()` 通过 `_path()` 检查 resolve 后的路径；`search()` 直接 `rglob()`、`stat()` 和 `read_text()`，没有对每个候选进行相同的 containment 检查。

**风险：** 工作区内的 symlink/junction 可以暴露外部文件。

**修复要求：**

- 默认不跟随 symlink；
- 所有候选路径在读取前必须 resolve 并检查 containment；
- 使用 `lstat()` 区分链接；
- 加入最大文件数、最大总字节数、超时预算；
- 增加 POSIX symlink 和 Windows reparse point 测试。

## 4. P1：高优先级缺陷

### CR-P1-001：Runtime 没有强制接入 Security 和 Session

`DeepSeekRuntime.run()` 直接调用 tool handler，没有统一接入：

- ToolRegistry/ToolSpec；
- JSON Schema 参数验证；
- PermissionPolicy；
- 用户审批回调；
- WorkspaceSandbox；
- ChangeManager；
- SessionStore/checkpoint；
- side-effect recovery；
- cost/context budget。

因此仓库现在是“原语集合”，不是“统一运行时执行合同”。

### CR-P1-002：Checkpoint 与公开证据使用同一脱敏模型

`SessionState.to_dict()` 会对会话状态执行 `redact()` 再落盘。

问题有两类：

1. 脱敏表只覆盖少数精确 key，完整消息、工具参数、工具结果仍可能明文保存；
2. 对 `reasoning_content` 的不可逆替换会破坏需要完整回传该字段的工具调用续接。

**必须拆分：**

- `CheckpointEnvelope`：本地可恢复，可选加密，不可公开；
- `EvidenceBundle`：不可恢复，默认脱敏，可公开。

### CR-P1-003：副作用工具可能在崩溃后重复执行

`resume_tool_calls()` 对所有非 `succeeded` 状态重新执行，`side_effect` 字段没有参与决策。

故障窗口：

```text
外部副作用成功
→ 进程在保存 succeeded 前崩溃
→ checkpoint 仍为 running
→ 恢复后重复执行
```

需要幂等键、执行 receipt、`running` 不确定态策略、重试预算及人工确认。

### CR-P1-004：命令沙箱可被解释器和包装器绕过

命令分类主要看第一个 executable：

- `bash -c "curl ..."`；
- `python -c "import socket"`；
- `env curl ...`；
- 子进程间接网络访问；
- 不完整的 Git mutating 子命令表。

同时子进程继承主进程环境，可能拿到 API Key；`cwd` 限制也不能阻止读取工作区外文件。

**结论：** 当前名称和文档应定位为 `CommandPermissionGate`，不应称为安全隔离边界。

### CR-P1-005：Evidence 生成可能先于 malformed response 检测而崩溃

Runtime 在完整校验 Provider body 前调用 `response_evidence()`。当 `choices=null`、JSON 根为数组、message/tool_call 类型错误时，证据函数可能先抛异常，绕过结构化错误返回。

要求 Provider adapter 先进行 schema normalization，再生成 evidence。

### CR-P1-006：ChangeManager 不是严格多文件原子事务

当前是逐文件 replace + 失败后补偿回滚：

- 其他进程可看到中间状态；
- validate 与 write 存在 TOCTOU；
- 无 workspace/file lock；
- 不拒绝同一 changeset 重复路径；
- 替换后可能丢失 mode/ACL/xattr；
- 没有 fsync 父目录；
- rollback 可能覆盖后续外部修改。

应改称 **best-effort transactional replacement**，除非补齐锁、冲突检测和持久化语义。

## 5. P2：中优先级问题

| ID | 问题 | 影响 |
| --- | --- | --- |
| CR-P2-001 | `wire_json()` 不排序 key | 语义相同对象可能产生不同指纹 |
| CR-P2-002 | 请求指纹不包含 method/endpoint | 空 body 请求共享指纹，证据身份不完整 |
| CR-P2-003 | `chat_stream()` 先缓存全部流 | 不是真正增量消费 API |
| CR-P2-004 | SSE parser 假设一行一个完整 JSON | 跨 chunk、多行 data 和损坏事件可能静默丢失 |
| CR-P2-005 | CLI 默认只输出回答摘要 | 用户运行 `run` 看不到实际回答 |
| CR-P2-006 | `env = env or os.environ` | 显式传入 `{}` 时仍读取宿主环境 |
| CR-P2-007 | 未知 Token 类别按 0 估算 | 成本可能显著低估 |
| CR-P2-008 | 发布包遍历工作树 denylist | `.env`、checkpoint、未跟踪敏感文件可能进入包 |
| CR-P2-009 | Manifest 只检查 SHA 长度 | 没有重新计算和比对真实构件 |
| CR-P2-010 | 版本号存在多个真源 | pyproject/package/diagnostics/scripts 易漂移 |
| CR-P2-011 | 所有工具 schema 固定为 `input:string` | 无法准确表达生产工具合同 |
| CR-P2-012 | ToolHandler 返回值类型未强制 | 非字符串结果可能在下一次请求序列化时失败 |
| CR-P2-013 | 工具异常捕获范围不一致 | TypeError、Timeout 等可能直接终止 Runtime |
| CR-P2-014 | Workspace search 无资源预算 | 大仓库可导致 CPU、IO 和延迟失控 |
| CR-P2-015 | 安全 hash 对低熵文本可被字典猜测 | hash 不能等价于隐私保护 |

## 6. 测试审查

当前测试定义约 15 个，覆盖：

- Client 请求构造；
- safe result 不包含 prompt/response；
- 空 choices；
- reasoning-content evidence；
- 基础路径逃逸和网络 deny；
- changeset apply/rollback；
- session resume；
- diagnostics；
- observability；
- release script happy path。

关键缺失：

1. 完整多轮 tool loop；
2. 未知工具、参数类型和非字符串结果；
3. symlink/junction 逃逸；
4. forged rollback token；
5. 并发修改、崩溃和冲突回滚；
6. side-effect 不确定态；
7. checkpoint-at-rest privacy；
8. SSE split chunk/multiline/malformed；
9. 429/5xx retry、取消和 timeout；
10. 上下文、输出和成本预算；
11. packaging secret leak 和 reproducible build；
12. Provider 任意 JSON shape 的 property/fuzz test。

当前 HEAD 未观察到可复现的 GitHub Actions 运行证据。

## 7. 产品承诺差距

| 对外能力 | 当前状态 | 差距 |
| --- | --- | --- |
| 安全工具执行 | Partial | Runtime 不能强制所有工具走 policy/sandbox |
| 会话记忆 | Partial | Session 原语未接入运行循环 |
| 断点续传 | Blocked | 副作用重复执行和 reasoning checkpoint 冲突 |
| 回滚 | Blocked | Token 信任和冲突安全不足 |
| 成本控制 | Partial | 有报表，无预算和停止策略 |
| Streaming | Partial | 有结构解析，无增量输出消费者 |
| 证据隐私 | Partial | 公开结果较安全，checkpoint 与低熵 hash 风险未解 |
| 开箱即用 | Partial | CLI 默认不返回可读最终回答 |

## 8. 代码维护性

### 过量教学注释

源码和测试包含大量逐行 Python 基础语法解释，降低控制流和不变量的可见性，部分注释与真实参数语义矛盾。

建议：

- 教学内容移入 `docs/tutorial/`；
- 源码只保留威胁模型、设计决策和非显然约束；
- 测试通过名称、Arrange/Act/Assert 结构表达意图。

### 版本与 Schema 治理

需要：

- 单一版本源；
- checkpoint/evidence/diagnostics schema 分别版本化；
- 明确迁移策略；
- 公共 API 稳定等级和 deprecation policy。

## 9. 审查结论

下一阶段不应横向增加新功能。唯一合理的里程碑是：

> **Open-source Alpha Hardening：让现有承诺真实、可测试、不可绕过。**

优先顺序：

1. 修复 rollback 和 symlink P0；
2. 分离 checkpoint/evidence；
3. 建立 ToolSpec/ToolRegistry；
4. 把 policy、approval、session、evidence 接入统一 runtime lifecycle；
5. 建立 CI、对抗测试和可复现发布；
6. 达到发布门禁后再扩大宣传。
