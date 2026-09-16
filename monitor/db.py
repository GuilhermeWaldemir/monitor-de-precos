"""SQLite database: categories, products, store links and price history."""

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from monitor.icons import CATEGORY_ICONS, DEFAULT_CATEGORY_ICON
from monitor.matching import normalize_code
from monitor.prices import from_cents, to_cents
from monitor.stores import link_key, store_name_from_url

DEFAULT_DB_PATH = Path("data") / "monitor.db"

# Created the first time the database is set up. Icon names come from monitor/icons.py.
DEFAULT_CATEGORIES = [("Eletrônicos", "cpu"), ("Vestuário", "shirt"), ("Perfumes", "droplet")]
MAX_CATEGORY_NAME = 40

# Kept apart from SCHEMA because the migration below needs to create this table under another name.
# source: 'auto' = read by the program, 'manual' = typed by the user,
#         'capture' = sent by the "Capturar preço" bookmarklet from a page the user had open.
PRICE_CHECKS_TABLE = """
-- One row per check. Nothing is overwritten: this table is the history.
CREATE TABLE IF NOT EXISTS {name} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id     INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
    checked_at  TEXT NOT NULL,
    source      TEXT NOT NULL CHECK (source IN ('auto', 'manual', 'capture')),
    price_cents INTEGER,  -- NULL when the check failed
    in_stock    INTEGER,  -- 1 = yes, 0 = no, NULL = unknown
    page_title  TEXT,
    page_code   TEXT,     -- manufacturer code the page declares (JSON-LD "mpn")
    page_gtin   TEXT,     -- EAN/barcode the page declares (JSON-LD "gtin13"...)
    error       TEXT      -- why it failed; NULL when it worked
);
"""
PRICE_CHECKS_COLUMNS = (
    "id, link_id, checked_at, source, price_cents, in_stock, page_title, page_code, page_gtin, error"
)
PRICE_CHECKS_INDEX = "CREATE INDEX IF NOT EXISTS idx_price_checks_link ON price_checks (link_id, checked_at);"

SCHEMA = """
-- Accounts. Only the password *hash* is stored, never the password itself.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE COLLATE NOCASE,  -- NOCASE: "perfumes" = "Perfumes"
    icon       TEXT NOT NULL DEFAULT 'tag',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id            INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    name                   TEXT NOT NULL,
    manufacturer_code      TEXT,  -- manufacturer code or EAN; optional
    image_url              TEXT,
    created_at             TEXT NOT NULL,
    -- Price the next drop is measured against (monitor/alerts.py). NULL until the first price.
    alert_reference_cents  INTEGER
);

-- One row per price drop big enough to warn about (4% or more).
CREATE TABLE IF NOT EXISTS price_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL,
    old_price_cents INTEGER NOT NULL,  -- the reference price before the drop
    new_price_cents INTEGER NOT NULL,
    store           TEXT NOT NULL,     -- store with the new best price
    emailed_at      TEXT               -- NULL while the e-mail has not been sent
);

CREATE TABLE IF NOT EXISTS links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    store      TEXT NOT NULL,
    url        TEXT NOT NULL,
    UNIQUE (product_id, url)
);

{price_checks_table}

-- One row per option (e.g. "theme"). Options with no saved row use the default in monitor/settings.py.
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products (category_id);
CREATE INDEX IF NOT EXISTS idx_price_alerts_product ON price_alerts (product_id, created_at);
{price_checks_index}
""".format(
    price_checks_table=PRICE_CHECKS_TABLE.format(name="price_checks"),
    price_checks_index=PRICE_CHECKS_INDEX,
)


