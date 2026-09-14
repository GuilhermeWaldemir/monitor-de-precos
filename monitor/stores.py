"""Identifies which store a product URL belongs to."""

import re
from urllib.parse import urlparse

# Domain -> name shown on the site.
KNOWN_STORES = {
    "mercadolivre.com.br": "Mercado Livre",
    "kabum.com.br": "KaBuM!",
    "terabyteshop.com.br": "Terabyte",
    "amazon.com.br": "Amazon",
    "magazineluiza.com.br": "Magazine Luiza",
}


def host_from_url(url: str) -> str:
    """"https://www.kabum.com.br/produto/1" -> "kabum.com.br".

    Raises ValueError when the text is not an http(s) URL.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Link inválido: {url!r}")
    return parsed.hostname.lower().removeprefix("www.")


def known_domain(url: str) -> str | None:
    """The KNOWN_STORES domain of the URL, including subdomains; None for other stores."""
    host = host_from_url(url)
    for domain in KNOWN_STORES:
        if host == domain or host.endswith("." + domain):
            return domain
    return None


# Where each store keeps the product id inside the URL path.
_PRODUCT_ID_PATTERNS = {
    "amazon.com.br": r"/(?:dp|gp/product)/([A-Z0-9]{10})",  # ASIN
    "mercadolivre.com.br": r"(MLB-?\d+)",
    "magazineluiza.com.br": r"/p/([a-z0-9]+)/",
}


def link_key(url: str) -> str:
    """Same product page written in different ways -> same key.

    "https://www.amazon.com.br/Kingston/dp/B097K2MRS3/ref=sr_1?x=1" and
    "https://amazon.com.br/dp/B097K2MRS3" both give "amazon.com.br:B097K2MRS3".
    Other stores: domain + path, ignoring "www.", query string, "#..." and a final "/".
    """
    domain = known_domain(url)
    path = urlparse(url.strip()).path
    pattern = _PRODUCT_ID_PATTERNS.get(domain)
    if pattern:
        match = re.search(pattern, path, re.IGNORECASE)
        if match:
            return f"{domain}:{match.group(1).upper().replace('-', '')}"
    return host_from_url(url) + path.rstrip("/")


def store_name_from_url(url: str) -> str:
    """"https://www.kabum.com.br/produto/1" -> "KaBuM!".

    Unknown stores use the domain itself, so any link can be added.
    """
    domain = known_domain(url)
    return KNOWN_STORES[domain] if domain else host_from_url(url)
