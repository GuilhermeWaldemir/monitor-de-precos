from decimal import Decimal

import pytest

from monitor.amazon import extract_amazon_product
from monitor.jsonld import ProductNotFoundError, extract_product
from monitor.readers import reader_for
from tests.helpers import AMAZON_URL, KABUM_URL, MAGALU_URL, RAM_CODE, read_fixture


def test_reads_real_amazon_page():
    info = extract_amazon_product(read_fixture("amazon_kf432c16bb1-16.html"))

    assert info.name.startswith(RAM_CODE)  # the code is in the title
    assert info.price == Decimal("1855.02")  # "R$1.855,02", no space after R$
    assert info.in_stock is True
    assert info.image_url.startswith("https://m.media-amazon.com/")


def test_amazon_page_without_featured_offer():
    # Real page where Amazon only showed "compare other offers from R$ 1.439,46".
    with pytest.raises(ProductNotFoundError, match="oferta principal"):
        extract_amazon_product(read_fixture("amazon_no_featured_offer.html"))


def test_amazon_bot_check_page():
    with pytest.raises(ProductNotFoundError):
        extract_amazon_product("<html><title>Robot Check</title><form>captcha</form></html>")


@pytest.mark.parametrize(
    ("availability", "expected"),
    [("Em estoque", True), ("Apenas 3 em estoque", True), ("Não disponível.", False), ("", None)],
)
def test_amazon_availability(availability, expected):
    html = f"""
        <span id="productTitle">Produto</span>
        <div id="corePrice_feature_div"><span class="a-offscreen">R$ 10,00</span></div>
        <div id="availability"><span>{availability}</span></div>
    """
    assert extract_amazon_product(html).in_stock is expected


def test_reader_for_chooses_by_store():
    assert reader_for(AMAZON_URL) is extract_amazon_product
    assert reader_for("https://amazon.com.br/dp/X") is extract_amazon_product
    assert reader_for(KABUM_URL) is extract_product
    assert reader_for(MAGALU_URL) is extract_product
