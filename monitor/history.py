"""Prepares the price history for the line chart and its data table."""

import sqlite3
from datetime import datetime

from monitor.prices import from_cents

LABEL_FORMAT = "%d/%m %H:%M"


def chart_data(rows: list[sqlite3.Row]) -> dict:
    """Turn db.price_history rows into chart data.

    {"labels": ["14/09 16:58", ...],
     "series": [{"store": "KaBuM!", "prices": ["929.99", None, ...]}, ...]}

    - One label per check time, oldest first (checks in the same minute share a label).
    - One series per store; None where the store has no price at that time.
    - Prices are text ("929.99"), so they never become float in Python.
    """
    labels: list[str] = []
    prices_by_store: dict[str, dict[str, str]] = {}

    for row in rows:
        label = datetime.fromisoformat(row["checked_at"]).strftime(LABEL_FORMAT)
        if label not in labels:
            labels.append(label)
        # Same store twice in one label: the later check wins (rows come oldest first).
        prices_by_store.setdefault(row["store"], {})[label] = str(from_cents(row["price_cents"]))

    series = [
        {"store": store, "prices": [prices.get(label) for label in labels]}
        for store, prices in prices_by_store.items()
    ]
    return {"labels": labels, "series": series}
