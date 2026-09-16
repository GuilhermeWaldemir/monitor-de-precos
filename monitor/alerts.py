"""Price drop alerts: decides when a drop is big enough to warn the user about.

Each product keeps a *reference price* (`products.alert_reference_cents`), the last best
price the alerts looked at. After every check the new best price is compared with it:

- no reference yet (first price): just save it, nothing to compare;
- price went up: the reference goes up too, so the next drop is measured from there;
- dropped less than 4%: nothing is saved and the reference stays, so small drops add up
  (2% today and 2% tomorrow become a 4% drop and do warn);
- dropped 4% or more: save the alert and the new price becomes the reference, so the same
  drop is never announced twice.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from monitor import compare, db
from monitor.prices import from_cents

# Drop needed to warn the user, as a fraction: 0.04 = 4%.
DROP_THRESHOLD = Decimal("0.04")


@dataclass
class PriceDrop:
    product_id: int
    product_name: str
    old_price: Decimal
    new_price: Decimal
    store: str
    created_at: datetime | None = None  # filled for drops read back from the database

    @property
    def difference(self) -> Decimal:
        return self.old_price - self.new_price

    @property
    def percent(self) -> Decimal:
        """How much it dropped, in percent, with one decimal place (e.g. 5.2)."""
        return (self.difference / self.old_price * 100).quantize(Decimal("0.1"))


def check_product_for_drop(conn: sqlite3.Connection, product_id: int) -> PriceDrop | None:
    """Compare the product's current best price with its reference price.

    Returns the drop when it is worth warning about (and saves it), None otherwise.
    Call it right after new prices are saved for a product.
    """
    product = db.get_product(conn, product_id)
    if product is None:
        return None

    best = compare.compare_product(conn, product).best
    if best is None:  # no valid price (no sources, all failed, out of stock...)
        return None

    reference = db.get_alert_reference(conn, product_id)
    if reference is None or best.price > reference:
        db.set_alert_reference(conn, product_id, best.price)
        return None

    if (reference - best.price) / reference < DROP_THRESHOLD:
        return None  # small drop: keep the old reference so drops can add up

    db.set_alert_reference(conn, product_id, best.price)
    db.add_price_alert(
        conn, product_id, old_price=reference, new_price=best.price, store=best.store
    )
    return PriceDrop(
        product_id=product_id,
        product_name=product["name"],
        old_price=reference,
        new_price=best.price,
        store=best.store,
    )


def recent_drops(conn: sqlite3.Connection, product: sqlite3.Row, limit: int = 10) -> list[PriceDrop]:
    """Price drops already saved for a product, newest first (shown on the product page)."""
    return [
        PriceDrop(
            product_id=product["id"],
            product_name=product["name"],
            old_price=from_cents(row["old_price_cents"]),
            new_price=from_cents(row["new_price_cents"]),
            store=row["store"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for row in db.list_price_alerts(conn, product["id"], limit)
    ]
