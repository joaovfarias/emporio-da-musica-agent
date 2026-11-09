import unittest

from emporio_agent.policies import PolicyManual


class PolicyManualTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manual = PolicyManual()

    def test_exposes_every_customer_facing_topic(self):
        self.assertEqual(
            self.manual.topics,
            [
                "about",
                "hours",
                "payment",
                "returns",
                "shipping",
                "promotions",
                "customer_service",
                "warranty",
                "privacy",
            ],
        )

    def test_sections_hold_their_own_content(self):
        expected = {
            "about": "Rua 14 de Maio",
            "hours": "09:00 às 13:00",
            "payment": "Parcelamento de 7x a 12x",
            "returns": "7 (sete) dias corridos",
            "shipping": "taxa fixa de R$ 35,00",
            "promotions": "não são cumulativas",
            "customer_service": "Prazo de retorno: 24 horas úteis",
            "warranty": "90",
            "privacy": "LGPD",
        }
        for topic, text in expected.items():
            with self.subTest(topic=topic):
                self.assertIn(text, self.manual.section(topic))

    def test_sections_do_not_leak_into_each_other(self):
        self.assertNotIn("Parcelamento", self.manual.section("hours"))
        self.assertNotIn("Garantia Legal", self.manual.section("customer_service"))

    def test_numbered_list_does_not_start_a_section(self):
        self.assertIn("Fechamento:", self.manual.section("customer_service"))

    def test_sections_spanning_pages_stay_whole(self):
        shipping = self.manual.section("shipping")
        self.assertIn("5.1 Entregas", shipping)
        self.assertIn("5.3 Código de Rastreamento", shipping)

    def test_page_furniture_is_removed(self):
        for topic in self.manual.topics:
            with self.subTest(topic=topic):
                section = self.manual.section(topic)
                self.assertNotIn("Manual de Políticas e Procedimentos", section)
                self.assertNotIn("Página ", section)

    def test_internal_section_is_not_exposed(self):
        self.assertIsNone(self.manual.section("final"))
        self.assertFalse(
            any("Disposições Finais" in self.manual.section(t) for t in self.manual.topics)
        )

    def test_unknown_topic_returns_none(self):
        self.assertIsNone(self.manual.section("nope"))


if __name__ == "__main__":
    unittest.main()
