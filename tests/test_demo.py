"""Modo demonstração: dados de exemplo e um site que ninguém consegue alterar."""

import pytest

from monitor import compare, db, demo
from monitor.app import create_app
from tests.helpers import TEST_EMAIL, TEST_PASSWORD, fake_fetch


# ---------- a chave liga/desliga ----------


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "sim", " on "])
def test_these_values_turn_the_demo_on(value):
    assert demo.is_on({demo.VARIABLE: value}) is True


@pytest.mark.parametrize("value", ["", "0", "false", "nao", "qualquer-coisa"])
def test_everything_else_leaves_it_off(value):
    assert demo.is_on({demo.VARIABLE: value}) is False


def test_it_is_off_when_the_variable_does_not_exist():
    assert demo.is_on({}) is False


# ---------- os dados de exemplo ----------


def test_it_fills_an_empty_database(conn):
    assert demo.fill_if_empty(conn) is True
    products = db.list_products(conn)
    assert len(products) == len(demo.EXAMPLE_PRODUCTS)
    assert all(product["name"].endswith("(exemplo)") for product in products)


def test_running_it_again_does_not_duplicate(conn):
    demo.fill_if_empty(conn)
    assert demo.fill_if_empty(conn) is False
    assert len(db.list_products(conn)) == len(demo.EXAMPLE_PRODUCTS)


def test_every_product_has_a_chart_worth_of_history(conn):
    demo.fill_if_empty(conn)
    for product in db.list_products(conn):
        dates = {row["checked_at"] for row in db.price_history(conn, product["id"])}
        assert len(dates) >= 2  # com menos de 2 datas o gráfico nem aparece


def test_the_cheapest_offer_out_of_stock_is_not_the_best_price(conn):
    """O perfume de exemplo existe para mostrar essa regra funcionando."""
    demo.fill_if_empty(conn)
    perfume = next(p for p in db.list_products(conn) if "Perfume" in p["name"])
    comparison = compare.compare_product(conn, db.get_product(conn, perfume["id"]))
    cheapest = min(o.price for o in comparison.offers if o.price is not None)
    assert comparison.best is not None
    assert comparison.best.price > cheapest


def test_a_failed_check_keeps_the_reason(conn):
    demo.fill_if_empty(conn)
    errors = conn.execute("SELECT error FROM price_checks WHERE error IS NOT NULL").fetchall()
    assert errors, "um exemplo precisa mostrar uma loja que bloqueou"


# ---------- o site em modo demonstração ----------


@pytest.fixture
def demo_client(db_path, mailbox, monkeypatch):
    monkeypatch.setenv(demo.VARIABLE, "1")
    app = create_app(db_path=db_path, fetch=fake_fetch, send_email=mailbox)
    app.config["TESTING"] = True
    return app.test_client()


def test_the_banner_warns_the_visitor(demo_client):
    page = demo_client.get("/").get_data(as_text=True)
    assert "Modo demonstração" in page
    assert "exemplos inventados" in page


def test_the_products_are_already_there(demo_client):
    page = demo_client.get("/").get_data(as_text=True)
    assert "Memória RAM 16GB DDR4 3200MHz (exemplo)" in page


def test_nobody_can_sign_up_or_change_anything(demo_client):
    answer = demo_client.post(
        "/signup",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD},
        follow_redirects=True,
    )
    assert "demonstração" in answer.get_data(as_text=True)
    assert db.count_users(db.connect(demo_client.application.config["DB_PATH"])) == 0


def test_the_refused_post_changes_nothing(demo_client):
    demo_client.post("/categories", data={"name": "Jardinagem"}, follow_redirects=True)
    assert "Jardinagem" not in demo_client.get("/").get_data(as_text=True)


def test_the_login_links_are_hidden(demo_client):
    page = demo_client.get("/").get_data(as_text=True)
    assert "Criar conta" not in page


def test_the_product_page_still_opens(demo_client):
    conn = db.connect(demo_client.application.config["DB_PATH"])
    product = db.list_products(conn)[0]
    answer = demo_client.get(f"/products/{product['id']}")
    assert answer.status_code == 200


def test_without_the_variable_nothing_changes(client):
    """O site normal continua sem faixa e sem dados de exemplo."""
    page = client.get("/").get_data(as_text=True)
    assert "Modo demonstração" not in page
    assert "(exemplo)" not in page