def connect(path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # access columns by name: row["name"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite leaves this off by default
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate_allow_capture_source(conn)
    _migrate_add_alert_reference(conn)
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        with conn:
            conn.executemany(
                "INSERT INTO categories (name, icon, created_at) VALUES (?, ?, ?)",
                [(name, icon, now()) for name, icon in DEFAULT_CATEGORIES],
            )


def _migrate_allow_capture_source(conn: sqlite3.Connection) -> None:
    """Migration: databases created before the bookmarklet only accept source 'auto'/'manual'.

    SQLite cannot change a CHECK constraint of an existing table, so the table is rebuilt
    (the official SQLite recipe): create the new table, copy every row, drop the old one,
    rename the new one. It all runs in one transaction: either the history is fully copied
    or nothing changes. Does nothing when the table already accepts 'capture'.
    """
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'price_checks'"
    ).fetchone()[0]
    if "'capture'" in table_sql:
        return

    conn.execute("PRAGMA foreign_keys = OFF")  # only works outside a transaction
    try:
        conn.execute("BEGIN")
        conn.execute(PRICE_CHECKS_TABLE.format(name="price_checks_new"))
        conn.execute(
            f"INSERT INTO price_checks_new ({PRICE_CHECKS_COLUMNS}) SELECT {PRICE_CHECKS_COLUMNS} FROM price_checks"
        )
        conn.execute("DROP TABLE price_checks")  # also drops its index
        conn.execute("ALTER TABLE price_checks_new RENAME TO price_checks")
        conn.execute(PRICE_CHECKS_INDEX)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_add_alert_reference(conn: sqlite3.Connection) -> None:
    """Migration: databases created before the price alerts have no `alert_reference_cents`.

    Adding a column is the one table change SQLite does directly (`ALTER TABLE ADD COLUMN`),
    so no table rebuild is needed here — unlike changing a CHECK constraint.
    """
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(products)")]
    if "alert_reference_cents" not in columns:
        with conn:
            conn.execute("ALTER TABLE products ADD COLUMN alert_reference_cents INTEGER")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- Users ----------

