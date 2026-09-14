import pytest

from monitor import db
from monitor.search import search_products
from tests.helpers import ELECTRONICS_ID, KABUM_URL, PERFUMES_ID, RAM_CODE


@pytest.fixture
def products(conn):
    ram = db.create_product(
        conn, name="Memória Kingston Fury Beast 16GB DDR4", category_id=ELECTRONICS_ID,
        urls=[KABUM_URL], manufacturer_code=RAM_CODE,
    )
    perfume = db.create_product(
        conn, name="Perfume Malbec Eau de Toilette 100ml", category_id=PERFUMES_ID,
        urls=[KABUM_URL], manufacturer_code="7891350034240",
    )
    return {"ram": ram, "perfume": perfume}


def ids(conn, query):
    return [p["id"] for p in search_products(conn, query)]


@pytest.mark.parametrize("query", ["memoria", "MEMÓRIA", "kingston 16gb", "king", "  fury   beast "])
def test_finds_by_name_ignoring_case_accents_and_partial_words(conn, products, query):
    assert ids(conn, query) == [products["ram"]]


def test_every_word_must_match(conn, products):
    assert ids(conn, "kingston perfume") == []


def test_small_words_are_ignored(conn, products):
    assert ids(conn, "perfume de malbec") == [products["perfume"]]


@pytest.mark.parametrize("query", ["KF432C16BB1/16", "kf432c16bb1-16", "kf432"])
def test_finds_by_code(conn, products, query):
    assert ids(conn, query) == [products["ram"]]


def test_finds_by_ean(conn, products):
    assert ids(conn, "7891350034240") == [products["perfume"]]


@pytest.mark.parametrize("query", ["", "   ", "de", "!!"])
def test_empty_or_meaningless_query_returns_nothing(conn, products, query):
    assert ids(conn, query) == []


def test_no_results(conn, products):
    assert ids(conn, "geladeira") == []


def test_newest_first(conn, products):
    newer = db.create_product(conn, name="Perfume Kingston", category_id=PERFUMES_ID, urls=[KABUM_URL])
    assert ids(conn, "kingston") == [newer, products["ram"]]
