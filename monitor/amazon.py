"""Reads product data from an Amazon Brasil product page (/dp/...).

Amazon does not publish JSON-LD, so this reader uses the page's HTML ids.
They can change without notice: tests/fixtures has real pages to catch that.
"""

from bs4 import BeautifulSoup

from monitor.jsonld import ProductInfo, ProductNotFoundError
from monitor.prices import parse_brl_price

# Main offer ("buy box") price. The first one found wins.
PRICE_SELECTORS = (
    "#corePrice_feature_div .a-offscreen",
    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
    "#apex_desktop .a-price .a-offscreen",
)


def extract_amazon_product(html: str) -> ProductInfo:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("#productTitle")
    price = _main_offer_price(soup)

    if title is None or price is None:
        if soup.select_one("#aod-ingress-link"):
            # Only "compare other offers from R$ ..." (other sellers, maybe used). Not the same thing.
            raise ProductNotFoundError(
                "A Amazon não mostrou uma oferta principal, só ofertas de outros vendedores."
            )
        raise ProductNotFoundError(
            "Preço não encontrado na página da Amazon (verificação anti-robô ou página mudou)."
        )

    image = soup.select_one("#landingImage")
    return ProductInfo(
        name=title.get_text(" ", strip=True),
        price=price,
        image_url=(image.get("data-old-hires") or image.get("src")) if image else None,
        in_stock=_in_stock(soup),
    )


def _main_offer_price(soup: BeautifulSoup):
    for selector in PRICE_SELECTORS:
        for element in soup.select(selector):
            try:
                return parse_brl_price(element.get_text(strip=True))
            except ValueError:
                continue  # empty or odd text: try the next element
    return None


def _in_stock(soup: BeautifulSoup) -> bool | None:
    availability = soup.select_one("#availability")
    text = availability.get_text(" ", strip=True).lower() if availability else ""
    if "em estoque" in text:  # "Em estoque", "Apenas 3 em estoque"
        return True
    if "indisponível" in text or "não disponível" in text:
        return False
    return None
