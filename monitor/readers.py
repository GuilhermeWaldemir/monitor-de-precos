"""Chooses how to read a store page.

Most stores publish JSON-LD, so that is the default. A store that needs its
own reader gets one file (e.g. amazon.py) and one line in SPECIFIC_READERS.
"""

from collections.abc import Callable

from monitor.amazon import extract_amazon_product
from monitor.jsonld import ProductInfo, extract_product
from monitor.stores import known_domain

Reader = Callable[[str], ProductInfo]

SPECIFIC_READERS: dict[str, Reader] = {
    "amazon.com.br": extract_amazon_product,
}


def reader_for(url: str) -> Reader:
    return SPECIFIC_READERS.get(known_domain(url), extract_product)
