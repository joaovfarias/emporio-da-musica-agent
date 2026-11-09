import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from emporio_agent.policies import PolicyManual
from emporio_agent.store import AVAILABLE, Store
from emporio_agent.store_hours import STORE_TIMEZONE
from emporio_agent.tickets import TicketLog
from emporio_agent.tools import ORDER_NOT_VERIFIED, Tools


class ToolsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()
        cls.tools = Tools(cls.store, PolicyManual())


class SearchProductsTest(ToolsTestCase):
    def test_finds_price_of_a_named_product(self):
        result = self.tools.search_products(query="Takamine GD20")
        self.assertEqual(result["total_found"], 1)
        pricing = result["products"][0]["pricing"]
        self.assertEqual(pricing["current_price"], 2199.0)
        self.assertEqual(pricing["pix_price"], 2089.05)

    def test_summary_spells_out_regular_price_terms(self):
        pricing = self.tools.search_products(query="Takamine GD20")["products"][0]["pricing"]
        self.assertEqual(
            pricing["summary"],
            "R$ 2.199,00 (em até 12x de R$ 183,25 sem juros), ou R$ 2.089,05 no PIX.",
        )

    def test_summary_spells_out_promotion_terms(self):
        product = self.store.products[127]
        pricing = self.tools.search_products(query=product.name)["products"][0]["pricing"]
        self.assertIn("(10% de desconto)", pricing["summary"])
        self.assertIn("Sem desconto adicional no PIX", pricing["summary"])

    def test_filters_available_products_by_category_and_price(self):
        result = self.tools.search_products(category="Violões", max_price=1000)
        self.assertGreater(result["total_found"], 0)
        for product in result["products"]:
            self.assertEqual(product["availability"], AVAILABLE)
            self.assertLessEqual(product["pricing"]["current_price"], 1000)

    def test_price_limit_uses_the_promotional_price(self):
        promoted = self.store.products[94]
        discounted = float(promoted.list_price) * 0.92
        result = self.tools.search_products(query=promoted.name, max_price=discounted + 1)
        self.assertEqual(result["total_found"], 1)

    def test_promotion_shows_original_price_and_percent(self):
        result = self.tools.search_products(query=self.store.products[127].name)
        pricing = result["products"][0]["pricing"]
        self.assertEqual(pricing["discount_percent"], 10)
        self.assertEqual(pricing["original_price"], float(self.store.products[127].list_price))
        self.assertFalse(pricing["pix_discount_applies"])
        self.assertNotIn("pix_price", pricing)

    def test_discontinued_product_is_reported_without_price_or_stock(self):
        result = self.tools.search_products(query="Ibanez Bass 2X")
        product = result["products"][0]
        self.assertEqual(product["availability"], "discontinued")
        self.assertNotIn("stock", product)
        self.assertNotIn("pricing", product)

    def test_unavailable_product_comes_with_available_alternatives(self):
        result = self.tools.search_products(query="Giannini GF-3D")
        self.assertEqual(result["products"][0]["availability"], "out_of_stock")
        self.assertTrue(result["alternatives"])
        for alternative in result["alternatives"]:
            self.assertEqual(alternative["availability"], AVAILABLE)

    def test_browsing_hides_unavailable_products(self):
        ids = {p["id"] for p in self.tools.search_products(category="Baixos")["products"]}
        self.assertNotIn(136, ids)

    def test_results_are_limited_but_total_is_reported(self):
        result = self.tools.search_products(category="Violões")
        self.assertEqual(len(result["products"]), 8)
        self.assertGreater(result["total_found"], 8)

    def test_specs_only_on_short_result_lists(self):
        self.assertIn("specs", self.tools.search_products(query="Takamine GD20")["products"][0])
        long_list = self.tools.search_products(category="Violões")["products"]
        self.assertNotIn("specs", long_list[0])

    def test_empty_category_does_not_claim_the_store_lacks_it(self):
        result = self.tools.search_products(category="Cordas Orquestrais")
        self.assertEqual(result["total_found"], 0)
        self.assertIn("Do not claim", result["note"])
        self.assertIn("Do not name specific products", result["note"])
        self.assertIn("similar options", result["note"])


class PromotionsTest(ToolsTestCase):
    def test_lists_only_active_promotions(self):
        ids = {p["id"] for p in self.tools.list_promotions()["promotions"]}
        self.assertEqual(ids, {90, 94, 121, 127})


class GetOrderTest(ToolsTestCase):
    def test_returns_order_to_its_owner(self):
        customer = self.store.customers[self.store.orders[8].customer_id]
        result = self.tools.get_order(8, customer.email)
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], "shipped")
        self.assertEqual(result["tracking_code"], "BRJL5544332BR")
        self.assertEqual(result["items"][0]["quantity"], 1)

    def test_does_not_expose_contact_details(self):
        customer = self.store.customers[self.store.orders[8].customer_id]
        payload = json.dumps(self.tools.get_order(8, customer.email))
        self.assertNotIn(customer.email, payload)
        self.assertNotIn(customer.phone, payload)

    def test_wrong_contact_and_unknown_order_look_the_same(self):
        wrong_contact = self.tools.get_order(8, "someone.else@example.com")
        unknown_order = self.tools.get_order(999, "someone.else@example.com")
        self.assertEqual(wrong_contact, unknown_order)
        self.assertEqual(wrong_contact["message"], ORDER_NOT_VERIFIED)

    def test_non_numeric_order_is_not_verified(self):
        self.assertFalse(self.tools.get_order("abc", "x@example.com")["verified"])


