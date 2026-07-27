# DeepSeek Runtime 测试报告

> 报告日期：2026-07-27
> 基线：`develop@0e1e435`
> 结论：**NO RELEASE / Open-source Alpha 被阻断**

## 1. 重要声明

本报告区分三种证据：

- **Dynamic verified**：在真实测试 runner 执行并有日志；
- **Static-confirmed**：通过当前源码控制流/数据流确认；
- **Not-run**：尚无实际执行证据。

当前环境能够读取 GitHub 仓库并已将本报告提交到 `yuanchenglu/deepseek_runtime:develop`，但：

1. 无法从执行容器联网 clone GitHub；
2. 审查基线 HEAD 没有可见的 Actions workflow run；
3. 原上游仓库 `7colorai/deepseek_runtime` 的 GitHub App installation 不具备写入范围，本次改为写入用户 fork；
4. 因此不能诚实声称“现有 15 个测试已经在本次会话运行通过”。

本报告完成了完整测试范围设计、现有测试审查和静态功能验证；动态执行必须在仓库 CI 或可访问源码的 runner 补跑。

## 2. 当前测试资产

现有测试文件：

- `tests/test_client_runtime.py`
- `tests/test_security_session.py`
- `tests/test_diagnostics_observability.py`
- `tests/test_cli_and_scripts.py`

根据源码，约有 15 个测试方法，主要覆盖：

- Client request；
- safe result；
- malformed empty choices；
- reasoning-content evidence；
- basic sandbox/path/network；
- changeset apply/rollback；
- session resume；
- diagnostics/observability；
- release scripts。

### 本次实际执行

| 项目 | 数量 |
| --- | ---: |
| 现有测试定义 | 约 15 |
| 本次动态执行 | 0 |
| 可见 GitHub Actions runs | 0 |
| 静态确认缺陷 | 8 |
| P0 发布阻断 | 2 |
| P1 发布阻断 | 6 |

## 3. 静态确认结果

### FAIL-S-001：伪造 RollbackToken

- 状态：Static-confirmed
- 严重度：P0/S0
- 依据：`rollback()` 对 token 中 Path 直接 `_restore()`，未重新 sandbox/policy。
- 影响：工作区外写入或删除。
- 对应用例：TC-CHG-001、TC-CHG-002。

### FAIL-S-002：Workspace search symlink escape

- 状态：Static-confirmed
- 严重度：P0/S0
- 依据：`search()` 未对 `rglob()` 候选执行 `_path()` containment。
- 影响：读取外部文件。
- 对应用例：TC-WS-002、TC-WS-003。

### FAIL-S-003：显式空 env 被忽略

- 状态：Static-confirmed
- 严重度：P2/S2
- 依据：`env = env or os.environ`。
- 影响：测试和诊断可能读取宿主环境。
- 对应用例：TC-CFG-005。

### FAIL-S-004：Malformed Provider 可在 evidence 阶段抛异常

- 状态：Static-confirmed
- 严重度：P1/S1
- 依据：Runtime 先生成 `response_evidence()`，后验证 `choices[0].message`。
- 影响：结构化错误处理被绕过。
- 对应用例：TC-PROV-002～004、TC-RUN-010。

### FAIL-S-005：Side-effect running 状态默认重试

- 状态：Static-confirmed
- 严重度：P1/S0/S1
- 依据：`resume_tool_calls()` 仅跳过 succeeded，忽略 side_effect。
- 影响：重复转账、写入或外部操作。
- 对应用例：TC-SES-007。

### FAIL-S-006：Runtime 未强制 policy/session

- 状态：Static-confirmed
- 严重度：P1/S1
- 依据：直接调用 `active_tools[name](arguments)`。
- 影响：自定义工具绕过治理，断点恢复不成立。
- 对应用例：TC-RUN-004、TC-SEC-004。

### FAIL-S-007：发布包 denylist 可包含敏感未跟踪文件

