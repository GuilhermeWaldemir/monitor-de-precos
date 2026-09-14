"""Conversion between price formats.

Money is always Decimal (never float): float cannot represent 0.10 exactly,
so sums like 0.1 + 0.2 give 0.30000000000000004.
"""

import re
from decimal import Decimal, InvalidOperation

# "1.299" or "12.345.678": dots used only as thousands separators.
_THOUSANDS_ONLY = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_brl_price(text: str) -> Decimal:
    """Convert a price typed in Brazilian format to Decimal.

    Examples: "R$ 1.299,90" -> Decimal("1299.90"), "929,99" -> Decimal("929.99").
    Raises ValueError when the text is not a valid price.
    """
    cleaned = text.replace("R$", "").replace("\xa0", "").replace(" ", "").strip()

    if "," in cleaned:
        # Brazilian format: dot = thousands, comma = decimal.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif _THOUSANDS_ONLY.match(cleaned):
        cleaned = cleaned.replace(".", "")
    # Otherwise, a single dot is the decimal separator ("929.99").

    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Preço inválido: {text!r}") from None

    if not value.is_finite() or value <= 0:
        raise ValueError(f"Preço inválido: {text!r}")
    return value.quantize(Decimal("0.01"))


def to_cents(price: Decimal) -> int:
    """Decimal("929.99") -> 92999. SQLite has no decimal type, so we store cents."""
    return int((price * 100).to_integral_value())


def from_cents(cents: int) -> Decimal:
    """92999 -> Decimal("929.99")."""
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def format_brl(price: Decimal) -> str:
    """Decimal("1299.9") -> "R$ 1.299,90"."""
    us_style = f"{price:,.2f}"  # "1,299.90"
    return "R$ " + us_style.replace(",", "_").replace(".", ",").replace("_", ".")
