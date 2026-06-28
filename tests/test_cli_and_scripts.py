# =============================================================================
# test_cli_and_scripts.py — DeepSeek Runtime CLI 与脚本测试
# =============================================================================
# ❓ 问：这个文件测试什么内容？
# 💡 答：测试 DeepSeek Runtime 的命令行界面（CLI）和发布脚本（release scripts）。
#    CLI 是用户通过终端命令行与 DeepSeek Runtime 交互的方式，
#    发布脚本用于自动化构建、测试和发布新版本。
#    这些测试确保命令行工具能正确运行、发布流程能顺利完成。
#
# 论文引用：llm-harness-agent 论文 B1: ReAct 提出了 Agent 与外部工具交互的循环范式，
# CLI 就是用户与 Agent 系统交互的"工具"之一。
# 参考 A1: Agent Harness Survey — CLI 测试是 Agent 系统部署流水线的关键环节。
# =============================================================================

from __future__ import annotations
# ❓ 问：这个导入有什么用？
# 💡 答：from __future__ import annotations 让 Python 将类型注解视为字符串，
#    而不是运行时求值的表达式。这样一来，使用更高级的语法（如 dict[str, str]）
#    也能在旧版 Python 中运行，同时避免循环导入的问题。

import json
# ❓ 问：为什么需要 json 模块？
# 💡 答：CLI 的 doctor 命令可以输出 JSON 格式的诊断报告，
#    发布脚本的输出也是 JSON 格式。我们需要 json 模块来解析这些 JSON 数据，
#    以便验证输出内容是否正确。

import os
# ❓ 问：os 模块用来做什么？
# 💡 答：os（操作系统）模块提供了与操作系统交互的功能。
#    在本测试中，我们用 os.environ 来获取当前环境变量，
#    然后构造子进程的环境变量（比如设置 PYTHONPATH）。

import subprocess
# ❓ 问：subprocess 是什么？
# 💡 答：subprocess 模块允许 Python 启动新的进程，并与之通信。
#    简单说，它让测试代码可以"在终端中运行命令"并获取输出结果。
#    本测试用 subprocess.run() 来运行 deepseek-runtime CLI 命令和发布脚本。
#    论文参考 A1: Agent Harness Survey — 子进程测试是验证 CLI 工具的主要方法。

import sys
# ❓ 问：sys 模块用来做什么？
# 💡 答：sys 模块提供了与 Python 解释器交互的功能。
#    本测试中使用 sys.executable 获取当前 Python 解释器的路径，
#    确保子进程使用和测试相同的 Python 版本。

import tempfile
# ❓ 问：tempfile 是做什么的？
# 💡 答：tempfile 模块用于创建临时文件和目录。
#    测试中，我们不想把生成的发布文件散落在项目目录中，
#    所以用 TemporaryDirectory() 创建一个临时目录，测试结束后自动清理。
#    就像用"临时草稿纸"画完就扔掉，不会弄脏办公桌。

import unittest
# ❓ 问：unittest 是什么？
# 💡 答：Python 内置的单元测试框架。它让开发者可以编写测试用例，
#    用标准化的方式验证代码功能。每个 test_ 开头的方法就是一个测试用例。

from pathlib import Path
# ❓ 问：Path 是做什么的？
# 💡 答：pathlib.Path 是 Python 中处理文件路径的现代方式。
#    它比字符串路径更安全、更直观，提供了 read_text()、write_text() 等便利方法。


ROOT = Path(__file__).resolve().parents[1]
# ❓ 问：ROOT 是什么路径？
# 💡 答：ROOT 是项目的根目录路径。
#    Path(__file__) 获取当前文件的路径，
#    .resolve() 将相对路径转为绝对路径（如 /Users/bluth/Code/deepseek_runtime/tests/test_cli_and_scripts.py），
#    .parents[1] 表示"父目录的父目录"——从 tests/ 向上两级，就是项目根目录。
#    效果：ROOT = /Users/bluth/Code/deepseek_runtime/

SRC = ROOT / "src"
# ❓ 问：SRC 是什么路径？
# 💡 答：SRC 是源代码目录，即项目根目录下的 src/ 文件夹。
#    ROOT / "src" 使用 Path 对象的 / 运算符拼接路径。
#    这样运行子进程时，Python 可以找到 deepseek_runtime 包。


