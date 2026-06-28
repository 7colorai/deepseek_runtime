# =============================================================================
# test_diagnostics_observability.py — 诊断与可观测性测试
# =============================================================================
# ❓ 问：这个文件测试什么？
# 💡 答：测试 DeepSeek Runtime 的"诊断"（Diagnostics）和"可观测性"（Observability）功能。
#    诊断功能用来检查系统配置和环境是否正常，
#    可观测性功能用来追踪 AI 调用的性能、成本和缓存命中率等指标。
#    这两者都是让系统"可见"和"可理解"的关键能力。
#
# 论文引用：llm-harness-agent 论文 A1: Agent Harness Survey — 可观测性是 Agent 系统生产运维的核心能力，
# 决定了是否能在不透明的大模型调用中发现问题和优化性能。
# 参考 B7: AgentBench — Agent 系统的性能监控指标（如成本、延迟、缓存命中率）是基准测试的重要组成部分。
# =============================================================================

from __future__ import annotations
# ❓ 问：这个导入的用途？
# 💡 答：启用 Python 的"未来注解"特性，让类型注解在运行时不被求值，
#    从而避免潜在的性能开销和循环导入问题。

import tempfile
# ❓ 问：为什么需要 tempfile？
# 💡 答：诊断测试需要写入文件（比如诊断报告），
#    使用临时目录可以避免污染项目文件夹，测试结束后自动清理。

import unittest
# ❓ 问：unittest 的作用？
# 💡 答：Python 内置的单元测试框架，用于编写和运行测试用例。

from pathlib import Path
# ❓ 问：Path 的用途？
# 💡 答：pathlib.Path 提供了面向对象的文件路径操作方式，
#    比字符串路径更安全、更可读。

from deepseek_runtime.diagnostics import build_diagnostics
# ❓ 问：build_diagnostics 是什么？
# 💡 答：从 deepseek_runtime.diagnostics 模块导入的"构建诊断报告"函数。
#    这个函数会检查运行环境——Python 版本、配置文件、API 密钥设置等——然后返回一份诊断报告。
#    PM 理解：就像体检中心的一套检查流程，最后出一份体检报告。
#    论文参考 A1: Agent Harness Survey — 系统诊断是 Agent 框架运维能力的基础。

from scripts.release_observability_drill import run_observability_drill
# ❓ 问：run_observability_drill 是什么？
# 💡 答：从发布脚本中导入的"运行可观测性演练"函数。
#    这个函数会模拟执行几组 AI 调用任务，收集延迟、Token 用量、
#    缓存命中率和预估成本等指标，帮助开发团队了解系统的实际运行状况。
#    论文参考 B7: AgentBench — 可观测性指标是评估 Agent 系统实际性能的数据基础。


