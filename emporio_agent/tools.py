"""Tools the model can call."""
import json
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from emporio_agent.policies import PolicyManual
from emporio_agent.pricing import Quote, quote
from emporio_agent.store import AVAILABLE, Order, Product, Store
from emporio_agent.store_hours import store_now
from emporio_agent.tickets import TicketLog

MAX_RESULTS = 8
MAX_ALTERNATIVES = 3
MAX_RESULTS_WITH_SPECS = 3

# The same answer for an unknown order and a wrong contact, so order numbers cannot be probed.
ORDER_NOT_VERIFIED = (
    "Could not verify this order. Ask the customer to confirm the order number "
    "and the e-mail or phone number used in the purchase."
)

NO_LOOKUP_REASONS = ("greeting", "out_of_scope", "asking_customer_for_details")

WITHDRAWAL_DAYS = 7
_STAFF_FOLLOW_UP = (
    "Forwarded to the store's team, who will contact the customer to continue. "
    "No deadline is set for this contact, so do not promise one."
)
TICKET_NEXT_STEPS = {
    "complaint": "Forwarded to the person responsible, who replies within 24 business hours.",
    "return": _STAFF_FOLLOW_UP,
    "exchange": _STAFF_FOLLOW_UP,
}


class Tools:
    def __init__(
        self,
        store: Store,
        manual: PolicyManual,
        tickets: TicketLog | None = None,
        clock: Callable[[], datetime] = store_now,
    ) -> None:
        self._store = store
        self._manual = manual
        self._tickets = tickets or TicketLog()
        self._clock = clock
        self._handlers = {
            "search_products": self.search_products,
            "list_promotions": self.list_promotions,
            "get_order": self.get_order,
            "get_policy": self.get_policy,
            "open_ticket": self.open_ticket,
            "answer_without_lookup": self.answer_without_lookup,
        }

    def schemas(self) -> list[dict[str, Any]]:
        categories = [c.name for c in self._store.categories.values()]
        return [
            _function(
                "search_products",
                "Search the catalog. Use it for any question about products, prices or stock.",
                {
                    "query": {
                        "type": "string",
                        "description": "Product name, brand or feature.",
                    },
                    "category": {"type": "string", "enum": categories},
                    "max_price": {
                        "type": "number",
                        "description": "Highest current price in BRL.",
                    },
                },
            ),
            _function("list_promotions", "List the promotions that are active now.", {}),
            _function(
                "get_order",
                "Get an order's status and details. Requires the order number and the "
                "e-mail or phone number of the customer who placed it. Ask the customer "
                "for both; never guess them.",
                {
                    "order_id": {"type": "integer"},
                    "contact": {
                        "type": "string",
                        "description": "E-mail or phone number given by the customer.",
                    },
                },
                required=["order_id", "contact"],
            ),
            _function(
                "get_policy",
                "Read a section of the store's policy manual: address and contact (about), "
                "opening hours, payment, returns and exchanges, shipping, promotion rules, "
                "customer service procedures, warranty or privacy.",
                {"topic": {"type": "string", "enum": self._manual.topics}},
                required=["topic"],
            ),
            _function(
                "open_ticket",
                "Hand a request over to the store's staff: a complaint, a return (the customer "
                "regrets the purchase) or an exchange (defect or preference). Call it only "
                "after the customer has given the required details.",
                {
                    "kind": {"type": "string", "enum": list(TICKET_NEXT_STEPS)},
                    "summary": {
                        "type": "string",
                        "description": "What happened and what the customer wants.",
                    },
                    "contact": {
                        "type": "string",
                        "description": "E-mail or phone number given by the customer.",
                    },
                    "order_id": {"type": "integer"},
                    "received_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD. The day the customer says the product "
                        "arrived; required for returns and exchanges. Never guess it.",
                    },
                },
                required=["kind", "summary", "contact"],
            ),
            _function(
                "answer_without_lookup",
                "Declare that the reply needs no store facts: a greeting, an out-of-scope "
                "request, or asking the customer for details you are missing. Never use it "
                "for questions about products, prices, stock, promotions, orders, shipping, "
                "payment, hours, address, returns or warranty; those need the other tools.",
                {"reason": {"type": "string", "enum": list(NO_LOOKUP_REASONS)}},
                required=["reason"],
            ),
        ]

    def execute(self, name: str, raw_arguments: str | None) -> str:
        """Run a tool call from the model, reporting bad calls back to it as JSON errors."""
        handler = self._handlers.get(name)
        if handler is None:
            return _to_json({"error": f"Unknown tool '{name}'."})
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return _to_json({"error": "Arguments are not valid JSON."})
        if not isinstance(arguments, dict):
            return _to_json({"error": "Arguments must be a JSON object."})
        try:
            return _to_json(handler(**arguments))
        except (TypeError, ValueError) as error:
            return _to_json({"error": f"Invalid arguments: {error}"})

    def search_products(
        self,
        query: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
    ) -> dict[str, Any]:
        category_id = None
        if category:
            found = self._store.category_by_name(category)
            if found is None:
                return {"error": f"Unknown category '{category}'."}
            category_id = found.id
        limit = _parse_price(max_price)

        products = self._store.find_products(query, category_id)
        if not query:
            products = [p for p in products if p.availability == AVAILABLE]
        if limit is not None:
            products = [p for p in products if self._current_price(p) <= limit]
        products.sort(key=lambda p: (p.availability != AVAILABLE, self._current_price(p)))

        shown = products[:MAX_RESULTS]
        with_specs = len(shown) <= MAX_RESULTS_WITH_SPECS
        result: dict[str, Any] = {
            "total_found": len(products),
            "products": [self._describe(p, with_specs) for p in shown],
        }
        if shown and all(p.availability != AVAILABLE for p in shown):
            result["alternatives"] = [
                self._describe(p) for p in self._alternatives_to(shown[0])
            ]
        if not products:
            result["note"] = (
                "Nothing found in the system. Do not claim that the store never sells this: "
                "say it was not found right now and offer to help with something else. "
                "Do not name specific products or claim there are similar options "
                "that a search has not returned."
            )
        return result

    def list_promotions(self) -> dict[str, Any]:
        promoted = [self._store.products[p] for p in self._store.promotions]
        return {
            "promotions": [
                self._describe(p) for p in promoted if p.availability == AVAILABLE
            ]
        }

    def get_order(self, order_id: int | str, contact: str) -> dict[str, Any]:
        order = self._verified_order(order_id, contact)
        if order is None:
            return {"verified": False, "message": ORDER_NOT_VERIFIED}
        return {"verified": True, **self._describe_order(order)}

    def get_policy(self, topic: str) -> dict[str, Any]:
        section = self._manual.section(topic)
        if section is None:
            return {"error": f"Unknown topic '{topic}'.", "topics": self._manual.topics}
        return {"topic": topic, "content": section}

    def open_ticket(
        self,
        kind: str,
        summary: str,
        contact: str,
        order_id: int | None = None,
        received_date: str | None = None,
    ) -> dict[str, Any]:
        if kind not in TICKET_NEXT_STEPS:
            return {"error": f"Unknown kind '{kind}'.", "kinds": list(TICKET_NEXT_STEPS)}
        if not str(summary).strip() or not str(contact).strip():
            return {"error": "Ask the customer for the missing summary or contact first."}
        if kind != "complaint":
            problem = self._return_problem(kind, order_id, contact, received_date)
            if problem:
                return {"error": problem}
        ticket_id = self._tickets.open(kind, str(summary), str(contact), order_id, received_date)
        return {"ticket_id": ticket_id, "next_step": TICKET_NEXT_STEPS[kind]}

    def _return_problem(
        self, kind: str, order_id: Any, contact: Any, received_date: Any
    ) -> str | None:
        if self._verified_order(order_id, contact) is None:
            return ORDER_NOT_VERIFIED
        received = _parse_date(received_date)
        if received is None:
            return "Ask the customer which day the product arrived. Do not assume it."
        days_since = (self._clock().date() - received).days
        if days_since < 0:
            return "The received date is in the future. Ask the customer to confirm it."
        if kind == "return" and days_since > WITHDRAWAL_DAYS:
            return (
                f"The product arrived {days_since} days ago, outside the {WITHDRAWAL_DAYS}-day "
                "withdrawal period. Do not open a ticket; explain this to the customer."
            )
        return None

    def answer_without_lookup(self, reason: str) -> dict[str, Any]:
        if reason not in NO_LOOKUP_REASONS:
            return {"error": f"Unknown reason '{reason}'.", "reasons": list(NO_LOOKUP_REASONS)}
        return {"reason": reason, "instruction": "Write your reply to the customer now."}

    def _verified_order(self, order_id: Any, contact: Any) -> Order | None:
        try:
            return self._store.verified_order(int(order_id), str(contact))
        except (TypeError, ValueError):
            return None

    def _current_price(self, product: Product) -> Decimal:
        return quote(product.list_price, self._promotion_percent(product)).price

    def _promotion_percent(self, product: Product) -> int | None:
        promotion = self._store.promotions.get(product.id)
        return promotion.percent if promotion else None

    def _alternatives_to(self, product: Product) -> list[Product]:
        same_category = [
            p
            for p in self._store.find_products(category_id=product.category_id)
            if p.availability == AVAILABLE
        ]
        same_category.sort(key=lambda p: abs(p.list_price - product.list_price))
        return same_category[:MAX_ALTERNATIVES]

    def _describe(self, product: Product, with_specs: bool = False) -> dict[str, Any]:
        described: dict[str, Any] = {
            "id": product.id,
            "name": product.name,
            "category": self._store.categories[product.category_id].name,
            "description": product.description,
            "availability": product.availability,
        }
        if product.availability == AVAILABLE:
            described["stock"] = product.stock
        if product.status == "active":
            described["pricing"] = self._describe_price(product)
        if with_specs:
            described["specs"] = product.specs
        return described

    def _describe_price(self, product: Product) -> dict[str, Any]:
        result = quote(product.list_price, self._promotion_percent(product))
        pricing: dict[str, Any] = {
            "summary": _price_summary(result),
            "current_price": float(result.price),
            "max_interest_free_installments": result.max_installments,
            "installment_value": float(result.installment_value),
        }
        if result.promotion_percent:
            pricing["original_price"] = float(result.list_price)
            pricing["discount_percent"] = result.promotion_percent
            pricing["promotion"] = self._store.promotions[product.id].description
            pricing["pix_discount_applies"] = False
        else:
            pricing["pix_price"] = float(result.pix_price)
        return pricing

    def _describe_order(self, order: Order) -> dict[str, Any]:
        customer = self._store.customers[order.customer_id]
        return {
            "order_id": order.id,
            "customer_first_name": customer.name.split()[0],
            "status": order.status,
            "order_date": order.date,
            "total": float(order.total),
            "payment_method": order.payment_method,
            "tracking_code": order.tracking_code,
            "estimated_delivery": order.estimated_delivery,
            "notes": order.notes,
            "items": [
                {"name": self._store.products[i.product_id].name, "quantity": i.quantity}
                for i in order.items
            ],
        }


def _function(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def _brl(value: Decimal) -> str:
    digits = f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    return f"R$ {digits}"


def _price_summary(result: Quote) -> str:
    """Ready-made text: models sometimes mix up numbers when composing it themselves."""
    if result.max_installments > 1:
        terms = f"em até {result.max_installments}x de {_brl(result.installment_value)} sem juros"
    else:
        terms = "à vista"
    if result.promotion_percent:
        return (
            f"De {_brl(result.list_price)} por {_brl(result.price)} "
            f"({result.promotion_percent}% de desconto), {terms}. Sem desconto adicional no PIX."
        )
    return f"{_brl(result.price)} ({terms}), ou {_brl(result.pix_price)} no PIX."


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_price(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("max_price must be a number") from None
    if price < 0:
        raise ValueError("max_price cannot be negative")
    return price


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
