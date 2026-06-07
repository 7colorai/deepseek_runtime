from __future__ import annotations

from deepseek_runtime import DeepSeekClient, DeepSeekRuntime, RuntimeSettings, WorkspaceTools


def main() -> None:
    runtime = DeepSeekRuntime(DeepSeekClient(RuntimeSettings.from_env()))
    result = runtime.run(
        [{"role": "user", "content": "Find README.md and summarize the runtime value in two bullets."}],
        workspace=".",
        tools=WorkspaceTools(".").catalog(),
    )
    if result.ok:
        print(result.final_text)
    else:
        print(result.error_class, result.error)


if __name__ == "__main__":
    main()
