from decimal import Decimal

import pytest

from monitor import db
from tests.helpers import CLOTHING_ID, ELECTRONICS_ID, KABUM_URL, ML_URL, PERFUMES_ID, RAM_CODE, TERABYTE_URL


def add_ram(conn, **overrides) -> int:
    fields = {
        "name": "Kingston Fury Beast 16GB",
        "category_id": ELECTRONICS_ID,
        "urls": [KABUM_URL, ML_URL, TERABYTE_URL],
        "manufacturer_code": RAM_CODE,
    }
    fields.update(overrides)
    return db.create_product(conn, **fields)


# ---------- Categories ----------

def test_default_categories_are_created_once(conn):
    db.init_db(conn)  # running again must not duplicate them
    names = [c["name"] for c in db.list_categories_with_counts(conn)]
    assert names == ["Eletrônicos", "Vestuário", "Perfumes"]


def test_category_counts_include_empty_categories(conn):
    add_ram(conn)
    counts = {c["name"]: c["product_count"] for c in db.list_categories_with_counts(conn)}
    assert counts == {"Eletrônicos": 1, "Vestuário": 0, "Perfumes": 0}


def test_new_category_uses_default_icon(conn):
    category_id = db.create_category(conn, "  Livros ")
    category = db.get_category(conn, category_id)
    assert (category["name"], category["icon"]) == ("Livros", "tag")


def test_create_category_with_chosen_icon(conn):
    category_id = db.create_category(conn, "Livros", "book-open")
    assert db.get_category(conn, category_id)["icon"] == "book-open"


@pytest.mark.parametrize("icon", ["", "not-an-icon", "<svg>", "grid"])  # "grid" exists in _icons.html but isn't offered
def test_icon_outside_the_list_is_rejected_and_nothing_saved(conn, icon):
    with pytest.raises(ValueError, match="Escolha um ícone"):
        db.create_category(conn, "Livros", icon)
    assert len(db.list_categories_with_counts(conn)) == 3


def test_update_category_changes_name_and_icon(conn):
    category_id = db.create_category(conn, "Livros")
    db.update_category(conn, category_id, name="Livros e HQs", icon="book-open")
    category = db.get_category(conn, category_id)
    assert (category["name"], category["icon"]) == ("Livros e HQs", "book-open")


def test_update_category_rejects_invalid_icon(conn):
    with pytest.raises(ValueError, match="Escolha um ícone"):
        db.update_category(conn, CLOTHING_ID, name="Roupas", icon="nope")
    assert db.get_category(conn, CLOTHING_ID)["name"] == "Vestuário"  # nothing changed


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_invalid_category_name(conn, name):
    with pytest.raises(ValueError):
        db.create_category(conn, name)


def test_category_names_are_unique_ignoring_case(conn):
    with pytest.raises(ValueError, match="Já existe"):
        db.create_category(conn, "perfumes")
    with pytest.raises(ValueError, match="Já existe"):
        db.update_category(conn, CLOTHING_ID, name="PERFUMES", icon="shirt")


def test_default_categories_use_icons_from_the_list(conn):
    from monitor.icons import CATEGORY_ICONS

    assert all(c["icon"] in CATEGORY_ICONS for c in db.list_categories_with_counts(conn))


def test_category_with_products_cannot_be_deleted(conn):
    add_ram(conn)
    with pytest.raises(ValueError, match="1 produto"):
        db.delete_category(conn, ELECTRONICS_ID)
    assert db.get_category(conn, ELECTRONICS_ID) is not None


def test_empty_category_can_be_deleted(conn):
    db.delete_category(conn, CLOTHING_ID)
    assert db.get_category(conn, CLOTHING_ID) is None


# ---------- Products ----------

def test_create_product_saves_links_with_store_names(conn):
    product_id = add_ram(conn)
    stores = [link["store"] for link in db.list_links(conn, product_id)]
    assert stores == ["KaBuM!", "Mercado Livre", "Terabyte"]
    assert db.get_product(conn, product_id)["category_name"] == "Eletrônicos"


def test_code_is_optional(conn):
    product_id = add_ram(conn, manufacturer_code="   ")
    assert db.get_product(conn, product_id)["manufacturer_code"] is None


def test_create_product_ignores_blank_and_duplicate_links(conn):
    product_id = add_ram(conn, urls=[KABUM_URL, "  ", KABUM_URL])
    assert len(db.list_links(conn, product_id)) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"category_id": 999},
        {"category_id": None},
        {"urls": []},
        {"urls": [KABUM_URL, "not a link"]},
    ],
)
def test_invalid_product_saves_nothing(conn, overrides):
    with pytest.raises(ValueError):
        add_ram(conn, **overrides)
    assert db.list_products(conn) == []


def test_list_products_by_category(conn):
    add_ram(conn)
    db.create_product(conn, name="Perfume", category_id=PERFUMES_ID, urls=[ML_URL])

    assert [p["name"] for p in db.list_products(conn, PERFUMES_ID)] == ["Perfume"]
    assert len(db.list_products(conn)) == 2


def test_update_product(conn):
    product_id = add_ram(conn)
    db.update_product(conn, product_id, name="Minha RAM", category_id=CLOTHING_ID, manufacturer_code="")

    product = db.get_product(conn, product_id)
    assert (product["name"], product["category_name"], product["manufacturer_code"]) == ("Minha RAM", "Vestuário", None)


def test_find_product_by_code_ignores_case_and_separators(conn):
    product_id = add_ram(conn)
    assert db.find_product_by_code(conn, "kf432c16bb1-16")["id"] == product_id
    assert db.find_product_by_code(conn, "KF432C16BB/16") is None
    assert db.find_product_by_code(conn, "kf432c16bb1-16", exclude_id=product_id) is None
    assert db.find_product_by_code(conn, "") is None


def test_deleting_product_removes_links_and_history(conn):
    product_id = add_ram(conn)
    link = db.list_links(conn, product_id)[0]
    db.add_price_check(conn, link["id"], source="manual", price=Decimal("10.00"))
    db.delete_product(conn, product_id)

    assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM price_checks").fetchone()[0] == 0


# ---------- Links ----------

def test_add_and_delete_link(conn):
    product_id = add_ram(conn, urls=[KABUM_URL])
    link_id = db.add_link(conn, product_id, f"  {TERABYTE_URL} ")
    assert db.get_link(conn, link_id)["store"] == "Terabyte"

    db.delete_link(conn, link_id)
    assert [link["store"] for link in db.list_links(conn, product_id)] == ["KaBuM!"]


def test_add_link_rejects_duplicate_and_invalid(conn):
    product_id = add_ram(conn, urls=[KABUM_URL])
    with pytest.raises(ValueError, match="já é uma fonte"):
        db.add_link(conn, product_id, KABUM_URL)
    with pytest.raises(ValueError):
        db.add_link(conn, product_id, "kabum")


# ---------- History ----------

def test_price_history_ignores_failures_and_is_oldest_first(conn):
    product_id = add_ram(conn)
    kabum, ml, _ = db.list_links(conn, product_id)
    db.add_price_check(conn, kabum["id"], source="auto", price=Decimal("950.00"))
    db.add_price_check(conn, ml["id"], source="auto", error="bloqueado")
    db.add_price_check(conn, kabum["id"], source="auto", price=Decimal("929.99"))

    rows = db.price_history(conn, product_id)
    assert [(r["store"], r["price_cents"]) for r in rows] == [("KaBuM!", 95000), ("KaBuM!", 92999)]
