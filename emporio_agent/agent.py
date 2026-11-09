"""Conversation loop between the customer, the model and the tools."""
from collections.abc import Callable
from datetime import datetime
from typing import Any

from openai import BadRequestError

from emporio_agent.config import llm_settings
from emporio_agent.llm import create_client
from emporio_agent.policies import PolicyManual
from emporio_agent.prompts import build_system_prompt
from emporio_agent.store import Store
from emporio_agent.store_hours import closed_notice, store_now
from emporio_agent.tools import Tools

MAX_TOOL_ROUNDS = 6
MAX_HISTORY_MESSAGES = 20
MAX_MALFORMED_CALL_RETRIES = 2
TEMPERATURE = 0.2

FALLBACK_REPLY = (
    "Desculpa, não consegui concluir isso agora. Pode tentar de novo "
    "ou falar com a loja pelo (67) 3341-4444?"
)

ToolObserver = Callable[[str, str, str], None]


class Agent:
    def __init__(
        self,
        client: Any = None,
        model: str | None = None,
        tools: Tools | None = None,
        clock: Callable[[], datetime] = store_now,
        on_tool_call: ToolObserver | None = None,
    ) -> None:
        if client is None:
            settings = llm_settings()
            client = create_client(settings)
            model = settings.model
        self._client = client
        self._model = model
        self._tools = tools or Tools(Store(), PolicyManual())
        self._clock = clock
        self._on_tool_call = on_tool_call
        # Only the text of finished turns. Tool results are large and go stale, so they are
        # dropped when a turn ends, which also keeps requests within free-tier token limits.
        self._history: list[dict[str, str]] = []

    def reply(self, message: str) -> str:
        now = self._clock()
        user_message = {"role": "user", "content": message}
        system_message = {"role": "system", "content": build_system_prompt(now)}
        messages: list[Any] = [system_message, *self._history, user_message]

        text = self._run_turn(messages)
        if text is None:
            return FALLBACK_REPLY
        notice = None if self._history else closed_notice(now)
        if notice:
            text = f"{notice}\n\n{text}"
        self._remember(user_message, {"role": "assistant", "content": text})
        return text

    def _complete(self, messages: list[Any], tool_choice: str) -> Any:
        for attempts_left in range(MAX_MALFORMED_CALL_RETRIES, -1, -1):
            try:
                return self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=self._tools.schemas(),
                    tool_choice=tool_choice,
                    temperature=TEMPERATURE,
                )
            except BadRequestError as error:
                # Groq rejects a generation whose tool call does not match the schemas,
                # e.g. a misspelled tool name. Sampling again usually fixes it.
                if error.code != "tool_use_failed" or not attempts_left:
                    raise
        raise AssertionError("unreachable")

    def _run_turn(self, messages: list[Any]) -> str | None:
        for round_number in range(MAX_TOOL_ROUNDS):
            # With "auto", the model sometimes invented facts or promised to check something
            # and stopped. Forcing a first call makes it look up or say why it does not need to.
            tool_choice = "required" if round_number == 0 else "auto"
            message = self._complete(messages, tool_choice).choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip() or None
            # The raw message is sent back because Gemini attaches data to its tool calls
            # that it expects to receive again.
            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                messages.append(self._run_tool(call))
        return None

    def _run_tool(self, call: Any) -> dict[str, str]:
        name, arguments = call.function.name, call.function.arguments
        result = self._tools.execute(name, arguments)
        if self._on_tool_call:
            self._on_tool_call(name, arguments, result)
        return {"role": "tool", "tool_call_id": call.id, "content": result}

    def _remember(self, *messages: dict[str, str]) -> None:
        self._history.extend(messages)
        del self._history[:-MAX_HISTORY_MESSAGES]
