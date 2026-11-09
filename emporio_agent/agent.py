"""Conversation loop between the customer, the model and the tools."""


class Agent:
    def reply(self, message: str) -> str:
        raise NotImplementedError
