"""Access to the store's operational data (products, orders, customers, promotions)."""
import csv
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from emporio_agent.config import DATA_DIR

AVAILABLE = "available"
OUT_OF_STOCK = "out_of_stock"
DISCONTINUED = "discontinued"
COMING_SOON = "coming_soon"

MIN_PHONE_DIGITS = 8
MIN_PARTIAL_TOKEN_LENGTH = 3


def normalize(text: str) -> str:
    """Lowercase, remove accents and replace punctuation with spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    description: str
    list_price: Decimal
    stock: int
    status: str
    specs: dict

    @property
    def availability(self) -> str:
        """Stock alone is misleading: discontinued items can still have units on record."""
        if self.status == "discontinued":
            return DISCONTINUED
        if self.status == "coming_soon":
            return COMING_SOON
        return AVAILABLE if self.stock > 0 else OUT_OF_STOCK


@dataclass(frozen=True)
class Promotion:
    product_id: int
    percent: int
    description: str


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str

    def matches_contact(self, contact: str) -> bool:
        """True if contact is this customer's e-mail or phone number."""
        contact = contact.strip()
        if "@" in contact:
            return contact.casefold() == self.email.strip().casefold()
        digits = _digits(contact)
        if len(digits) > 11 and digits.startswith("55"):
            digits = digits[2:]
        return len(digits) >= MIN_PHONE_DIGITS and _digits(self.phone).endswith(digits)


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    date: str
    status: str
    total: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: str | None
    notes: str | None
    items: tuple[OrderItem, ...]


def _read(data_dir: Path, table: str) -> list[dict[str, str]]:
    with open(data_dir / f"{table}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Store:
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        self.categories = {
            int(r["category_id"]): Category(int(r["category_id"]), r["name"])
            for r in _read(data_dir, "categories")
        }
        self.products = {
            int(r["product_id"]): Product(
                id=int(r["product_id"]),
                name=r["name"],
                category_id=int(r["category_id"]),
                description=r["description"],
                list_price=Decimal(r["price_brl"]),
                stock=int(r["stock_quantity"]),
                status=r["status"],
                specs=json.loads(r["specs"]),
            )
            for r in _read(data_dir, "products")
        }
        self.promotions = {
            int(r["product_id"]): Promotion(
                int(r["product_id"]), int(r["discount_percent"]), r["description"]
            )
            for r in _read(data_dir, "promotions")
            if r["is_active"] == "1"
        }
        self.customers = {
            int(r["customer_id"]): Customer(
                int(r["customer_id"]), r["name"], r["phone"], r["email"]
            )
            for r in _read(data_dir, "customers")
        }
        items: dict[int, list[OrderItem]] = {}
        for r in _read(data_dir, "order_items"):
            items.setdefault(int(r["order_id"]), []).append(
                OrderItem(int(r["product_id"]), int(r["quantity"]))
            )
        self.orders = {
            int(r["order_id"]): Order(
                id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                date=r["order_date"],
                status=r["status"],
                total=Decimal(r["total_brl"]),
                payment_method=r["payment_method"],
                tracking_code=r["tracking_code"] or None,
                estimated_delivery=r["estimated_delivery"] or None,
                notes=r["notes"] or None,
                items=tuple(items.get(int(r["order_id"]), ())),
            )
            for r in _read(data_dir, "orders")
        }

    def category_by_name(self, name: str) -> Category | None:
        wanted = normalize(name)
        return next((c for c in self.categories.values() if normalize(c.name) == wanted), None)

    def find_products(
        self, query: str | None = None, category_id: int | None = None
    ) -> list[Product]:
        """Products matching every query term or, failing that, those matching the most terms."""
        candidates = [
            p for p in self.products.values() if category_id in (None, p.category_id)
        ]
        tokens = normalize(query).split() if query else []
        if not tokens:
            return candidates

        full_matches = [p for p in candidates if self._matched_terms(p, tokens) == len(tokens)]
        if full_matches:
            return full_matches

        significant = [t for t in tokens if len(t) >= MIN_PARTIAL_TOKEN_LENGTH]
        scored = [(self._matched_terms(p, significant), p) for p in candidates]
        best = max((score for score, _ in scored), default=0)
        return [p for score, p in scored if best and score == best]

    @staticmethod
    def _matched_terms(product: Product, tokens: list[str]) -> int:
        searchable = normalize(f"{product.name} {product.description}").replace(" ", "")
        return sum(1 for token in tokens if token in searchable)

    def verified_order(self, order_id: int, contact: str) -> Order | None:
        """The order, only if contact belongs to its customer."""
        order = self.orders.get(order_id)
        if order is None or not self.customers[order.customer_id].matches_contact(contact):
            return None
        return order
