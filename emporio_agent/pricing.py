"""Deterministic price rules, kept out of the model: promotions, PIX discount, installments."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
PIX_DISCOUNT_PERCENT = 5

# (highest number of installments in the tier, minimum value of each installment)
INSTALLMENT_TIERS = (
    (12, Decimal("100")),
    (6, Decimal("80")),
    (3, Decimal("50")),
)


@dataclass(frozen=True)
class Quote:
    list_price: Decimal
    price: Decimal
    promotion_percent: int | None
    pix_price: Decimal | None
    max_installments: int
    installment_value: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _apply_discount(amount: Decimal, percent: int) -> Decimal:
    return _money(amount * (100 - percent) / 100)


def max_installments(amount: Decimal) -> int:
    """Highest number of installments whose value meets the minimum of its tier."""
    lower_limits = (6, 3, 1)
    for (upper, minimum), lower in zip(INSTALLMENT_TIERS, lower_limits):
        for count in range(upper, lower, -1):
            if amount / count >= minimum:
                return count
    return 1


def quote(list_price: Decimal, promotion_percent: int | None = None) -> Quote:
    """Price a product. Promotions and the PIX discount are not cumulative."""
    list_price = _money(list_price)
    if promotion_percent:
        price = _apply_discount(list_price, promotion_percent)
        pix_price = None
    else:
        price = list_price
        pix_price = _apply_discount(list_price, PIX_DISCOUNT_PERCENT)
    installments = max_installments(price)
    return Quote(
        list_price=list_price,
        price=price,
        promotion_percent=promotion_percent or None,
        pix_price=pix_price,
        max_installments=installments,
        installment_value=_money(price / installments),
    )
