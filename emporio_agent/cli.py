"""Terminal interface for chatting with the agent."""
import argparse
import sys

from dotenv import load_dotenv
from openai import APIError

from emporio_agent.agent import Agent
from emporio_agent.config import ROOT


def _print_tool_call(name: str, arguments: str, result: str) -> None:
    print(f"  [tool] {name}({arguments}) -> {len(result)} chars")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the Empório da Música assistant.")
    parser.add_argument("--show-tools", action="store_true", help="print each tool call")
    options = parser.parse_args()

    # Windows defaults to a legacy code page when input or output is redirected.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    load_dotenv(ROOT / ".env")
    try:
        agent = Agent(on_tool_call=_print_tool_call if options.show_tools else None)
    except ValueError as error:
        sys.exit(str(error))

    print("Empório da Música (type 'sair' to quit)")
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if message.lower() == "sair":
            break
        if not message:
            continue
        try:
            print(agent.reply(message))
        except APIError as error:
            print(f"[the model provider returned an error, please try again: {error}]")
