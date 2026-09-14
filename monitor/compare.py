"""Builds each product's price comparison and picks the best offer."""

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from monitor import db
from monitor.matching import code_matches
from monitor.prices import from_cents


@dataclass
class StoreOffer:
    link_id: int
    store: str
    url: str
    price: Decimal | None = None
    in_stock: bool | None = None
    source: str | None = None  # "auto", "manual" or "capture" (see db.PRICE_CHECKS_TABLE)
    price_checked_at: datetime | None = None
    page_title: str | None = None
    error: str | None = None  # set only when the latest check failed
    code_matches: bool | None = None  # None = not confirmed (manual price or page without code)

    @property
    def can_be_best(self) -> bool:
        # Out of stock or a different product never wins.
        return self.price is not None and self.in_stock is not False and self.code_matches is not False


@dataclass
class ProductComparison:
    id: int
    name: str
    category_id: int
    category_name: str
    manufacturer_code: str | None
    image_url: str | None
    offers: list[StoreOffer] = field(default_factory=list)

    @property
    def best(self) -> StoreOffer | None:
        candidates = [offer for offer in self.offers if offer.can_be_best]
        return min(candidates, key=lambda offer: offer.price, default=None)

    def bar_percent(self, offer: StoreOffer) -> int:
        """Bar width (0-100) for the price chart: the most expensive store is 100."""
        top = max((o.price for o in self.offers if o.price is not None), default=None)
        if offer.price is None or not top:
            return 0
        return round(offer.price / top * 100)

    def difference_from_best(self, offer: StoreOffer) -> Decimal | None:
        """How much more this store costs than the best offer."""
        best = self.best
        if best is None or offer.price is None or offer.link_id == best.link_id:
            return None
        return offer.price - best.price


def compare_product(conn: sqlite3.Connection, product: sqlite3.Row) -> ProductComparison:
    """`product` is a row from db.get_product or db.list_products (includes category_name)."""
    comparison = ProductComparison(
        id=product["id"],
        name=product["name"],
        category_id=product["category_id"],
        category_name=product["category_name"],
        manufacturer_code=product["manufacturer_code"],
        image_url=product["image_url"],
    )
    for link in db.list_links(conn, product["id"]):
        comparison.offers.append(_store_offer(conn, link, product["manufacturer_code"]))

    # Cheapest first; stores without a price go to the end.
    comparison.offers.sort(key=lambda offer: (offer.price is None, offer.price or 0))
    return comparison


def compare_all(conn: sqlite3.Connection) -> list[ProductComparison]:
    return [compare_product(conn, product) for product in db.list_products(conn)]


def best_prices(conn: sqlite3.Connection, products: list[sqlite3.Row]) -> dict[int, Decimal | None]:
    """{product id: best price} for the grid's price filter. None when there is no valid price
    (same rules as the product page: out of stock or a different product never count)."""
    prices = {}
    for product in products:
        best = compare_product(conn, product).best
        prices[product["id"]] = best.price if best else None
    return prices


def price_range(prices: dict[int, Decimal | None]) -> tuple[int, int] | None:
    """Whole-real limits for the price slider: (floor of the cheapest, ceiling of the most expensive).
    None when no product has a price, so there is nothing to filter."""
    known = [price for price in prices.values() if price is not None]
    if not known:
        return None
    cheapest, most_expensive = min(known), max(known)
    if cheapest == most_expensive:
        # Only one price (e.g. 929.99 would give 929..930): start at 0 so the slider has room to move.
        return 0, math.ceil(most_expensive)
    return math.floor(cheapest), math.ceil(most_expensive)


def _store_offer(conn: sqlite3.Connection, link: sqlite3.Row, manufacturer_code: str | None) -> StoreOffer:
    offer = StoreOffer(link_id=link["id"], store=link["store"], url=link["url"])

    priced = db.latest_price(conn, link["id"])
    if priced is not None:
        offer.price = from_cents(priced["price_cents"])
        offer.in_stock = None if priced["in_stock"] is None else bool(priced["in_stock"])
        offer.source = priced["source"]
        offer.price_checked_at = datetime.fromisoformat(priced["checked_at"])
        offer.page_title = priced["page_title"]
        if offer.source in ("auto", "capture"):  # a typed price has no page data to compare
            offer.code_matches = code_matches(
                manufacturer_code, priced["page_code"], priced["page_gtin"], priced["page_title"]
            )

    latest = db.latest_check(conn, link["id"])
    if latest is not None and latest["error"]:
        offer.error = latest["error"]
    return offer
