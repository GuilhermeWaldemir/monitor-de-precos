import pytest

from monitor.matching import code_matches, title_has_code
from monitor.stores import store_name_from_url
from tests.helpers import AMAZON_URL, KABUM_URL, MAGALU_URL, ML_URL, TERABYTE_URL

CODE = "KF432C16BB1/16"


def test_title_with_same_code_matches():
    assert title_has_code("Memória RAM Kingston Fury Beast, 16GB, 3200MHz, DDR4, CL16, Preto - KF432C16BB1/16", CODE)


def test_code_comparison_ignores_case_and_separators():
    assert title_has_code("memoria kingston kf432c16bb1-16 preto", CODE)


def test_similar_code_is_a_different_product():
    # KF432C16BB/16 (without the "1") is another memory module.
    assert not title_has_code("Memória Kingston Fury Beast 16GB 3200MHz DDR4 - KF432C16BB/16", CODE)


def test_code_must_be_a_whole_word():
    assert not title_has_code("Memória Kingston Fury Beast KF432C16BB1/16WP", CODE)


def test_empty_code_never_matches():
    assert not title_has_code("qualquer coisa", "")


@pytest.mark.parametrize(
    ("page_code", "page_gtin", "page_title", "expected"),
    [
        ("KF432C16BB1/16", None, "Memória Kingston Fury Beast 16GB | Terabyte", True),  # confirmed by mpn
        ("KF432C16BB/16", None, "Memória Kingston Fury Beast", False),  # page declares another mpn
        (None, None, "Memória Kingston Fury Beast - KF432C16BB1/16", True),  # confirmed by title
        (None, None, "Memória Kingston Fury Beast 16GB", None),  # page shows no code: unknown
        (None, "740617319880", "Memória Kingston Fury Beast", None),  # only a barcode: can't compare
        (None, None, None, None),
    ],
)
def test_code_matches_manufacturer_code(page_code, page_gtin, page_title, expected):
    assert code_matches(CODE, page_code, page_gtin, page_title) is expected


EAN = "7891350034240"


@pytest.mark.parametrize(
    ("page_code", "page_gtin", "expected"),
    [
        (None, EAN, True),
        (None, "07891350034240", True),  # GTIN-14 with a leading zero is the same barcode
        (None, "7891350099999", False),  # another barcode = another product
        ("ABC-123", None, None),  # page has only a part number: can't compare with an EAN
    ],
)
def test_code_matches_ean(page_code, page_gtin, expected):
    assert code_matches(EAN, page_code, page_gtin, "Perfume Malbec 100ml") is expected


@pytest.mark.parametrize("code", [None, "", "  ", "/-"])
def test_product_without_code_is_never_confirmed(code):
    assert code_matches(code, "KF432C16BB1/16", EAN, "KF432C16BB1/16") is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (KABUM_URL, "KaBuM!"),
        (ML_URL, "Mercado Livre"),
        (TERABYTE_URL, "Terabyte"),
        (AMAZON_URL, "Amazon"),
        (MAGALU_URL, "Magazine Luiza"),
        ("https://produto.mercadolivre.com.br/MLB-123", "Mercado Livre"),
        ("https://notamazon.com.br/dp/1", "notamazon.com.br"),  # not a subdomain of amazon.com.br
        ("https://www.pichau.com.br/memoria", "pichau.com.br"),
    ],
)
def test_store_name_from_url(url, expected):
    assert store_name_from_url(url) == expected


@pytest.mark.parametrize("url", ["", "kabum.com.br/produto/1", "ftp://kabum.com.br", "not a link"])
def test_invalid_url(url):
    with pytest.raises(ValueError):
        store_name_from_url(url)