class CliAndScriptsTests(unittest.TestCase):
    # ❓ 问：这个类包含哪些测试？
    # 💡 答：CliAndScriptsTests 测试类包含三个测试方法：
    #    1) test_cli_doctor_json — 测试 CLI 的 doctor 命令是否能输出正确的 JSON 诊断报告
    #    2) test_release_scripts_without_live_api — 测试发布脚本能否在没有真实 API 的情况下运行
    #    3) test_release_gate_audit_with_fixture_live_smoke — 测试发布审计脚本是否正常工作
    #    PM 理解：就像检查"发布流水线"的每个环节是否顺畅。

    def _env(self) -> dict[str, str]:
        # ❓ 问：_env 方法的作用是什么？
        # 💡 答：这是一个辅助方法（以下划线开头表示"内部使用"），
        #    它创建一个环境变量字典，供子进程使用。
        #    关键是设置 PYTHONPATH 环境变量，让子进程能够找到项目的 Python 模块。
        #    论文参考 A1: Agent Harness Survey — 测试环境的一致性对 Agent 系统至关重要。

        env = dict(os.environ)
        # ❓ 问：为什么要复制当前环境变量？
        # 💡 答：先复制当前进程的所有环境变量（os.environ），
        #    然后在此基础上修改。这样子进程既能继承父进程的环境，
        #    又能获得我们自定义的配置（如 PYTHONPATH）。

        env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        # ❓ 问：这行设置 PYTHONPATH 的逻辑是什么？
        # 💡 答：把 SRC（src/ 目录）添加到 PYTHONPATH 环境变量。
        #    PYTHONPATH 告诉 Python 解释器从哪里搜索模块。
        #    这里的逻辑是：
        #    - 如果已有 PYTHONPATH，就在前面加上 SRC + 路径分隔符（:）
        #    - 如果没有 PYTHONPATH，就直接设为 SRC
        #    这样子进程就能导入 deepseek_runtime 包了。

        return env
        # ❓ 问：返回这个字典给谁用？
        # 💡 答：返回给 subprocess.run() 的 env 参数，
        #    让子进程使用这个自定义的环境变量。

    def test_cli_doctor_json(self) -> None:
        # ❓ 问：这个测试验证什么？
        # 💡 答：测试 "deepseek-runtime doctor --json" 命令能否正常执行并输出有效的 JSON。
        #    doctor 命令类似于"体检报告"，会检查项目配置、环境变量等是否正常。
        #    --json 表示以 JSON 格式输出，便于程序解析。
        #    论文参考 B7: AgentBench — CLI 的诊断功能是 Agent 系统可维护性的重要指标。

        completed = subprocess.run(
            # ❓ 问：subprocess.run() 在做什么？
            # 💡 答：运行一个子进程并等待它完成。
            #    返回一个 CompletedProcess 对象，包含返回码、标准输出、标准错误等信息。

            [sys.executable, "-m", "deepseek_runtime.cli", "doctor", "--json", "--workspace", str(ROOT)],
            # ❓ 问：这个命令列表是什么意思？
            # 💡 答：相当于在终端执行：
            #    python3 -m deepseek_runtime.cli doctor --json --workspace /path/to/project
            #    - sys.executable: 当前 Python 解释器的路径（如 /usr/bin/python3）
            #    - "-m": 运行一个模块（module）
            #    - "deepseek_runtime.cli": 要运行的模块名（CLI 入口）
            #    - "doctor": CLI 的子命令
            #    - "--json": 输出 JSON 格式
            #    - "--workspace": 指定工作区路径
            #    - str(ROOT): 项目根目录作为工作区

            cwd=ROOT,
            # ❓ 问：cwd 是什么？
            # 💡 答：cwd（Current Working Directory）指定子进程的工作目录。
            #    设为 ROOT（项目根目录），这样脚本就能正确找到项目中的文件。

            env=self._env(),
            # ❓ 问：env 参数传入了什么？
            # 💡 答：调用 self._env() 获取自定义环境变量（包含 PYTHONPATH），
            #    确保子进程能导入 deepseek_runtime 包。

            text=True,
            # ❓ 问：text=True 的作用？
            # 💡 答：让子进程的输出以文本（字符串）形式返回，而不是字节（bytes）。
            #    这样 stdout 和 stderr 就是 str 类型，便于解析。

            capture_output=True,
            # ❓ 问：capture_output=True 的作用？
            # 💡 答：捕获子进程的标准输出（stdout）和标准错误（stderr），
            #    不打印到终端。测试代码可以通过 completed.stdout 和 completed.stderr 访问。

            check=False,
            # ❓ 问：check=False 是什么意思？
            # 💡 答：即使子进程返回非零退出码（表示出错），也不抛出异常。
            #    我们手动检查 completed.returncode 并记录 stderr，而不是让 subprocess.run() 自动抛异常。
            #    这样测试可以更优雅地报告错误详情。
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        # ❓ 问：为什么检查 returncode 是否为 0？
        # 💡 答：Unix/Linux 系统中，进程退出码 0 表示成功，非 0 表示出错。
        #    如果 returncode != 0，测试失败，并显示标准错误输出（stderr）作为失败信息。

        bundle = json.loads(completed.stdout)
        # ❓ 问：json.loads() 在做什么？
        # 💡 答：把 completed.stdout（标准输出的字符串）解析为 Python 字典。
        #    doctor 命令的输出是 JSON 格式，所以可以用 json.loads() 解析。

        self.assertIn("checks", bundle)
        # ❓ 问：为什么检查 "checks" 键？
        # 💡 答：验证诊断报告包含 "checks"（检查项）字段。
        #    doctor 命令会运行多项检查（如 API 密钥是否存在、网络是否可达等），
        #    结果汇总在 "checks" 中。如果这个字段缺失，说明输出格式不对。

        self.assertEqual(bundle["config_summary"]["deepseek_api_key"], "absent")
        # ❓ 问：为什么 API 密钥应该是 "absent"？
        # 💡 答：在测试环境中，我们没有设置真正的 DeepSeek API 密钥，
        #    所以诊断报告应该显示 API 密钥状态为 "absent"（缺失）。
        #    这是预期行为——测试环境本来就不应该有真实密钥。

    def test_release_scripts_without_live_api(self) -> None:
        # ❓ 问：这个测试验证什么？
        # 💡 答：测试发布相关的脚本能否在没有真实 API 密钥的情况下正常运行。
        #    发布流程包括：发布演练（release_drill.py）和构建发布包（build_release_artifact.py）。
        #    这个测试确保即使没有网络连接，这些脚本也能执行基本的验证和构建工作。
        #    论文参考 A1: Agent Harness Survey — CI/CD 流水线测试是 Agent 系统交付质量的保障。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：with 语句和 TemporaryDirectory 是什么意思？
            # 💡 答：这是 Python 的"上下文管理器"（context manager）语法。
            #    tempfile.TemporaryDirectory() 创建一个临时目录，
            #    with 块结束时自动删除该目录及其所有内容。
            #    就像借用了一张"临时工作台"，用完后自动清理干净。

            out = Path(directory)
            # ❓ 问：out 是什么？
            # 💡 答：把临时目录的路径包装成 Path 对象。
            #    这样可以用 out / "release-drill.json" 的方式拼接路径。

            release = subprocess.run(
                [sys.executable, "scripts/release_drill.py", "--skip-tests", "--out", str(out / "release-drill.json")],
                # ❓ 问：这个命令在做什么？
                # 💡 答：运行发布演练脚本：
                #    - "scripts/release_drill.py": 发布演练脚本路径
                #    - "--skip-tests": 跳过测试（因为测试环境没有 API 密钥）
                #    - "--out": 指定输出文件路径
                #    - str(out / "release-drill.json"): 输出到临时目录中的 release-drill.json

                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(release.returncode, 0, release.stderr)
            # ❓ 问：验证发布演练是否成功？
            # 💡 答：检查脚本退出码是否为 0（成功）。
            #    如果失败，completed.stderr 会显示详细的错误信息。

            artifact = subprocess.run(
                [sys.executable, "scripts/build_release_artifact.py", "--out", str(out / "dist"), "--manifest", str(out / "manifest.json")],
                # ❓ 问：这个命令在做什么？
                # 💡 答：运行构建发布包的脚本：
                #    - "scripts/build_release_artifact.py": 构建发布包的脚本
                #    - "--out": 输出目录（dist 子目录）
                #    - "--manifest": 输出清单文件路径（manifest.json）
                #    这个脚本会生成一个发布包和一个包含校验信息的清单文件。

                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(artifact.returncode, 0, artifact.stderr)
            # ❓ 问：验证构建是否成功？
            # 💡 答：再次检查退出码为 0，否则输出错误信息。

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            # ❓ 问：manifest 加载了什么内容？
            # 💡 答：读取临时目录中的 manifest.json 文件，解析为 Python 字典。
            #    这个清单文件包含了构建的发布包信息，如文件名、SHA256 校验值等。

            self.assertTrue(manifest["success"])
            # ❓ 问：检查 manifest["success"] 为什么是 True？
            # 💡 答：验证清单文件声称构建成功。
            #    如果脚本执行成功了但 manifest.json 中的 success 为 False，
            #    说明脚本内部有逻辑错误。

            self.assertEqual(len(manifest["artifacts"][0]["sha256"]), 64)
            # ❓ 问：SHA256 长度为什么是 64？
            # 💡 答：SHA256 是一种加密哈希算法，生成的十六进制字符串固定为 64 个字符。
            #    这行验证：发布的第一个物件的 SHA256 校验值长度确实是 64。
            #    如果长度不对，说明校验值计算有误或者格式异常。
            #    校验值的作用：确保下载的文件没有被篡改过。

    def test_release_gate_audit_with_fixture_live_smoke(self) -> None:
        # ❓ 问：这个测试验证什么发布环节？
        # 💡 答：测试"发布门禁审计"脚本（release_gate_audit.py）的功能。
        #    这个脚本会读取之前步骤的输出（发布演练结果、在线烟雾测试结果、构建清单），
        #    然后综合评估是否满足发布条件。测试使用"夹具数据"（fixture）
        #    来模拟这些输入，不依赖真实的 API 调用。
        #    论文参考 A1: Agent Harness Survey — 发布门禁（Release Gate）是 Agent 系统质量保障的最后一道防线。

        with tempfile.TemporaryDirectory() as directory:
            # ❓ 问：为什么又用临时目录？
            # 💡 答：创建一个干净的临时工作区，用于放置模拟的输入文件和输出文件。
            #    所有文件在 with 块结束时自动删除。

            out = Path(directory)
            release = out / "release.json"
            live = out / "live.json"
            manifest = out / "manifest.json"
            # ❓ 问：这三个路径分别代表什么？
            # 💡 答：
            #    - release: 模拟的发布演练结果文件
            #    - live: 模拟的在线烟雾测试结果文件
            #    - manifest: 模拟的构建清单文件
            #    这些都是"夹具"（fixture）——预制的测试数据。

            release.write_text(json.dumps({"success": True}), encoding="utf-8")
            # ❓ 问：写入什么内容到 release.json？
            # 💡 答：写入一个表示发布演练成功的 JSON 对象 {"success": True}。
            #    在真实场景中，这个文件由 release_drill.py 生成。

            live.write_text(json.dumps({"success": True, "provider_status": 200, "leak_checks": {"api_key_absent": True, "prompt_absent": True, "response_content_absent": True, "reasoning_content_absent": True}}), encoding="utf-8")
            # ❓ 问：live.json 中的这些字段是什么意思？
            # 💡 答：这是一个模拟的在线烟雾测试成功结果：
            #    - success: True — 烟雾测试通过
            #    - provider_status: 200 — AI 提供商返回正常
            #    - leak_checks: 安全泄漏检查结果
            #      - api_key_absent: API 密钥未泄露
            #      - prompt_absent: 提示词未泄露
            #      - response_content_absent: 响应内容未泄露
            #      - reasoning_content_absent: 推理内容未泄露
            #    所有这些检查都通过，说明安全脱敏机制有效。
            #    论文参考 A1: Agent Harness Survey — 泄漏检查是 Agent 安全审计的核心环节。

            manifest.write_text(json.dumps({"artifacts": [{"sha256": "a" * 64}]}), encoding="utf-8")
            # ❓ 问：manifest.json 写了什么？
            # 💡 答：写入一个模拟的构建清单，包含一个构建产物（artifact），
            #    其 SHA256 校验值为 64 个 "a"（在真实场景中是一个真正的 64 位十六进制哈希值）。

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/release_gate_audit.py",
                    "--release-drill-result",
                    str(release),
                    "--live-smoke-result",
                    str(live),
                    "--manifest",
                    str(manifest),
                    "--out",
                    str(out / "audit.json"),
                ],
                # ❓ 问：这个命令的每个参数是什么意思？
                # 💡 答：运行发布门禁审计脚本，传入以下参数：
                #    - "--release-drill-result": 发布演练结果文件路径
                #    - "--live-smoke-result": 在线烟雾测试结果文件路径
                #    - "--manifest": 构建清单文件路径
                #    - "--out": 审计报告输出路径（audit.json）
                #    脚本会分析这些输入，判断是否满足发布条件。

                cwd=ROOT,
                env=self._env(),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            # ❓ 问：验证什么？
            # 💡 答：确认审计脚本成功执行（返回码为 0）。
            #    如果审计发现不满足发布条件，脚本可能返回非零退出码。

            self.assertTrue(json.loads(completed.stdout)["success"])
            # ❓ 问：检查审计结果的什么字段？
            # 💡 答：解析审计脚本的标准输出 JSON，验证其中的 "success" 字段为 True。
            #    因为我们的夹具数据都是"通过"状态，所以审计应该也通过。


if __name__ == "__main__":
    # ❓ 问：__name__ == "__main__" 的作用？
    # 💡 答：当直接运行本文件时（python3 test_cli_and_scripts.py），
    #    __name__ 被设为 "__main__"，因此会执行 unittest.main()。
    #    当其他模块导入本文件时，不会自动运行测试。

    unittest.main()
    # ❓ 问：unittest.main() 的执行效果？
    # 💡 答：自动发现并运行 CliAndScriptsTests 中的所有测试方法，
    #    在终端输出测试结果。每个通过的测试显示一个点（.），
    #    失败的显示 F，错误的显示 E。
