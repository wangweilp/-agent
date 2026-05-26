"""Agent Memory CLI — 交互式命令行界面。"""
import sys

from src.core.agent import CognitiveAgent


def run_cli(agent: CognitiveAgent) -> None:
    print("Agent Memory CLI — 输入消息与 Agent 对话，Ctrl+C 或输入 exit 退出")
    print("-" * 50)
    try:
        while True:
            user_input = input("\n> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("再见！")
                break
            reply = agent.run(user_input)
            print(f"\n{reply}")
    except (KeyboardInterrupt, EOFError):
        print("\n再见！")
        sys.exit(0)
