# ❓ 这个文件是做什么的？为什么它几乎是空的？
# 💡 __init__.py 是 Python 包的"身份证"——它告诉 Python 解释器：
#    "这个目录下的代码是一个包（package），你可以用 import 导入它。"
#    文件本身可以完全为空，只要存在这个文件名，目录就能被当作包识别。
#    这里仅有一行文档字符串（docstring），说明这个包的用途：
#    "本地发布辅助脚本，用于测试和源码检出场景。"
# 参考 llm-harness-agent 论文 A1 (Agent Harness Survey) 中对 CI/CD 管线的讨论，
# 这些脚本构成了发布验证流水线（release validation pipeline）的一部分，
# 确保每次发布前都经过自动化的、可重复的质量检查。
"""Local release helper scripts for tests and source checkouts."""
