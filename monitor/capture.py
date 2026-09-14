"""The "Capturar preço" bookmarklet: builds the link and reads what it sends.

Why a bookmarklet: some stores block programs (Mercado Livre, Magazine Luiza). Instead of
trying to get around that, the user opens the page normally and clicks a bookmark that sends
the data the page is already showing. Everything that arrives here came from a third-party
page, so it is treated as untrusted: validated, trimmed and never saved without confirmation.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from monitor.prices import parse_brl_price
from monitor.stores import store_name_from_url

BOOKMARKLET_SOURCE = Path(__file__).parent / "static" / "js" / "bookmarklet.js"
MAX_TEXT_LENGTH = 300


@dataclass
class CapturedPage:
    url: str
    store: str
    name: str
    price: Decimal | None  # None when the page had no readable price (the user types it)
    image_url: str | None
    mpn: str | None
    gtin: str | None


def bookmarklet_href(app_url: str) -> str:
    """The "javascript:..." link the user drags to the bookmarks bar.

    Full-line // comments are removed (the code becomes one line inside a link) and the
    code is percent-encoded so quotes and spaces survive inside the href.
    """
    lines = BOOKMARKLET_SOURCE.read_text(encoding="utf-8").splitlines()
    code = " ".join(line.strip() for line in lines if line.strip() and not line.strip().startswith("//"))
    return "javascript:" + quote(code.replace("__APP_URL__", app_url), safe="(){};,=:'!*")


def read_captured(values: Mapping[str, str]) -> CapturedPage:
    """Validate the data sent by the bookmarklet (query string) or re-sent by the confirm form.

    Raises ValueError when the URL is not a valid http(s) link.
    """
    url = values.get("url", "").strip()
    store = store_name_from_url(url)  # raises ValueError for invalid links

    try:
        price = parse_brl_price(values.get("price", ""))
    except ValueError:
        price = None

    image = _text(values.get("image"))
    if image and not image.startswith(("https://", "http://")):
        image = None  # only real image links, never e.g. "javascript:" or "data:"

    return CapturedPage(
        url=url,
        store=store,
        name=_text(values.get("name")) or "",
        price=price,
        image_url=image,
        mpn=_text(values.get("mpn")),
        gtin=_text(values.get("gtin")),
    )


def _text(value: str | None) -> str | None:
    value = (value or "").strip()[:MAX_TEXT_LENGTH]
    return value or None
