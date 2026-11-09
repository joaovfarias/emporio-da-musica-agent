import unittest
from decimal import Decimal

from emporio_agent.pricing import max_installments, quote


class QuoteTest(unittest.TestCase):
    def test_regular_price_gets_pix_discount(self):
        result = quote(Decimal("2199"))
        self.assertEqual(result.price, Decimal("2199.00"))
        self.assertEqual(result.pix_price, Decimal("2089.05"))
        self.assertIsNone(result.promotion_percent)

    def test_promotional_price_has_no_pix_discount(self):
        result = quote(Decimal("1000"), 10)
        self.assertEqual(result.price, Decimal("900.00"))
        self.assertEqual(result.list_price, Decimal("1000.00"))
        self.assertEqual(result.promotion_percent, 10)
        self.assertIsNone(result.pix_price)

    def test_installments_use_the_promotional_price(self):
        result = quote(Decimal("1250"), 20)
        self.assertEqual(result.price, Decimal("1000.00"))
        self.assertEqual(result.max_installments, 10)
        self.assertEqual(result.installment_value, Decimal("100.00"))

    def test_prices_are_rounded_to_cents(self):
        self.assertEqual(quote(Decimal("599.9")).pix_price, Decimal("569.91"))


class MaxInstallmentsTest(unittest.TestCase):
    def test_tiers(self):
        cases = {
            "1200": 12,
            "800": 8,
            "700": 7,
            "699.99": 6,
            "400": 5,
            "240": 3,
            "150": 3,
            "120": 2,
            "100": 2,
            "60": 1,
        }
        for amount, expected in cases.items():
            with self.subTest(amount=amount):
                self.assertEqual(max_installments(Decimal(amount)), expected)


if __name__ == "__main__":
    unittest.main()