def create_user(conn: sqlite3.Connection, email: str, password_hash: str) -> int:
    """Save a new account. Raises ValueError when the e-mail is already taken."""
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, now()),
            )
    except sqlite3.IntegrityError:
        raise ValueError("Já existe uma conta com esse e-mail.") from None
    return cursor.lastrowid


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    # The column is COLLATE NOCASE, so "Ana@x.com" finds "ana@x.com".
    return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def count_users(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ---------- Categories ----------

def list_categories_with_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every category with how many products it has (0 included, thanks to LEFT JOIN)."""
    return conn.execute(
        """
        SELECT c.id, c.name, c.icon, COUNT(p.id) AS product_count
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        GROUP BY c.id
        ORDER BY c.id
        """
    ).fetchall()


def get_category(conn: sqlite3.Connection, category_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()


def create_category(conn: sqlite3.Connection, name: str, icon: str = DEFAULT_CATEGORY_ICON) -> int:
    name = _clean_category_name(name)
    _check_category_icon(icon)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO categories (name, icon, created_at) VALUES (?, ?, ?)", (name, icon, now())
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"Já existe uma categoria chamada “{name}”.") from None
    return cursor.lastrowid


def update_category(conn: sqlite3.Connection, category_id: int, *, name: str, icon: str) -> None:
    name = _clean_category_name(name)
    _check_category_icon(icon)
    try:
        with conn:
            conn.execute(
                "UPDATE categories SET name = ?, icon = ? WHERE id = ?", (name, icon, category_id)
            )
    except sqlite3.IntegrityError:
        raise ValueError(f"Já existe uma categoria chamada “{name}”.") from None


def delete_category(conn: sqlite3.Connection, category_id: int) -> None:
    """Delete an empty category. Raises ValueError if it still has products."""
    count = conn.execute(
        "SELECT COUNT(*) FROM products WHERE category_id = ?", (category_id,)
    ).fetchone()[0]
    if count:
        plural = "produto" if count == 1 else "produtos"
        raise ValueError(f"Mova ou exclua os {count} {plural} desta categoria antes de excluí-la.")
    with conn:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))


def _clean_category_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Informe o nome da categoria.")
    if len(name) > MAX_CATEGORY_NAME:
        raise ValueError(f"O nome da categoria pode ter no máximo {MAX_CATEGORY_NAME} caracteres.")
    return name


def _check_category_icon(icon: str) -> None:
    # Allow-list: only names from monitor/icons.py, never free text typed into the form.
    if icon not in CATEGORY_ICONS:
        raise ValueError("Escolha um ícone da lista.")


# ---------- Products ----------

_PRODUCT_COLUMNS = """
    p.id, p.category_id, p.name, p.manufacturer_code, p.image_url, p.created_at,
    c.name AS category_name
"""


def create_product(
    conn: sqlite3.Connection,
    *,
    name: str,
    category_id: int,
    urls: list[str],
    manufacturer_code: str | None = None,
) -> int:
    """Save a product with its links. Returns the new product id.

    Raises ValueError if a field is invalid; nothing is saved in that case.
    """
    name = _clean_product_name(name)
    _check_category_exists(conn, category_id)
    code = _clean_code(manufacturer_code)
    urls = list(dict.fromkeys(url.strip() for url in urls if url.strip()))  # drop blanks and duplicates
    if not urls:
        raise ValueError("Informe pelo menos um link.")
    stores = [store_name_from_url(url) for url in urls]  # validates every link before saving

    with conn:  # transaction: saves everything or nothing
        cursor = conn.execute(
            "INSERT INTO products (category_id, name, manufacturer_code, created_at) VALUES (?, ?, ?, ?)",
            (category_id, name, code, now()),
        )
        product_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO links (product_id, store, url) VALUES (?, ?, ?)",
            [(product_id, store, url) for store, url in zip(stores, urls)],
        )
    return product_id


def update_product(
    conn: sqlite3.Connection,
    product_id: int,
    *,
    name: str,
    category_id: int,
    manufacturer_code: str | None,
) -> None:
    name = _clean_product_name(name)
    _check_category_exists(conn, category_id)
    with conn:
        conn.execute(
            "UPDATE products SET name = ?, category_id = ?, manufacturer_code = ? WHERE id = ?",
            (name, category_id, _clean_code(manufacturer_code), product_id),
        )


def delete_product(conn: sqlite3.Connection, product_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))


def list_products(conn: sqlite3.Connection, category_id: int | None = None) -> list[sqlite3.Row]:
    """All products, newest first; only one category when category_id is given."""
    sql = f"SELECT {_PRODUCT_COLUMNS} FROM products p JOIN categories c ON c.id = p.category_id"
    params: tuple = ()
    if category_id is not None:
        sql += " WHERE p.category_id = ?"
        params = (category_id,)
    sql += " ORDER BY p.created_at DESC, p.id DESC"
    return conn.execute(sql, params).fetchall()


def get_product(conn: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {_PRODUCT_COLUMNS} FROM products p JOIN categories c ON c.id = p.category_id WHERE p.id = ?",
        (product_id,),
    ).fetchone()


def find_product_by_code(
    conn: sqlite3.Connection, code: str | None, exclude_id: int | None = None
) -> sqlite3.Row | None:
    """Product with the same code, ignoring case and separators ("kf432c16bb1-16" = "KF432C16BB1/16")."""
    wanted = normalize_code(code or "")
    if not wanted:
        return None
    for product in list_products(conn):
        if product["id"] != exclude_id and normalize_code(product["manufacturer_code"] or "") == wanted:
            return product
    return None


def set_image_if_missing(conn: sqlite3.Connection, product_id: int, image_url: str) -> None:
    with conn:
        conn.execute(
            "UPDATE products SET image_url = ? WHERE id = ? AND image_url IS NULL",
            (image_url, product_id),
        )


def _clean_product_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Informe o nome do produto.")
    return name


def _clean_code(code: str | None) -> str | None:
    code = (code or "").strip()
    return code or None


def _check_category_exists(conn: sqlite3.Connection, category_id) -> None:
    if not isinstance(category_id, int) or get_category(conn, category_id) is None:
        raise ValueError("Escolha uma categoria.")


# ---------- Links (sources) ----------

def add_link(conn: sqlite3.Connection, product_id: int, url: str) -> int:
    """Add a store link to an existing product. Returns the new link id."""
    url = url.strip()
    store = store_name_from_url(url)  # raises ValueError for invalid links
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO links (product_id, store, url) VALUES (?, ?, ?)", (product_id, store, url)
            )
    except sqlite3.IntegrityError:
        raise ValueError("Esse link já é uma fonte deste produto.") from None
    return cursor.lastrowid


def find_links_for_url(conn: sqlite3.Connection, url: str) -> list[sqlite3.Row]:
    """Registered links that point to the same product page as `url` (see stores.link_key),
    with the product's name and code. Compared in Python because the key isn't stored."""
    wanted = link_key(url)
    rows = conn.execute(
        """
        SELECT l.*, p.name AS product_name, p.manufacturer_code
        FROM links l JOIN products p ON p.id = l.product_id
        ORDER BY l.id
        """
    ).fetchall()
    return [row for row in rows if link_key(row["url"]) == wanted]


def delete_link(conn: sqlite3.Connection, link_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))


def get_link(conn: sqlite3.Connection, link_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()


def list_links(conn: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM links WHERE product_id = ? ORDER BY id", (product_id,)).fetchall()


# ---------- Price checks ----------

def add_price_check(
    conn: sqlite3.Connection,
    link_id: int,
    *,
    source: str,
    price: Decimal | None = None,
    in_stock: bool | None = None,
    page_title: str | None = None,
    page_code: str | None = None,
    page_gtin: str | None = None,
    error: str | None = None,
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO price_checks
                (link_id, checked_at, source, price_cents, in_stock, page_title, page_code, page_gtin, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                now(),
                source,
                to_cents(price) if price is not None else None,
                None if in_stock is None else int(in_stock),
                page_title,
                page_code,
                page_gtin,
                error,
            ),
        )


def latest_check(conn: sqlite3.Connection, link_id: int) -> sqlite3.Row | None:
    """The most recent check, whether it worked or not."""
    return conn.execute(
        "SELECT * FROM price_checks WHERE link_id = ? ORDER BY checked_at DESC, id DESC LIMIT 1",
        (link_id,),
    ).fetchone()


def latest_price(conn: sqlite3.Connection, link_id: int) -> sqlite3.Row | None:
    """The most recent check that found a price."""
    return conn.execute(
        """
        SELECT * FROM price_checks
        WHERE link_id = ? AND price_cents IS NOT NULL
        ORDER BY checked_at DESC, id DESC LIMIT 1
        """,
        (link_id,),
    ).fetchone()


def price_history(conn: sqlite3.Connection, product_id: int) -> list[sqlite3.Row]:
    """Every price found for the product, oldest first, with the store name."""
    return conn.execute(
        """
        SELECT l.store, pc.checked_at, pc.price_cents, pc.source
        FROM price_checks pc
        JOIN links l ON l.id = pc.link_id
        WHERE l.product_id = ? AND pc.price_cents IS NOT NULL
        ORDER BY pc.checked_at, pc.id
        """,
        (product_id,),
    ).fetchall()


# ---------- Settings ----------

# ---------- Price alerts ----------

def get_alert_reference(conn: sqlite3.Connection, product_id: int) -> Decimal | None:
    """Price the next drop is measured against. None when the product never had a price."""
    row = conn.execute(
        "SELECT alert_reference_cents FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    if row is None or row["alert_reference_cents"] is None:
        return None
    return from_cents(row["alert_reference_cents"])


def set_alert_reference(conn: sqlite3.Connection, product_id: int, price: Decimal) -> None:
    with conn:
        conn.execute(
            "UPDATE products SET alert_reference_cents = ? WHERE id = ?", (to_cents(price), product_id)
        )


def add_price_alert(
    conn: sqlite3.Connection, product_id: int, *, old_price: Decimal, new_price: Decimal, store: str
) -> int:
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO price_alerts (product_id, created_at, old_price_cents, new_price_cents, store)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, now(), to_cents(old_price), to_cents(new_price), store),
        )
    return cursor.lastrowid


def list_price_alerts(conn: sqlite3.Connection, product_id: int, limit: int = 10) -> list[sqlite3.Row]:
    """Price drops of one product, newest first."""
    return conn.execute(
        "SELECT * FROM price_alerts WHERE product_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (product_id, limit),
    ).fetchall()


def mark_alert_emailed(conn: sqlite3.Connection, alert_id: int) -> None:
    """Remember that the e-mail for this drop went out, so it is never sent twice."""
    with conn:
        conn.execute("UPDATE price_alerts SET emailed_at = ? WHERE id = ?", (now(), alert_id))


def list_user_emails(conn: sqlite3.Connection) -> list[str]:
    """Who receives the alerts: every account (the products are shared between them)."""
    return [row["email"] for row in conn.execute("SELECT email FROM users ORDER BY id")]


def get_settings_rows(conn: sqlite3.Connection) -> dict[str, str]:
    """Every saved setting as {key: value}. Options never saved simply don't appear here."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def save_settings_rows(conn: sqlite3.Connection, items: dict[str, str]) -> None:
    """Save several settings at once, all in the same transaction (all-or-nothing).

    Saving theme and font together must not leave one saved and the other not, e.g.
    if the connection is interrupted mid-way. `executemany` runs one UPSERT per item
    inside a single `with conn:` block instead of one `with conn:` per key.
    """
    if not items:
        return
    with conn:
        conn.executemany(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            list(items.items()),
        )
