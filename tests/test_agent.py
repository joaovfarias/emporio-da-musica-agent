import json
import unittest
from datetime import datetime
from types import SimpleNamespace

from openai import BadRequestError

from emporio_agent.agent import (
    FALLBACK_REPLY,
    MAX_HISTORY_MESSAGES,
    MAX_MALFORMED_CALL_RETRIES,
    MAX_TOOL_ROUNDS,
    Agent,
)
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


def bad_request(code):
    response = SimpleNamespace(request=None, status_code=400, headers={})
    return BadRequestError("rejected", response=response, body={"code": code})


MONDAY_MORNING = datetime(2026, 11, 9, 10, tzinfo=STORE_TIMEZONE)
SUNDAY = datetime(2026, 11, 15, 10, tzinfo=STORE_TIMEZONE)


class AgentTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = Tools(Store(), PolicyManual())

    def agent(self, *script, now=MONDAY_MORNING, **options):
        client = FakeClient(*script)
        agent = Agent(client=client, model="fake", tools=self.tools, clock=lambda: now, **options)
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


class MalformedToolCallTest(AgentTestCase):
    def test_retries_when_the_provider_rejects_a_tool_call(self):
        agent, client = self.agent(bad_request("tool_use_failed"), FakeMessage("Ok."))
        self.assertEqual(agent.reply("?"), "Ok.")
        self.assertEqual(len(client.requests), 2)

    def test_stops_retrying_eventually(self):
        failures = [bad_request("tool_use_failed")] * (MAX_MALFORMED_CALL_RETRIES + 1)
        agent, client = self.agent(*failures)
        with self.assertRaises(BadRequestError):
            agent.reply("?")
        self.assertEqual(len(client.requests), MAX_MALFORMED_CALL_RETRIES + 1)

    def test_other_bad_requests_are_not_retried(self):
        agent, client = self.agent(bad_request("invalid_api_key"))
        with self.assertRaises(BadRequestError):
            agent.reply("?")
        self.assertEqual(len(client.requests), 1)


class ClosedStoreTest(AgentTestCase):
    def test_first_reply_tells_when_the_store_reopens(self):
        agent, _ = self.agent(FakeMessage("Oi!"), now=SUNDAY)
        reply = agent.reply("oi")
        self.assertIn("volta amanhã às 09:00", reply)
        self.assertTrue(reply.endswith("Oi!"))

    def test_notice_is_not_repeated(self):
        agent, _ = self.agent(FakeMessage("Oi!"), FakeMessage("Claro."), now=SUNDAY)
        agent.reply("oi")
        self.assertEqual(agent.reply("e aí?"), "Claro.")

    def test_no_notice_while_open(self):
        agent, _ = self.agent(FakeMessage("Oi!"))
        self.assertEqual(agent.reply("oi"), "Oi!")


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
        agent, client = self.agent(FakeMessage("Oi."), now=SUNDAY)
        agent.reply("oi")
        system = client.requests[0]["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("CLOSED", system["content"])
        self.assertIn("Monday, 2026-11-16 at 09:00", system["content"])


if __name__ == "__main__":
    unittest.main()
