import sqlite3
from decimal import Decimal
from urllib.parse import unquote

import pytest

from monitor import db
from monitor.capture import bookmarklet_href, read_captured
from monitor.stores import link_key
from tests.helpers import AMAZON_URL, KABUM_URL, MAGALU_URL, ML_URL


# ---------- Bookmarklet link ----------

def test_bookmarklet_link_points_to_this_site():
    href = bookmarklet_href("http://127.0.0.1:5000/")
    code = unquote(href.removeprefix("javascript:"))

    assert href.startswith("javascript:")
    assert 'var appUrl = "http://127.0.0.1:5000/";' in code
    assert "__APP_URL__" not in code
    assert "\n" not in code and "// " not in code  # one line, comments removed
    assert '"' not in href  # quotes are encoded, so the link survives inside href="..."


# ---------- Reading what the bookmarklet sends ----------

def test_read_captured_page():
    page = read_captured({
        "url": ML_URL, "price": "929.99", "name": "  Memória Kingston  ",
        "image": "https://http2.mlstatic.com/foto.jpg", "mpn": "KF432C16BB1/16", "gtin": "",
    })
    assert page.store == "Mercado Livre"
    assert page.price == Decimal("929.99")
    assert page.name == "Memória Kingston"
    assert page.image_url == "https://http2.mlstatic.com/foto.jpg"
    assert (page.mpn, page.gtin) == ("KF432C16BB1/16", None)


@pytest.mark.parametrize(("sent", "expected"), [("R$1.855,02", Decimal("1855.02")), ("929", Decimal("929.00")), ("", None), ("grátis", None)])
def test_captured_price_formats(sent, expected):
    assert read_captured({"url": KABUM_URL, "price": sent}).price == expected


@pytest.mark.parametrize("image", ["javascript:alert(1)", "data:image/png;base64,AAA", "/foto.jpg"])
def test_only_http_images_are_accepted(image):
    assert read_captured({"url": KABUM_URL, "image": image}).image_url is None


def test_long_texts_are_cut():
    assert len(read_captured({"url": KABUM_URL, "name": "x" * 5000}).name) == 300


@pytest.mark.parametrize("url", ["", "chrome://settings", "javascript:alert(1)"])
def test_invalid_url_is_rejected(url):
    with pytest.raises(ValueError):
        read_captured({"url": url, "price": "10"})


# ---------- Recognizing the same page written differently ----------

@pytest.mark.parametrize(
    ("a", "b"),
    [
        (AMAZON_URL, "https://amazon.com.br/Kingston-Fury/dp/B097K2MRS3/ref=sr_1_1?keywords=ram&th=1"),
        (MAGALU_URL, "https://www.magazineluiza.com.br/memoria-kingston/p/gd5ak43hk3/in/mram/"),
        (ML_URL, "https://www.mercadolivre.com.br/outro-titulo/p/MLB18623867?pdp_filters=item_id#reco"),
        (KABUM_URL, KABUM_URL + "/?utm_source=x#avaliacoes"),
    ],
)
def test_link_key_matches_same_page(a, b):
    assert link_key(a) == link_key(b)


def test_link_key_distinguishes_products():
    assert link_key(AMAZON_URL) != link_key("https://www.amazon.com.br/dp/B097K3WV9J")
    assert link_key(KABUM_URL) != link_key("https://www.kabum.com.br/produto/402907/outra")


def test_find_links_for_url(conn):
    from tests.helpers import ELECTRONICS_ID

    product_id = db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[AMAZON_URL, KABUM_URL])
    found = db.find_links_for_url(conn, "https://www.amazon.com.br/x/dp/B097K2MRS3?th=1")
    assert [(row["store"], row["product_id"], row["product_name"]) for row in found] == [("Amazon", product_id, "RAM")]


# ---------- Migration: old databases only accepted 'auto' / 'manual' ----------

OLD_PRICE_CHECKS = """
CREATE TABLE price_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id     INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    checked_at  TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ('auto', 'manual')),
    price_cents INTEGER,
    in_stock    INTEGER,
    page_title  TEXT,
    page_code   TEXT,
    page_gtin   TEXT,
    error       TEXT
);
CREATE INDEX idx_price_checks_link ON price_checks (link_id, checked_at);
"""


def test_migration_keeps_history_and_allows_capture(tmp_path):
    path = tmp_path / "old.db"
    # A database as it was before this feature, with some history in it.
    with sqlite3.connect(path) as old:
        schema_without_price_checks = db.SCHEMA.replace(db.PRICE_CHECKS_TABLE.format(name="price_checks"), "")
        schema_without_price_checks = schema_without_price_checks.replace(db.PRICE_CHECKS_INDEX, "")
        old.executescript(schema_without_price_checks + OLD_PRICE_CHECKS)
        old.execute("INSERT INTO categories (name, created_at) VALUES ('Eletrônicos', 'x')")
        old.execute("INSERT INTO products (category_id, name, created_at) VALUES (1, 'RAM', 'x')")
        old.execute(f"INSERT INTO links (product_id, store, url) VALUES (1, 'KaBuM!', '{KABUM_URL}')")
        old.execute("INSERT INTO price_checks (link_id, checked_at, source, price_cents) VALUES (1, '2026-01-01', 'auto', 92999)")
        old.execute("INSERT INTO price_checks (link_id, checked_at, source, error) VALUES (1, '2026-01-02', 'auto', 'bloqueou')")
        with pytest.raises(sqlite3.IntegrityError):
            old.execute("INSERT INTO price_checks (link_id, checked_at, source) VALUES (1, 'x', 'capture')")
    old.close()

    conn = db.connect(path)
    db.init_db(conn)  # runs the migration
    db.init_db(conn)  # running again does nothing

    rows = conn.execute("SELECT id, source, price_cents, error FROM price_checks ORDER BY id").fetchall()
    assert [tuple(row) for row in rows] == [(1, "auto", 92999, None), (2, "auto", None, "bloqueou")]

    db.add_price_check(conn, 1, source="capture", price=Decimal("899.90"))  # now allowed
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # turned back on
    index_names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='price_checks'")]
    assert "idx_price_checks_link" in index_names

    db.delete_product(conn, 1)  # ON DELETE CASCADE still works after the rebuild
    assert conn.execute("SELECT COUNT(*) FROM price_checks").fetchone()[0] == 0
    conn.close()
