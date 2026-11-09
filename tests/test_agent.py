import json
import unittest
from datetime import datetime
from types import SimpleNamespace

from emporio_agent.agent import FALLBACK_REPLY, MAX_HISTORY_MESSAGES, MAX_TOOL_ROUNDS, Agent
from emporio_agent.policies import PolicyManual
from emporio_agent.store import Store
from emporio_agent.store_hours import STORE_TIMEZONE
from emporio_agent.tools import Tools


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=False):
        calls = [{"id": c.id} for c in self.tool_calls or []]
        return {"role": "assistant", "content": self.content, "tool_calls": calls}


def call(call_id, name, arguments="{}"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def asks_for(*calls):
    return FakeMessage(tool_calls=list(calls))


class FakeClient:
    """Plays back scripted model messages and records every request."""

    def __init__(self, *script):
        self._script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **request):
        self.requests.append({**request, "messages": list(request["messages"])})
        message = self._script.pop(0)
        if isinstance(message, Exception):
            raise message
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


SUNDAY = datetime(2026, 11, 15, 10, tzinfo=STORE_TIMEZONE)


class AgentTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = Tools(Store(), PolicyManual())

    def agent(self, *script, **options):
        client = FakeClient(*script)
        agent = Agent(client=client, model="fake", tools=self.tools, clock=lambda: SUNDAY, **options)
        return agent, client


class ToolLoopTest(AgentTestCase):
    def test_plain_answer_uses_no_tools(self):
        agent, client = self.agent(FakeMessage("Oi!"))
        self.assertEqual(agent.reply("oi"), "Oi!")
        self.assertEqual(len(client.requests), 1)

    def test_tool_result_goes_back_to_the_model(self):
        agent, client = self.agent(
            asks_for(call("1", "get_policy", '{"topic": "hours"}')),
            FakeMessage("Abrimos às 9h."),
        )
        self.assertEqual(agent.reply("que horas abre?"), "Abrimos às 9h.")
        tool_message = client.requests[1]["messages"][-1]
        self.assertEqual(tool_message["role"], "tool")
        self.assertEqual(tool_message["tool_call_id"], "1")
        self.assertIn("09:00", tool_message["content"])

    def test_answers_every_parallel_tool_call(self):
        agent, client = self.agent(
            asks_for(
                call("1", "get_policy", '{"topic": "hours"}'),
                call("2", "get_policy", '{"topic": "payment"}'),
            ),
            FakeMessage("Pronto."),
        )
        agent.reply("horário e pagamento?")
        answered = [m["tool_call_id"] for m in client.requests[1]["messages"] if m["role"] == "tool"]
        self.assertEqual(answered, ["1", "2"])

    def test_bad_tool_call_is_reported_to_the_model(self):
        agent, client = self.agent(asks_for(call("1", "nope")), FakeMessage("Ok."))
        agent.reply("?")
        self.assertIn("error", json.loads(client.requests[1]["messages"][-1]["content"]))

    def test_gives_up_after_too_many_rounds(self):
        script = [asks_for(call(str(i), "list_promotions")) for i in range(MAX_TOOL_ROUNDS)]
        agent, client = self.agent(*script)
        self.assertEqual(agent.reply("?"), FALLBACK_REPLY)
        self.assertEqual(len(client.requests), MAX_TOOL_ROUNDS)

    def test_empty_answer_falls_back(self):
        agent, _ = self.agent(FakeMessage("  "))
        self.assertEqual(agent.reply("?"), FALLBACK_REPLY)

    def test_observer_sees_tool_calls(self):
        seen = []
        agent, _ = self.agent(
            asks_for(call("1", "list_promotions")),
            FakeMessage("Ok."),
            on_tool_call=lambda name, arguments, result: seen.append(name),
        )
        agent.reply("promoções?")
        self.assertEqual(seen, ["list_promotions"])


class HistoryTest(AgentTestCase):
    def test_next_turn_sees_previous_text_but_not_tool_results(self):
        agent, client = self.agent(
            asks_for(call("1", "list_promotions")),
            FakeMessage("Temos 4."),
            FakeMessage("Claro."),
        )
        agent.reply("promoções?")
        agent.reply("e a primeira?")
        roles = [m["role"] for m in client.requests[-1]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])

    def test_failed_turn_is_not_remembered(self):
        agent, client = self.agent(RuntimeError("provider down"), FakeMessage("Oi."))
        with self.assertRaises(RuntimeError):
            agent.reply("primeira")
        agent.reply("segunda")
        self.assertEqual([m["role"] for m in client.requests[-1]["messages"]], ["system", "user"])

    def test_history_is_bounded(self):
        turns = MAX_HISTORY_MESSAGES
        agent, client = self.agent(*[FakeMessage(str(i)) for i in range(turns)])
        for i in range(turns):
            agent.reply(str(i))
        self.assertEqual(len(client.requests[-1]["messages"]), MAX_HISTORY_MESSAGES + 2)


class SystemPromptTest(AgentTestCase):
    def test_prompt_carries_the_store_status(self):
        agent, client = self.agent(FakeMessage("Oi."))
        agent.reply("oi")
        system = client.requests[0]["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("CLOSED", system["content"])
        self.assertIn("Monday, 2026-11-16 at 09:00", system["content"])


if __name__ == "__main__":
    unittest.main()