class GetPolicyTest(ToolsTestCase):
    def test_returns_the_section(self):
        self.assertIn("09:00", self.tools.get_policy("hours")["content"])

    def test_unknown_topic_lists_valid_ones(self):
        result = self.tools.get_policy("nope")
        self.assertIn("hours", result["topics"])


class OpenTicketTest(ToolsTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "tickets.jsonl"
        monday = datetime(2026, 11, 9, 10, tzinfo=STORE_TIMEZONE)
        self.tools = Tools(self.store, PolicyManual(), TicketLog(self.path), clock=lambda: monday)

    def records(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]

    def test_complaint_is_recorded_with_the_24_hour_deadline(self):
        result = self.tools.open_ticket("complaint", "Braço rachado", "a@b.com", 8)
        self.assertEqual(result["ticket_id"], "EM-00001")
        self.assertIn("24 business hours", result["next_step"])
        record = self.records()[0]
        self.assertEqual(record["summary"], "Braço rachado")
        self.assertEqual(record["order_id"], 8)

    def test_return_request_promises_no_deadline(self):
        result = self.open_return("2026-11-07")
        self.assertIn("do not promise", result["next_step"])
        self.assertEqual(self.records()[0]["received_date"], "2026-11-07")

    def open_return(self, received_date, kind="return"):
        owner = self.store.customers[self.store.orders[8].customer_id]
        return self.tools.open_ticket(kind, "x", owner.email, 8, received_date)

    def test_return_needs_a_verified_order(self):
        for order_id in (8, None):
            with self.subTest(order_id=order_id):
                result = self.tools.open_ticket("return", "x", "a@b.com", order_id, "2026-11-07")
                self.assertEqual(result["error"], ORDER_NOT_VERIFIED)
        self.assertFalse(self.path.exists())

    def test_return_needs_a_valid_received_date(self):
        for received_date in (None, "ontem", "2026-11-10"):
            with self.subTest(received_date=received_date):
                self.assertIn("error", self.open_return(received_date))
        self.assertFalse(self.path.exists())

    def test_withdrawal_window_is_seven_days(self):
        self.assertIn("ticket_id", self.open_return("2026-11-02"))
        late = self.open_return("2026-11-01")
        self.assertIn("8 days ago", late["error"])

    def test_exchange_is_not_limited_to_seven_days(self):
        self.assertIn("ticket_id", self.open_return("2026-10-20", kind="exchange"))

    def test_ticket_numbers_increase(self):
        self.tools.open_ticket("complaint", "um", "a@b.com")
        result = self.tools.open_ticket("complaint", "dois", "a@b.com")
        self.assertEqual(result["ticket_id"], "EM-00002")

    def test_invalid_tickets_are_not_recorded(self):
        for arguments in (("nope", "x", "a@b.com"), ("complaint", " ", "a@b.com"), ("complaint", "x", "")):
            with self.subTest(arguments=arguments):
                self.assertIn("error", self.tools.open_ticket(*arguments))
        self.assertFalse(self.path.exists())


class AnswerWithoutLookupTest(ToolsTestCase):
    def test_accepts_only_the_listed_reasons(self):
        self.assertEqual(self.tools.answer_without_lookup("greeting")["reason"], "greeting")
        self.assertIn("error", self.tools.answer_without_lookup("shipping"))


class ExecuteTest(ToolsTestCase):
    def test_runs_a_tool_from_json_arguments(self):
        result = json.loads(self.tools.execute("get_policy", '{"topic": "hours"}'))
        self.assertEqual(result["topic"], "hours")

    def test_accepts_missing_arguments(self):
        self.assertIn("promotions", json.loads(self.tools.execute("list_promotions", None)))

    def test_output_keeps_accents_readable(self):
        self.assertIn("Horário", self.tools.execute("get_policy", '{"topic": "hours"}'))

    def test_bad_calls_become_errors(self):
        calls = [
            ("does_not_exist", "{}"),
            ("get_policy", "not json"),
            ("get_policy", "[1, 2]"),
            ("get_policy", '{"wrong_argument": 1}'),
            ("search_products", '{"max_price": -1}'),
            ("search_products", '{"max_price": "cheap"}'),
        ]
        for name, arguments in calls:
            with self.subTest(name=name, arguments=arguments):
                self.assertIn("error", json.loads(self.tools.execute(name, arguments)))


class SchemasTest(ToolsTestCase):
    def test_every_schema_has_a_handler(self):
        names = {s["function"]["name"] for s in self.tools.schemas()}
        self.assertEqual(
            names,
            {
                "search_products",
                "list_promotions",
                "get_order",
                "get_policy",
                "open_ticket",
                "answer_without_lookup",
            },
        )

    def test_category_enum_comes_from_the_data(self):
        schema = self.tools.schemas()[0]["function"]["parameters"]
        self.assertIn("Violões", schema["properties"]["category"]["enum"])


if __name__ == "__main__":
    unittest.main()
