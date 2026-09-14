"""Reads product data from the JSON-LD block of a page.

Many stores publish product info for search engines in
<script type="application/ld+json">, following schema.org:
Product -> name, image, offers -> price, availability.
"""

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup


class ProductNotFoundError(Exception):
    """The page has no JSON-LD Product with a price."""


@dataclass
class ProductInfo:
    name: str
    price: Decimal
    image_url: str | None
    in_stock: bool | None  # None = the page does not say
    mpn: str | None = None  # Manufacturer Part Number, e.g. "KF432C16BB1/16"
    gtin: str | None = None  # EAN/barcode, e.g. "740617319880"


def extract_product(html: str) -> ProductInfo:
    """Return name, price, image and availability found in the page's JSON-LD."""
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            # parse_float=Decimal: read 929.99 as Decimal, never as float.
            data = json.loads(script.string or "", parse_float=Decimal)
        except json.JSONDecodeError:
            continue  # a broken block should not stop us from reading the others

        for item in _walk(data):
            if _is_product(item):
                info = _product_info(item)
                if info is not None:
                    return info

    raise ProductNotFoundError(
        "Preço não encontrado na página (verificação anti-robô ou página mudou)."
    )


def _walk(data):
    """Yield every JSON object, including ones inside lists and "@graph"."""
    if isinstance(data, list):
        for element in data:
            yield from _walk(element)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _walk(data["@graph"])


def _is_product(item: dict) -> bool:
    kind = item.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "Product" in kinds


def _product_info(product: dict) -> ProductInfo | None:
    offers = product.get("offers")
    offer_list = offers if isinstance(offers, list) else [offers]

    for offer in offer_list:
        if not isinstance(offer, dict):
            continue
        # A single offer has "price"; a group of offers (AggregateOffer) has "lowPrice".
        price = _to_decimal(offer.get("price", offer.get("lowPrice")))
        if price is None:
            continue
        return ProductInfo(
            name=str(product.get("name", "")).strip(),
            price=price,
            image_url=_first_image(product.get("image")),
            in_stock=_in_stock(offer.get("availability")),
            mpn=_first_text(product, ("mpn",)),
            gtin=_first_text(product, ("gtin13", "gtin", "gtin12", "gtin14", "gtin8")),
        )
    return None


def _to_decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        return None
    if not price.is_finite() or price <= 0:
        return None
    return price.quantize(Decimal("0.01"))


def _first_text(product: dict, keys: tuple[str, ...]) -> str | None:
    """Value of the first key that exists and is not empty, as text."""
    for key in keys:
        value = product.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _first_image(image) -> str | None:
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    return image if isinstance(image, str) else None


def _in_stock(availability) -> bool | None:
    if not isinstance(availability, str):
        return None
    status = availability.rsplit("/", 1)[-1]  # "https://schema.org/InStock" -> "InStock"
    return status in ("InStock", "LimitedAvailability", "OnlineOnly")
