"""Checks the current price of a product's links."""

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from monitor import db
from monitor.fetcher import FetchError, fetch_html
from monitor.jsonld import ProductNotFoundError
from monitor.prices import format_brl
from monitor.readers import reader_for

logger = logging.getLogger(__name__)

Fetch = Callable[[str], str]


@dataclass
class CheckResult:
    store: str
    ok: bool
    message: str


def check_product(conn: sqlite3.Connection, product_id: int, fetch: Fetch = fetch_html) -> list[CheckResult]:
    """Check every link of the product and save each result in the history.

    `fetch` can be replaced in tests by a function that returns saved HTML,
    so tests never touch the internet.
    """
    return [_check(conn, link, fetch) for link in db.list_links(conn, product_id)]


def check_link(conn: sqlite3.Connection, link_id: int, fetch: Fetch = fetch_html) -> CheckResult:
    """Check a single link (used right after a new source is added)."""
    link = db.get_link(conn, link_id)
    if link is None:
        raise ValueError(f"Link {link_id} não existe.")
    return _check(conn, link, fetch)


def _check(conn: sqlite3.Connection, link: sqlite3.Row, fetch: Fetch) -> CheckResult:
    try:
        html = fetch(link["url"])
        info = reader_for(link["url"])(html)
    except (FetchError, ProductNotFoundError) as error:
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
