from decimal import Decimal

import pytest

from monitor import checker, db
from monitor.compare import compare_all
from monitor.fetcher import FetchError
from tests.helpers import AMAZON_URL, ELECTRONICS_ID, KABUM_URL, ML_URL, RAM_CODE, TERABYTE_URL, read_fixture

CODE = RAM_CODE


def fake_fetch(url: str) -> str:
    """Stands in for the internet: returns saved pages or simulates a block."""
    if url == KABUM_URL:
        return read_fixture("kabum_kf432c16bb1-16.html")
    if url == ML_URL:
        return read_fixture("mercadolivre_bot_check.html")
    raise FetchError("A loja bloqueou o acesso automático (HTTP 403).")


@pytest.fixture
def product_id(conn):
    return db.create_product(
        conn,
        name="Kingston Fury Beast 16GB",
        category_id=ELECTRONICS_ID,
        urls=[KABUM_URL, ML_URL, TERABYTE_URL],
        manufacturer_code=CODE,
    )


def test_one_store_failing_does_not_stop_the_others(conn, product_id):
    results = checker.check_product(conn, product_id, fetch=fake_fetch)

    assert [(r.store, r.ok) for r in results] == [
        ("KaBuM!", True),
        ("Mercado Livre", False),
        ("Terabyte", False),
    ]
    assert "403" in results[2].message


def test_unexpected_error_is_recorded_not_raised(conn, product_id):
    def broken_fetch(url):
        raise RuntimeError("bug")

    results = checker.check_product(conn, product_id, fetch=broken_fetch)
    assert all(not r.ok for r in results)


def test_check_saves_image_and_best_price(conn, product_id):
    checker.check_product(conn, product_id, fetch=fake_fetch)

    [comparison] = compare_all(conn)
    assert comparison.image_url.startswith("https://images.kabum.com.br/")
    assert comparison.best.store == "KaBuM!"
    assert comparison.best.price == Decimal("929.99")
    assert comparison.best.code_matches is True


def test_manual_price_can_become_the_best(conn, product_id):
    checker.check_product(conn, product_id, fetch=fake_fetch)
    terabyte = db.list_links(conn, product_id)[2]
    db.add_price_check(conn, terabyte["id"], source="manual", price=Decimal("899.90"))

    [comparison] = compare_all(conn)
    assert comparison.best.store == "Terabyte"
    assert comparison.best.source == "manual"
    assert comparison.best.error is None  # the manual price is newer than the failure
    assert comparison.difference_from_best(comparison.offers[1]) == Decimal("30.09")


def test_last_known_price_is_kept_when_a_new_check_fails(conn, product_id):
    kabum = db.list_links(conn, product_id)[0]
    db.add_price_check(conn, kabum["id"], source="auto", price=Decimal("929.99"), page_title=CODE)
    db.add_price_check(conn, kabum["id"], source="auto", error="A loja demorou demais para responder.")

    offer = next(o for o in compare_all(conn)[0].offers if o.store == "KaBuM!")
    assert offer.price == Decimal("929.99")
    assert offer.error == "A loja demorou demais para responder."


def test_out_of_stock_and_different_product_never_win(conn, product_id):
    kabum, ml, terabyte = db.list_links(conn, product_id)
    db.add_price_check(conn, kabum["id"], source="auto", price=Decimal("500.00"), in_stock=False, page_code=CODE)
    db.add_price_check(conn, ml["id"], source="auto", price=Decimal("400.00"), page_code="KF432C16BB/16")
    db.add_price_check(conn, terabyte["id"], source="auto", price=Decimal("950.00"), page_code=CODE)

    [comparison] = compare_all(conn)
    assert comparison.best.store == "Terabyte"


def test_real_pages_kabum_in_stock_beats_terabyte_out_of_stock(conn, product_id):
    def real_pages(url):
        return {
            KABUM_URL: read_fixture("kabum_kf432c16bb1-16.html"),
            TERABYTE_URL: read_fixture("terabyte_kf432c16bb1-16.html"),
        }.get(url) or read_fixture("mercadolivre_bot_check.html")

    checker.check_product(conn, product_id, fetch=real_pages)

    [comparison] = compare_all(conn)
    terabyte = next(o for o in comparison.offers if o.store == "Terabyte")
    assert terabyte.code_matches is True  # confirmed through "mpn"
    assert terabyte.in_stock is False
    assert comparison.best.store == "KaBuM!"


def test_offers_are_sorted_cheapest_first_without_price_last(conn, product_id):
    kabum, ml, terabyte = db.list_links(conn, product_id)
    db.add_price_check(conn, kabum["id"], source="manual", price=Decimal("950.00"))
    db.add_price_check(conn, terabyte["id"], source="manual", price=Decimal("900.00"))

    [comparison] = compare_all(conn)
    assert [o.store for o in comparison.offers] == ["Terabyte", "KaBuM!", "Mercado Livre"]
    assert comparison.bar_percent(comparison.offers[1]) == 100
    assert comparison.bar_percent(comparison.offers[2]) == 0


def test_check_link_uses_the_amazon_reader(conn, product_id):
    link_id = db.add_link(conn, product_id, AMAZON_URL)
    result = checker.check_link(conn, link_id, fetch=lambda url: read_fixture("amazon_kf432c16bb1-16.html"))

    assert (result.store, result.ok, result.message) == ("Amazon", True, "R$ 1.855,02")
    offer = next(o for o in compare_all(conn)[0].offers if o.store == "Amazon")
    assert offer.code_matches is True  # code found in the Amazon title
    # Only the new link was checked.
    assert conn.execute("SELECT COUNT(*) FROM price_checks").fetchone()[0] == 1


def test_check_link_unknown_id(conn):
    with pytest.raises(ValueError):
        checker.check_link(conn, 999, fetch=fake_fetch)


def test_best_prices_and_price_range(conn, product_id):
    from monitor.compare import best_prices, price_range

    checker.check_product(conn, product_id, fetch=fake_fetch)  # KaBuM! R$ 929,99
    no_price_id = db.create_product(conn, name="Sem preço", category_id=ELECTRONICS_ID, urls=[TERABYTE_URL])

    prices = best_prices(conn, db.list_products(conn))
    assert prices == {product_id: Decimal("929.99"), no_price_id: None}
    assert price_range(prices) == (0, 930)  # a single price: the slider starts at 0


def test_price_range_with_several_prices_and_without_prices():
    from monitor.compare import price_range

    assert price_range({1: Decimal("929.99"), 2: Decimal("1855.02"), 3: None}) == (929, 1856)
    assert price_range({1: None}) is None
    assert price_range({}) is None


def test_best_price_ignores_out_of_stock(conn, product_id):
    from monitor.compare import best_prices

    kabum = db.list_links(conn, product_id)[0]
    db.add_price_check(conn, kabum["id"], source="auto", price=Decimal("10.00"), in_stock=False)
    assert best_prices(conn, db.list_products(conn)) == {product_id: None}


def test_comparison_has_category(conn, product_id):
    [comparison] = compare_all(conn)
    assert (comparison.category_id, comparison.category_name) == (ELECTRONICS_ID, "Eletrônicos")
