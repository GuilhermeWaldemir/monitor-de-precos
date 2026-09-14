from monitor.history import chart_data


def row(store, checked_at, price_cents):
    # db.price_history returns sqlite3.Row; a dict supports the same row["column"] access.
    return {"store": store, "checked_at": checked_at, "price_cents": price_cents}


def test_empty_history():
    assert chart_data([]) == {"labels": [], "series": []}


def test_aligns_stores_by_time_with_gaps():
    data = chart_data([
        row("KaBuM!", "2026-09-14T10:00:05", 92999),
        row("Amazon", "2026-09-14T10:00:40", 185502),  # same minute as KaBuM!: same label
        row("KaBuM!", "2026-09-15T09:30:00", 89990),
    ])

    assert data["labels"] == ["14/09 10:00", "15/09 09:30"]
    assert data["series"] == [
        {"store": "KaBuM!", "prices": ["929.99", "899.90"]},
        {"store": "Amazon", "prices": ["1855.02", None]},  # no Amazon price on 15/09
    ]


def test_prices_are_text_not_float():
    data = chart_data([row("KaBuM!", "2026-09-14T10:00:00", 10)])
    assert data["series"][0]["prices"] == ["0.10"]


def test_later_check_in_the_same_minute_wins():
    data = chart_data([
        row("KaBuM!", "2026-09-14T10:00:01", 100000),
        row("KaBuM!", "2026-09-14T10:00:59", 95000),
    ])
    assert data["series"][0]["prices"] == ["950.00"]
