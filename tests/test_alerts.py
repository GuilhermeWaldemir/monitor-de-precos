from decimal import Decimal

import pytest

from monitor import alerts, db
from tests.helpers import ELECTRONICS_ID, KABUM_URL, TERABYTE_URL


@pytest.fixture
def product_id(conn):
    return db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL, TERABYTE_URL])


def save_price(conn, product_id, price, link_index=0):
    """A new price for one of the product's stores (as a manually informed price)."""
    link = db.list_links(conn, product_id)[link_index]
    db.add_price_check(conn, link["id"], source="manual", price=Decimal(price))


def test_first_price_only_sets_the_reference(conn, product_id):
    save_price(conn, product_id, "1000.00")

    assert alerts.check_product_for_drop(conn, product_id) is None
    assert db.get_alert_reference(conn, product_id) == Decimal("1000.00")
    assert db.list_price_alerts(conn, product_id) == []


def test_product_without_price_is_ignored(conn, product_id):
    assert alerts.check_product_for_drop(conn, product_id) is None
    assert db.get_alert_reference(conn, product_id) is None


def test_small_drop_does_not_warn(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)

    save_price(conn, product_id, "970.00")  # 3%
    assert alerts.check_product_for_drop(conn, product_id) is None
    assert db.get_alert_reference(conn, product_id) == Decimal("1000.00")  # reference kept


def test_small_drops_add_up(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)

    save_price(conn, product_id, "980.00")  # 2%: nothing
    assert alerts.check_product_for_drop(conn, product_id) is None

    save_price(conn, product_id, "960.00")  # 4% from the original reference: warns
    drop = alerts.check_product_for_drop(conn, product_id)
    assert drop is not None
    assert (drop.old_price, drop.new_price) == (Decimal("1000.00"), Decimal("960.00"))


def test_drop_of_exactly_four_percent_warns(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)
    save_price(conn, product_id, "960.00")

    drop = alerts.check_product_for_drop(conn, product_id)
    assert drop.percent == Decimal("4.0")
    assert drop.difference == Decimal("40.00")
    assert drop.store == "KaBuM!"
    assert drop.product_name == "RAM"


def test_alert_is_saved_and_the_new_price_becomes_the_reference(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)
    save_price(conn, product_id, "900.00")
    alerts.check_product_for_drop(conn, product_id)

    [alert] = db.list_price_alerts(conn, product_id)
    assert (alert["old_price_cents"], alert["new_price_cents"], alert["store"]) == (100000, 90000, "KaBuM!")
    assert alert["emailed_at"] is None  # the e-mail is sent in the next step
    assert db.get_alert_reference(conn, product_id) == Decimal("900.00")

    # Checking again without a new price must not warn twice.
    assert alerts.check_product_for_drop(conn, product_id) is None


def test_price_going_up_raises_the_reference(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)

    save_price(conn, product_id, "1200.00")
    assert alerts.check_product_for_drop(conn, product_id) is None
    assert db.get_alert_reference(conn, product_id) == Decimal("1200.00")

    save_price(conn, product_id, "1140.00")  # 5% below the new reference
    assert alerts.check_product_for_drop(conn, product_id).percent == Decimal("5.0")


def test_a_cheaper_store_counts_as_a_drop(conn, product_id):
    save_price(conn, product_id, "1000.00", link_index=0)  # KaBuM!
    alerts.check_product_for_drop(conn, product_id)

    save_price(conn, product_id, "900.00", link_index=1)  # Terabyte is now the best price
    drop = alerts.check_product_for_drop(conn, product_id)
    assert drop.store == "Terabyte"


def test_out_of_stock_price_is_not_used(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)

    link = db.list_links(conn, product_id)[1]
    db.add_price_check(conn, link["id"], source="auto", price=Decimal("500.00"), in_stock=False)
    assert alerts.check_product_for_drop(conn, product_id) is None


def test_recent_drops_newest_first(conn, product_id):
    product = db.get_product(conn, product_id)
    for price in ["1000.00", "900.00", "800.00"]:
        save_price(conn, product_id, price)
        alerts.check_product_for_drop(conn, product_id)

    drops = alerts.recent_drops(conn, product)
    assert [str(drop.new_price) for drop in drops] == ["800.00", "900.00"]
    assert drops[0].created_at is not None
    assert drops[0].percent == Decimal("11.1")  # 900 -> 800


def test_deleting_the_product_deletes_its_alerts(conn, product_id):
    save_price(conn, product_id, "1000.00")
    alerts.check_product_for_drop(conn, product_id)
    save_price(conn, product_id, "900.00")
    alerts.check_product_for_drop(conn, product_id)

    db.delete_product(conn, product_id)
    assert conn.execute("SELECT COUNT(*) FROM price_alerts").fetchone()[0] == 0


def test_old_database_gets_the_reference_column(tmp_path):
    """A database created before this feature keeps its data and gains the new column."""
    path = tmp_path / "old.db"
    conn = db.connect(path)
    conn.executescript(db.SCHEMA)
    with conn:
        conn.execute("ALTER TABLE products DROP COLUMN alert_reference_cents")
        conn.execute("INSERT INTO categories (name, created_at) VALUES ('Eletrônicos', 'x')")
        conn.execute("INSERT INTO products (category_id, name, created_at) VALUES (1, 'RAM', 'x')")

    db.init_db(conn)  # runs the migration

    columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
    assert "alert_reference_cents" in columns
    assert db.get_product(conn, 1)["name"] == "RAM"
    db.set_alert_reference(conn, 1, Decimal("10.00"))
    assert db.get_alert_reference(conn, 1) == Decimal("10.00")
    conn.close()
