from decimal import Decimal

import pytest

from monitor.prices import format_brl, from_cents, parse_brl_price, to_cents


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("R$ 1.299,90", Decimal("1299.90")),
        ("929,99", Decimal("929.99")),
        ("R$\xa0929,99", Decimal("929.99")),  # non-breaking space, common in store HTML
        ("1.299", Decimal("1299.00")),  # dot as thousands separator
        ("12.345.678,00", Decimal("12345678.00")),
        ("929.99", Decimal("929.99")),  # a single dot followed by 2 digits is decimal
        ("50", Decimal("50.00")),
    ],
)
def test_parse_brl_price(text, expected):
    assert parse_brl_price(text) == expected


@pytest.mark.parametrize("text", ["", "abc", "R$", "-10,00", "0", "1,2,3"])
def test_parse_brl_price_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_brl_price(text)


def test_cents_round_trip_is_exact():
    price = Decimal("929.99")
    assert to_cents(price) == 92999
    assert from_cents(92999) == price


def test_format_brl():
    assert format_brl(Decimal("1299.9")) == "R$ 1.299,90"
    assert format_brl(Decimal("929.99")) == "R$ 929,99"
