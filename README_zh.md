# DeepSeek Runtime

[English](README.md) | [简体中文](README_zh.md)

DeepSeek Runtime 是一个可 fork 的 Python Runtime Kernel，用于基于 DeepSeek 官方 API 构建本地 Agent。

它不是只做缓存命中率的 API wrapper。这个项目关注的是会影响本地 Agent 正确性、证据链、安全、诊断和成本可见性的 DeepSeek 物理特性。

研究脉络：

- Runtime 仓库目标：[7colorai/deepseek_runtime](https://github.com/7colorai/deepseek_runtime)
- 上层产品线：[yuanchenglu/deepseekagent](https://github.com/yuanchenglu/deepseekagent)
- Harness 研究归档：[yuanchenglu/llm-harness-agent](https://github.com/yuanchenglu/llm-harness-agent)
- DeepSeek 官方 API 文档：[api-docs.deepseek.com](https://api-docs.deepseek.com/)

## 价值矩阵

| 层级 | DeepSeek 物理特性或本地 Agent 问题 | 当前 Runtime 已提供 | 为什么不只是缓存命中率 |
| --- | --- | --- | --- |
| 原生聊天协议 | DeepSeek 暴露 OpenAI 兼容的 `/chat/completions`，并包含 V4 模型 ID、thinking 模式、工具调用、流式分片和 usage 字段。 | `DeepSeekClient.chat()`、`chat_stream()`、`models()` 和 `RuntimeSettings.from_env()`。 | Runtime 保留 DeepSeek 特有请求字段，而不是把它们藏在通用 provider shim 后面。 |
| Thinking 模式控制 | DeepSeek V4 有显式 `thinking` 和 `reasoning_effort` 控制。 | `DeepSeekRuntime.run()` 默认启用 thinking，live smoke 验证官方 endpoint 接受原生请求形态。 | 只做缓存的 Runtime 不会把推理模式控制建模为一等运行时行为。 |
| Reasoning-content 安全 | Thinking response 可能包含 `reasoning_content`；发布证据和日志不能写入这类内容。 | Evidence 只记录字段存在性、字段名、字节数和 hash，不记录原始 `reasoning_content`。 | 既保护推理内容，又能证明模型响应结构。 |
| Wire evidence | 协议实验和缓存行为依赖精确请求字节。 | 稳定 JSON wire 编码和请求 sha256 指纹。 | 维护者可以比较 Runtime 行为，而不需要保存 prompt 明文。 |
| Function tool loop | DeepSeek 工具调用响应包含函数名和 JSON argument 字符串。 | 有界工具循环、JSON 参数解析、工具结果消息和 max-step 停止。 | Agent 正确性取决于循环语义，不只是 provider 连通性。 |
| Prefix-cache 可观测性 | DeepSeek usage 可暴露 cache hit/miss token 字段。 | Diagnostics 和 observability 汇总 hit tokens、miss tokens、total tokens、成功率和估算成本。 | 缓存可见性和任务成功率、成本放在同一证据流里，而不是孤立指标。 |
| 本地安全 | 本地 Agent 需要工作区边界、权限决策、diff preview、rollback 和可恢复副作用。 | `WorkspaceSandbox`、`PermissionPolicy`、change-set rollback、`SessionState` 和确定性 safety drill。 | 这是本地 Agent 的 Runtime 基础设施，不是 API cache。 |
| 发布证据 | Fork 用户需要证明可安装、可诊断、artifact checksum 和真实 API 兼容。 | `doctor`、`release_drill.py`、`build_release_artifact.py`、`release_gate_audit.py` 和 `live_api_smoke.py`。 | Release 需要可执行证据和 redaction 检查通过才算成立。 |

## 范围

版本 `0.1.1a0` 是 Runtime Kernel Open Alpha。

包含：

- Python package distribution：`deepseek-runtime`
- Import namespace：`deepseek_runtime`
- CLI：`deepseek-runtime doctor --json` 和 `deepseek-runtime run`
- 通过 `DEEPSEEK_API_KEY` 进行真实 DeepSeek 官方 API smoke
- 本地安全、session、diagnostics、evidence 和 observability 原语

不包含：

- Hosted API service
- Desktop GUI
- Mobile app
- Enterprise policy center
- Plugin marketplace

## 安装

```bash
git clone https://github.com/7colorai/deepseek_runtime.git
cd deepseek_runtime
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
deepseek-runtime doctor --json
```

`doctor --json` 不会调用真实 DeepSeek API。它只报告本地健康状态、脱敏配置、entrypoint 可用性、workspace 可写性、session store 可写性，以及显式传入 evidence 时的摘要。

## 运行

```bash
export DEEPSEEK_API_KEY=...
deepseek-runtime run --workspace . "Summarize this repository structure."
```

默认情况下，CLI JSON 输出可以用于日志：它只输出 fingerprints、字节数、message 结构、usage 和 diagnostics，不输出 prompt 或 response 明文。只有在本地可信调试时才使用 `--include-content`。

## Python API

```python
from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools

settings = RuntimeSettings.from_env()
client = DeepSeekClient(settings)
runtime = DeepSeekRuntime(client)
tools = WorkspaceTools(".").catalog()

result = runtime.run(
    [{"role": "user", "content": "List the files in this workspace."}],
    workspace=".",
    tools=tools,
)

print(result.ok)
print(result.final_text)
print(result.to_safe_dict())
```

## Live API Smoke

```bash
export DEEPSEEK_API_KEY=...
python3 scripts/live_api_smoke.py --out live-smoke.json
```

Smoke 只写入脱敏结构化证据：

- request fingerprint
- request/response 字段摘要
- token usage
- response content hash 和字节数
- reasoning-content 是否存在、hash 和字节数
- API key、prompt、response、reasoning text 泄漏检查

## 发布验证

```bash
python3 -m unittest discover -s tests -v
deepseek-runtime doctor --json
python3 scripts/release_drill.py
python3 scripts/build_release_artifact.py --out dist --manifest dist/release-manifest.json
DEEPSEEK_API_KEY=... python3 scripts/live_api_smoke.py --out live-smoke.json
python3 scripts/release_gate_audit.py \
  --release-drill-result release-drill.json \
  --live-smoke-result live-smoke.json \
  --manifest dist/release-manifest.json
```

## 文档

- [API Reference](docs/api.md)
- [Integration Guide](docs/integration-guide.md)
- [Physical Traits](docs/physical-traits.md)
- [Known Unknowns](docs/known-unknowns.md)
- [Hosting Roadmap](docs/hosting-roadmap.md)
- [Security](SECURITY.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
