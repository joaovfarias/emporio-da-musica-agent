import unittest
from decimal import Decimal

from emporio_agent.store import (
    AVAILABLE,
    COMING_SOON,
    DISCONTINUED,
    OUT_OF_STOCK,
    Store,
    normalize,
)


class StoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()

    def test_loads_every_table(self):
        self.assertEqual(len(self.store.products), 65)
        self.assertEqual(len(self.store.customers), 50)
        self.assertEqual(len(self.store.orders), 20)
        self.assertEqual(sum(len(o.items) for o in self.store.orders.values()), 22)

    def test_availability_considers_status_before_stock(self):
        self.assertEqual(self.store.products[81].availability, AVAILABLE)
        self.assertEqual(self.store.products[96].availability, OUT_OF_STOCK)
        self.assertEqual(self.store.products[136].availability, DISCONTINUED)
        self.assertEqual(self.store.products[130].availability, COMING_SOON)

    def test_only_active_promotions_are_loaded(self):
        self.assertEqual(set(self.store.promotions), {90, 94, 121, 127})
        self.assertEqual(self.store.promotions[127].percent, 10)

    def test_normalize_removes_accents_and_punctuation(self):
        self.assertEqual(normalize("Violão GD-20!"), "violao gd 20")

    def test_finds_product_by_name(self):
        self.assertEqual([p.id for p in self.store.find_products("Takamine GD20")], [95])

    def test_search_ignores_case_and_punctuation(self):
        self.assertEqual([p.id for p in self.store.find_products("takamine gd-20")], [95])

    def test_filters_by_category(self):
        category = self.store.category_by_name("violoes")
        products = self.store.find_products(category_id=category.id)
        self.assertEqual(len(products), 35)

    def test_partial_match_returns_closest_products(self):
        names = [p.name for p in self.store.find_products("Takamine Stradivarius")]
        self.assertTrue(names)
        self.assertTrue(all("Takamine" in name for name in names))

    def test_no_match_returns_nothing(self):
        self.assertEqual(self.store.find_products("xylophone"), [])

    def test_order_requires_the_owners_contact(self):
        order = self.store.orders[3]
        customer = self.store.customers[order.customer_id]
        self.assertEqual(self.store.verified_order(3, customer.email.upper()), order)
        self.assertEqual(self.store.verified_order(3, customer.phone), order)
        self.assertIsNone(self.store.verified_order(3, "someone.else@example.com"))
        self.assertIsNone(self.store.verified_order(3, "1234"))
        self.assertIsNone(self.store.verified_order(999, customer.email))

    def test_phone_accepts_country_code(self):
        customer = self.store.customers[self.store.orders[3].customer_id]
        digits = "".join(c for c in customer.phone if c.isdigit())
        self.assertIsNotNone(self.store.verified_order(3, f"+55 {digits}"))

    def test_order_amounts_are_decimal(self):
        self.assertEqual(self.store.orders[4].total, Decimal("799.9"))


if __name__ == "__main__":
    unittest.main()
