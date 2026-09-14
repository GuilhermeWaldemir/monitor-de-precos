from decimal import Decimal

import pytest

from monitor.jsonld import ProductNotFoundError, extract_product
from tests.helpers import read_fixture


def page(jsonld: str) -> str:
    return f'<html><head><script type="application/ld+json">{jsonld}</script></head></html>'


def test_reads_real_kabum_page():
    info = extract_product(read_fixture("kabum_kf432c16bb1-16.html"))

    assert info.name == "Memória RAM Kingston Fury Beast, 16GB, 3200MHz, DDR4, CL16, Preto - KF432C16BB1/16"
    assert info.price == Decimal("929.99")
    assert isinstance(info.price, Decimal)
    assert info.in_stock is True
    assert info.image_url.startswith("https://images.kabum.com.br/")


def test_reads_real_terabyte_page():
    info = extract_product(read_fixture("terabyte_kf432c16bb1-16.html"))

    assert info.price == Decimal("1624.49")  # price comes as text "1624.49"
    assert info.in_stock is False  # "http://schema.org/OutOfStock"
    assert info.mpn == "KF432C16BB1/16"  # the code is not in the name, only in "mpn"
    assert info.image_url.startswith("https://img.terabyteshop.com.br/")


def test_mercadolivre_bot_check_page_has_no_price():
    with pytest.raises(ProductNotFoundError):
        extract_product(read_fixture("mercadolivre_bot_check.html"))


def test_price_is_never_float():
    # 0.1 as float is 0.1000000000000000055...; as Decimal it stays exactly 0.10.
    info = extract_product(page('{"@type": "Product", "name": "X", "offers": {"price": 0.1}}'))
    assert info.price == Decimal("0.10")


def test_offers_as_list_and_price_as_text():
    info = extract_product(page(
        '{"@type": "Product", "name": "X", "image": ["https://img/1.jpg"],'
        ' "offers": [{"price": "1299.90", "availability": "https://schema.org/OutOfStock"}]}'
    ))
    assert info.price == Decimal("1299.90")
    assert info.in_stock is False
    assert info.image_url == "https://img/1.jpg"


def test_aggregate_offer_uses_low_price():
    info = extract_product(page(
        '{"@type": "Product", "name": "X", "offers": {"@type": "AggregateOffer", "lowPrice": 850, "highPrice": 990}}'
    ))
    assert info.price == Decimal("850.00")


def test_product_inside_graph():
    info = extract_product(page(
        '{"@graph": [{"@type": "Organization"}, {"@type": ["Product"], "name": "X", "offers": {"price": 10}}]}'
    ))
    assert info.name == "X"


def test_skips_broken_json_block():
    html = (
        '<script type="application/ld+json">{ broken </script>'
        '<script type="application/ld+json">{"@type": "Product", "name": "X", "offers": {"price": 5}}</script>'
    )
    assert extract_product(html).price == Decimal("5.00")


def test_product_without_price_is_not_found():
    with pytest.raises(ProductNotFoundError):
        extract_product(page('{"@type": "Product", "name": "X"}'))