- 状态：Static-confirmed
- 严重度：P1/S0
- 依据：递归打包工作树，仅排除有限 glob。
- 影响：`.env`、checkpoint、editor 文件进入发布包。
- 对应用例：TC-OSS-003、TC-OSS-005。

### FAIL-S-008：Manifest 不验证真实 digest

- 状态：Static-confirmed
- 严重度：P1/S1
- 依据：门禁只检查 `sha256` 字符串长度为 64。
- 影响：篡改构件仍可能通过。
- 对应用例：TC-OSS-004。

## 4. 现有测试覆盖差距

| 能力 | 现有测试 | 结论 |
| --- | --- | --- |
| Text completion | 有 | 需动态复跑 |
| Multi-tool loop | 不足 | Blocked |
| Provider arbitrary JSON | 不足 | Blocked |
| Real SSE chunking | 无 | Blocked |
| Symlink escape | 无 | P0 |
| Forged rollback token | 无 | P0 |
| Approval ASK | 无端到端 | Blocked |
| Checkpoint privacy | 无 | Blocked |
| Uncertain side effect | 无 | Blocked |
| Runtime budgets | 无 | Planned |
| Packaging secret leak | 无 | Blocked |
| Cross-platform CI | 无可见证据 | Blocked |

## 5. 功能测试判定

### Provider/Client

- 基本请求构造：代码路径存在；Dynamic not-run。
- 非 2xx 错误：部分结构化；异常分类不完整。
- 任意 JSON：Fail。
- 流式：只做结构证据，缺真正增量 API；协议边界未验证。

### Runtime

- 文本和基础工具循环：部分实现；Dynamic not-run。
- Security enforcement：Fail。
- Session checkpoint：未接入。
- Cancellation/budgets：未实现。
- Tool schema：固定 `input:string`，不满足生产要求。

### Security

- 基础 traversal：存在保护。
- Symlink search：Fail。
- Command isolation：不成立，只是 Gate。
- Rollback trust：Fail。
- Secret redaction：部分。

### Recovery

- succeeded call skip：实现存在。
- crash-after-effect：Fail。
- Provider continuation checkpoint：Fail/未接入。
- checkpoint encryption：未实现。

### Observability

- 基础汇总：实现存在。
- unknown cost：会被 0 化，Fail。
- runtime budget：未实现。

### CLI/Release

- doctor：实现存在。
- run 默认 UX：只输出摘要，Fail 产品验收。
- artifact allowlist：Fail。
- digest gate：Fail。
- CI：无可见运行。

## 6. 发布门禁结果

| Gate | 结果 |
| --- | --- |
| P0 缺陷为 0 | FAIL |
| P1 缺陷为 0 | FAIL |
| 多平台 CI | NOT RUN |
| 核心测试 100% | NOT RUN |
| 安全对抗测试 100% | FAIL/NOT IMPLEMENTED |
| Clean install wheel/sdist | NOT RUN |
| Secret scan | NOT IMPLEMENTED |
| Artifact digest verification | FAIL |
| Live API smoke | NOT RUN |
| README/PRD traceability | FAIL，现已在文档中规划 |

## 7. Release 决策

**NO RELEASE。**

当前可以继续作为：

- 内部 Alpha；
- 架构研究；
- 可信环境原型；
- 教学仓库。

当前不能宣传为：

- 生产安全沙箱；
- 可靠断点续传；
- 不会重复副作用；
- 可直接用于不可信 Agent；
- 已通过完整发布验证。

## 8. 补跑命令

代码整改并加入 CI 后，最少执行：

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/release_safety_drill.py
python scripts/release_observability_drill.py
python scripts/release_drill.py
python -m build
```

并新增：

```bash
ruff check .
pyright
coverage run -m unittest discover -s tests -v
coverage report --fail-under=85
python scripts/secret_scan.py
python scripts/verify_release_artifact.py
```

最终 CI 日志和构件哈希必须回填到下一版测试报告。