class DiagnosticsObservabilityTests(unittest.TestCase):
    # ❓ 问：这个测试类包含哪些测试？
    # 💡 答：两个测试方法：
    #    1) test_diagnostics_are_redacted_and_do_not_require_live_api
    #       — 验证诊断报告能脱敏敏感信息，且不需要真实的 API 密钥
    #    2) test_observability_drill_exposes_route_cache_usage_cost
    #       — 验证可观测性演练能正确暴露路由、缓存使用量和成本信息

    def test_diagnostics_are_redacted_and_do_not_require_live_api(self) -> None:
        # ❓ 问：这个测试具体验证什么？
        # 💡 答：验证两个关键特性：
        #    1）诊断功能不需要真实的 API 密钥也能运行（离线可用）
        #    2）诊断报告中的 API 密钥信息会被自动隐藏（脱敏）
        #    这两个特性让诊断工具既安全又易用——任何人都能运行它，而不用担心泄露密钥。
        #    论文参考 A1: Agent Harness Survey — Agent 系统的安全诊断需要实现"默认安全"（Security by Default）。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：为什么用临时目录？
            # 💡 答：build_diagnostics 需要一个目录来存放诊断过程中产生的临时文件。
            #    TemporaryDirectory 会在 with 块结束时自动清理。

            bundle = build_diagnostics(Path(directory), env={})
            # ❓ 问：build_diagnostics() 的两个参数是什么？
            # 💡 答：
            #    1) Path(directory) — 临时目录路径，用于存储诊断过程中的文件
            #    2) env={} — 传入空的环境变量字典
            #    注意 env 是空字典！这意味着即使你的电脑上有 DEEPSEEK_API_KEY 环境变量，
            #    诊断函数也看不到它。这是为了测试"无 API 密钥"场景。

        self.assertTrue(bundle["ok"])
        # ❓ 问：bundle["ok"] 应该是什么？
        # 💡 答：bundle 是诊断报告字典，包含多个字段。
        #    bundle["ok"] 是总体健康状态——即使没有 API 密钥，
        #    诊断本身应该成功运行并报告"系统基本正常，但缺少 API 密钥"。
        #    如果这里返回 False，说明诊断功能本身有 bug。

        self.assertEqual(bundle["config_summary"]["deepseek_api_key"], "absent")
        # ❓ 问：为什么 API 密钥状态是 "absent"？
        # 💡 答：因为我们传入了空的环境变量（env={}），
        #    诊断函数无法找到 API 密钥，所以报告为 "absent"（缺失）。
        #    这是正确的行为——诊断报告诚实地反映了实际情况。

        self.assertIn("api_key_absent", bundle["warnings"])
        # ❓ 问：bundle["warnings"] 是什么？
        # 💡 答：诊断报告的 warnings（警告）列表，列出了系统存在的问题。
        #    这里检查警告列表中是否包含 "api_key_absent"（API 密钥缺失）。
        #    即使没有密钥，诊断也不应该崩溃，而是发出警告并继续完成其他检查。
        #    这是"优雅降级"的设计理念——部分功能不可用时，系统仍能提供有价值的信息。

    def test_observability_drill_exposes_route_cache_usage_cost(self) -> None:
        # ❓ 问：这个测试验证什么？
        # 💡 答：验证可观测性演练能否正确报告以下关键指标：
        #    - route（路由）：请求被路由到了哪个模型或 API 端点
        #    - cache usage（缓存使用量）：提示词缓存命中了多少 Token
        #    - cost（成本）：这次调用预估花费了多少美元
        #    这些指标对于 AI 系统的成本控制和性能优化至关重要。
        #    论文参考 B7: AgentBench — Agent 系统的成本效率是评估其实际可用性的关键维度。
        #    参考 A1: Agent Harness Survey — 可观测性工具链应该暴露这些生产级指标。

        result = run_observability_drill()
        # ❓ 问：run_observability_drill() 做了什么？
        # 💡 答：执行可观测性演练，它会：
        #    1) 模拟几组 AI 对话场景（发送几条用户消息）
        #    2) 记录每次调用的延迟、Token 用量、缓存命中情况
        #    3) 计算预估成本
        #    4) 返回一个包含所有指标的汇总报告

        self.assertTrue(result["success"])
        # ❓ 问：验证什么？
        # 💡 答：确认演练报告中的 success 字段为 True。
        #    如果演练过程中出现任何错误（如 API 调用失败），success 应为 False。

        summary = result["summary"]
        # ❓ 问：summary 包含什么？
        # 💡 答：从报告中提取 summary（汇总）部分，包含任务数量、使用的模型、
        #    缓存命中量、成本等聚合指标。

        self.assertEqual(summary["task_count"], 3)
        # ❓ 问：为什么 task_count 应该是 3？
        # 💡 答：可观测性演练设计了 3 个模拟任务（对话场景）。
        #    如果 task_count 不等于 3，说明有些任务没有被执行，
        #    或者执行过程中被跳过/失败了。

        self.assertIn("deepseek-v4-flash", summary["models"])
        # ❓ 问：检查 models 字段的意义？
        # 💡 答：确认演练使用的模型列表中包含 "deepseek-v4-flash"。
        #    这验证了演练正确配置了使用的 AI 模型。

        self.assertGreater(summary["prompt_cache_hit_tokens"], 0)
        # ❓ 问：prompt_cache_hit_tokens 是什么？
        # 💡 答：提示词缓存命中的 Token 数量。当多个请求使用相似的提示词前缀时，
        #    AI 提供商可以缓存处理结果，后续请求直接使用缓存，
        #    既加快速度又降低成本。
        #    self.assertGreater(x, 0) 检查这个值是否大于 0——意味着缓存确实被命中了。
        #    PM 理解：就像用同一种模板发快递，快递公司记住了你的地址，
        #    下次就不用重新填写了，更快更省钱。

        self.assertGreater(summary["estimated_cost_usd"], 0)
        # ❓ 问：estimated_cost_usd 是什么？
        # 💡 答：预估的总成本（美元）。所有模拟调用的总花费。
        #    大于 0 说明演练确实产生了可计量的 API 调用成本。
        #    这就是"可观测性"的价值——让团队知道每次运行花了多少钱。


if __name__ == "__main__":
    # ❓ 问：这个条件判断的含义？
    # 💡 答：当直接运行本文件时执行 unittest.main()；
    #    当被其他文件导入时不自动运行测试。

    unittest.main()
    # ❓ 问：unittest.main() 的效果？
    # 💡 答：自动发现并运行当前模块中所有以 test_ 开头的方法。
