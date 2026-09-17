"""Checks the current price of a product's links."""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from monitor import db, mercadolivre
from monitor.fetcher import FetchError, fetch_html
from monitor.jsonld import ProductInfo, ProductNotFoundError
from monitor.prices import format_brl
from monitor.readers import reader_for

logger = logging.getLogger(__name__)

Fetch = Callable[[str], str]
MlReader = Callable[[sqlite3.Connection, str], ProductInfo]


@dataclass
class CheckResult:
    store: str
    ok: bool
    message: str


def check_product(
    conn: sqlite3.Connection, product_id: int, fetch: Fetch = fetch_html, read_ml: MlReader | None = None
) -> list[CheckResult]:
    """Check every link of the product and save each result in the history.

    `fetch` (and `read_ml`, the Mercado Livre API) can be replaced in tests by functions
    that return saved data, so tests never touch the internet.
    """
    return [_check(conn, link, fetch, read_ml) for link in db.list_links(conn, product_id)]


def check_link(
    conn: sqlite3.Connection, link_id: int, fetch: Fetch = fetch_html, read_ml: MlReader | None = None
) -> CheckResult:
    """Check a single link (used right after a new source is added)."""
    link = db.get_link(conn, link_id)
    if link is None:
        raise ValueError(f"Link {link_id} não existe.")
    return _check(conn, link, fetch, read_ml)


def _read(conn: sqlite3.Connection, url: str, fetch: Fetch, read_ml: MlReader | None):
    """Mercado Livre goes through its official API when connected; everything else reads the page."""
    if mercadolivre.handles(url) and mercadolivre.can_read(conn):
        return (read_ml or mercadolivre.read_product)(conn, url)
    return reader_for(url)(fetch(url))


def _check(conn: sqlite3.Connection, link: sqlite3.Row, fetch: Fetch, read_ml: MlReader | None) -> CheckResult:
    try:
        info = _read(conn, link["url"], fetch, read_ml)
    except (FetchError, ProductNotFoundError, mercadolivre.MercadoLivreError) as error:
        return _save_failure(conn, link, str(error))
    except Exception:
        # A bug or an unexpected page must not stop the other stores.
        logger.exception("Unexpected error checking %s", link["url"])
        return _save_failure(conn, link, "Erro inesperado ao ler a página.")

    db.add_price_check(
        conn,
        link["id"],
        source="auto",
        price=info.price,
        in_stock=info.in_stock,
        page_title=info.name,
        page_code=info.mpn,
        page_gtin=info.gtin,
    )
    if info.image_url:
        db.set_image_if_missing(conn, link["product_id"], info.image_url)
    return CheckResult(link["store"], True, format_brl(info.price))


def _save_failure(conn: sqlite3.Connection, link: sqlite3.Row, message: str) -> CheckResult:
    db.add_price_check(conn, link["id"], source="auto", error=message)
    return CheckResult(link["store"], False, message)
