"""Terminal interface for chatting with the agent."""
from emporio_agent.agent import Agent


def main() -> None:
    agent = Agent()
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
        except NotImplementedError:
            print("[agent not implemented yet]")
