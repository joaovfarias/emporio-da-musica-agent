"""Tools the model can call."""


def search_products(query: str, max_price: float | None = None) -> list[dict]:
    raise NotImplementedError


def get_order(order_id: int, verification: str) -> dict:
    """Order details, released only after the customer's identity is verified."""
    raise NotImplementedError


def get_policy(query: str) -> str:
    raise NotImplementedError
