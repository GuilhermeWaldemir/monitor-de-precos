import json
import re
from contextlib import closing
from urllib.parse import unquote

import pytest

from monitor import db
from monitor.app import create_app
from tests.helpers import (
    AMAZON_URL,
    CLOTHING_ID,
    ELECTRONICS_ID,
    KABUM_URL,
    PERFUMES_ID,
    RAM_CODE,
    TERABYTE_URL,
    read_fixture,
)
from tests.test_checker_and_compare import fake_fetch

RAM_NAME = "Memória Kingston Fury Beast 16GB DDR4 3200MHz"


def fetch_with_amazon(url):
    if url == AMAZON_URL:
        return read_fixture("amazon_kf432c16bb1-16.html")
    return fake_fetch(url)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path, fetch=fetch_with_amazon)
    app.config["TESTING"] = True
    return app.test_client()


def add_ram(client, **overrides):
    data = {
        "name": RAM_NAME,
        "category_id": str(ELECTRONICS_ID),
        "code": RAM_CODE,
        "links": f"{KABUM_URL}\n{TERABYTE_URL}",
    }
    data.update(overrides)
    return client.post("/products", data=data, follow_redirects=True)


# ---------- Grid and categories ----------

def test_home_without_products(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Nenhum produto ainda" in response.text
    for name in ("Eletrônicos", "Vestuário", "Perfumes"):
        assert name in response.text  # sidebar


def test_grid_card_has_photo_and_name_but_no_price(client):
    add_ram(client)
    response = client.get("/")

    assert RAM_NAME in response.text
    assert 'class="product-card"' in response.text
    assert "images.kabum.com.br" in response.text  # photo
    card = re.search(r'<a class="product-card".*?</a>', response.text, re.S).group()
    assert "R$" not in card  # the card itself shows no price (only the product page does)


# ---------- Price filter slider ----------

def test_grid_items_carry_best_price_for_the_slider(client):
    add_ram(client)  # KaBuM! R$ 929,99 (Terabyte fails in fake_fetch)
    page = client.get("/").text

    assert '<li data-price="929.99">' in page
    slider = re.search(r'<input class="price-range"[^>]*>', page, re.S).group()
    assert 'min="0"' in slider and 'max="930"' in slider and 'value="930"' in slider  # one price: 0..ceil
    assert "js/price-filter.js" in page


def test_slider_range_goes_from_cheapest_to_most_expensive(client):
    add_ram(client)
    client.post("/products/1/links", data={"url": AMAZON_URL})  # Amazon R$ 1.855,02 (not the best)
    add_ram(client, name="Pente de memória genérico XPTO", code="", links=AMAZON_URL, confirm="1")  # best R$ 1.855,02

    page = client.get("/").text
    slider = re.search(r'<input class="price-range"[^>]*>', page, re.S).group()
    assert 'min="929"' in slider and 'max="1856"' in slider


def test_product_without_price_has_no_data_price(client, db_path):
    add_ram(client)
    add_ram(client, name="Perfume sem preço", category_id=str(PERFUMES_ID), code="", links=TERABYTE_URL, confirm="1")

    page = client.get("/").text
    assert page.count("data-price=") == 1  # only the RAM


def test_no_slider_when_no_product_has_a_price(client):
    add_ram(client, code="", links=TERABYTE_URL)  # Terabyte is blocked in fake_fetch: no price
    page = client.get("/").text
    assert "data-price-filter" not in page
    assert "js/price-filter.js" not in page


def test_category_page_filters_products(client):
    add_ram(client)
    assert RAM_NAME in client.get(f"/categories/{ELECTRONICS_ID}").text
    perfumes = client.get(f"/categories/{PERFUMES_ID}").text
    assert RAM_NAME not in perfumes
    assert "Nenhum produto nesta categoria" in perfumes


def test_unknown_category_returns_404(client):
    assert client.get("/categories/999").status_code == 404


def icon_is_checked(html, id_prefix, icon_name):
    """True when the icon picker has this icon's radio checked."""
    return re.search(rf'id="{id_prefix}-icon-{re.escape(icon_name)}"\s+checked', html) is not None


def test_create_edit_and_delete_category(client):
    response = client.post("/categories", data={"name": "Livros", "icon": "book-open"}, follow_redirects=True)
    assert "Categoria criada." in response.text
    assert "<h1>Livros</h1>" in response.text
    assert icon_is_checked(response.text, "edit-category", "book-open")

    category_id = int(re.search(r"/categories/(\d+)/edit", response.text).group(1))
    response = client.post(
        f"/categories/{category_id}/edit", data={"name": "Livros e HQs", "icon": "gift"}, follow_redirects=True
    )
    assert "Categoria atualizada." in response.text
    assert "<h1>Livros e HQs</h1>" in response.text
    assert icon_is_checked(response.text, "edit-category", "gift")

    response = client.post(f"/categories/{category_id}/delete", follow_redirects=True)
    assert "Categoria “Livros e HQs” excluída." in response.text


def test_sidebar_new_category_form_has_icon_picker_with_default(client):
    html = client.get("/").text
    assert 'class="icon-picker"' in html
    assert icon_is_checked(html, "new-category", "tag")
    assert 'title="Livros"' in html  # accessible label of the book icon


def test_category_without_icon_field_gets_default(client):
    response = client.post("/categories", data={"name": "Livros"}, follow_redirects=True)
    assert icon_is_checked(response.text, "edit-category", "tag")


def test_invalid_icon_shows_error(client):
    response = client.post("/categories", data={"name": "Livros", "icon": "hack"}, follow_redirects=True)
    assert "Escolha um ícone da lista." in response.text
    assert '<span class="nav-label">Livros</span>' not in response.text  # not created (not in the sidebar)


def test_edit_unknown_category_returns_404(client):
    assert client.post("/categories/999/edit", data={"name": "X", "icon": "tag"}).status_code == 404


def test_every_category_icon_has_its_own_svg(client):
    from monitor.icons import CATEGORY_ICONS

    env = client.application.jinja_env
    render = env.from_string('{% from "_icons.html" import icon %}{{ icon(name) }}').render
    tag_svg = render(name="tag")
    svgs = {name: render(name=name) for name in CATEGORY_ICONS}

    assert all(svg != tag_svg for name, svg in svgs.items() if name != "tag"), "icon missing in _icons.html"
    assert len(set(svgs.values())) == len(svgs)  # no two icons share the same drawing


def test_duplicate_category_name_shows_error(client):
    response = client.post("/categories", data={"name": "perfumes"}, follow_redirects=True)
    assert "Já existe uma categoria" in response.text


def test_category_with_products_is_not_deleted(client):
    add_ram(client)
    response = client.post(f"/categories/{ELECTRONICS_ID}/delete", follow_redirects=True)
    assert "Mova ou exclua os 1 produto" in response.text
    assert "<h1>Eletrônicos</h1>" in response.text


# ---------- Search ----------

def test_search_bar_is_on_every_page(client):
    assert 'role="search"' in client.get("/").text
    assert 'role="search"' in client.get(f"/categories/{PERFUMES_ID}").text


def test_search_shows_results_and_keeps_the_query(client):
    add_ram(client)
    response = client.get("/search?q=memoria+king")

    assert response.status_code == 200
    assert "Resultados para “memoria king”" in response.text
    assert RAM_NAME in response.text
    assert 'value="memoria king"' in response.text  # the field still shows what was typed


def test_search_without_results(client):
    add_ram(client)
    response = client.get("/search?q=geladeira")
    assert "Nenhum produto encontrado" in response.text
    assert RAM_NAME not in response.text


def test_empty_search_goes_home(client):
    response = client.get("/search?q=++")
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


# ---------- Create / edit ----------

def test_new_product_form_preselects_category(client):
    response = client.get(f"/products/new?category={PERFUMES_ID}")
    assert f'<option value="{PERFUMES_ID}" selected>' in response.text


def test_adding_product_opens_product_page(client):
    response = add_ram(client)

    assert response.status_code == 200
    assert f"<h1>{RAM_NAME}</h1>" in response.text
    assert "R$ 929,99" in response.text
    assert "melhor preço" in response.text
    assert "bloqueou o acesso automático" in response.text  # Terabyte error is visible


def test_code_is_optional(client):
    response = add_ram(client, code="")
    assert "sem código" in response.text


def test_form_error_keeps_what_was_typed(client):
    response = client.post("/products", data={"name": "Minha RAM", "category_id": "", "links": KABUM_URL})

    assert response.status_code == 400
    assert "Escolha uma categoria" in response.text
    assert "Minha RAM" in response.text


def test_duplicate_code_is_blocked(client):
    add_ram(client)
    response = add_ram(client, name="Outro nome qualquer", code="kf432c16bb1-16")

    assert response.status_code == 400
    assert "Você já cadastrou um produto com esse código" in response.text
    assert "/products/1" in response.text  # link to the existing product


def test_similar_name_asks_for_confirmation(client):
    add_ram(client)
    response = add_ram(client, name="Memoria Kingston Fury Beast 16GB", code="")

    assert "Você já tem produtos parecidos" in response.text
    assert "Salvar mesmo assim" in response.text
    assert len(db_products(client)) == 1  # nothing saved yet

    response = add_ram(client, name="Memoria Kingston Fury Beast 16GB", code="", confirm="1")
    assert "<h1>Memoria Kingston Fury Beast 16GB</h1>" in response.text
    assert len(db_products(client)) == 2


def test_edit_product(client):
    add_ram(client)
    response = client.post(
        "/products/1/edit",
        data={"name": "Minha RAM", "category_id": str(CLOTHING_ID), "code": ""},
        follow_redirects=True,
    )
    assert "Produto atualizado." in response.text
    assert "<h1>Minha RAM</h1>" in response.text
    assert "Vestuário" in response.text


# ---------- Product page ----------

def test_product_page_shows_similar_products(client):
    add_ram(client)
    add_ram(client, name="Memória Kingston Fury Beast 16GB DDR4 RGB", code="", confirm="1")

    response = client.get("/products/1")
    assert "Produtos parecidos na sua lista" in response.text
    assert "Memória Kingston Fury Beast 16GB DDR4 RGB" in response.text


def test_add_source_checks_only_the_new_link(client):
    add_ram(client)
    response = client.post("/products/1/links", data={"url": AMAZON_URL}, follow_redirects=True)

    assert "Amazon: R$ 1.855,02" in response.text
    assert "KaBuM!: R$ 929,99" not in response.text  # the other sources were not checked again


def test_add_invalid_or_duplicate_source(client):
    add_ram(client)
    assert "Link inválido" in client.post("/products/1/links", data={"url": "amazon"}, follow_redirects=True).text
    assert "já é uma fonte" in client.post("/products/1/links", data={"url": KABUM_URL}, follow_redirects=True).text


def test_remove_source(client):
    add_ram(client)
    response = client.post("/links/2/delete", follow_redirects=True)
    assert "Fonte Terabyte removida." in response.text


def test_manual_price(client):
    add_ram(client)
    response = client.post("/links/2/manual-price", data={"price": "R$ 899,90"}, follow_redirects=True)
    assert "Preço da Terabyte salvo: R$ 899,90" in response.text


def test_manual_price_invalid(client):
    add_ram(client)
    response = client.post("/links/2/manual-price", data={"price": "barato"}, follow_redirects=True)
    assert "Preço inválido" in response.text


def test_chart_needs_two_check_times(client, db_path):
    add_ram(client)
    assert "O gráfico aparece a partir de 2 verificações" in client.get("/products/1").text

    # Simulate an older check, one day before.
    with closing(db.connect(db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO price_checks (link_id, checked_at, source, price_cents) VALUES (1, '2026-01-01T10:00:00', 'auto', 99990)"
        )

    page = client.get("/products/1").text
    chart = json.loads(re.search(r'id="price-chart-data">(.*?)</script>', page, re.S).group(1))
    assert chart["labels"][0] == "01/01 10:00"
    assert chart["series"][0] == {"store": "KaBuM!", "prices": ["999.90", "929.99"]}
    assert "chart.umd.min.js" in page
    assert "Ver dados em tabela" in page


def test_delete_product_goes_back_to_its_category(client):
    add_ram(client)
    response = client.post("/products/1/delete", follow_redirects=True)
    assert "foi removido" in response.text
    assert "<h1>Eletrônicos</h1>" in response.text


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/products/999"),
        ("get", "/products/999/edit"),
        ("post", "/products/999/check"),
        ("post", "/products/999/links"),
        ("post", "/links/999/delete"),
        ("post", "/links/999/manual-price"),
    ],
)
def test_unknown_ids_return_404(client, method, url):
    assert getattr(client, method)(url).status_code == 404


# ---------- Settings ----------

def test_default_pages_use_auto_theme(client):
    assert 'data-theme="auto"' in client.get("/").text


def test_default_pages_use_default_font(client):
    assert 'data-font="default"' in client.get("/").text


def test_sidebar_has_settings_link(client):
    assert 'href="/settings"' in client.get("/").text


def test_settings_page_shows_the_three_options_with_current_one_checked(client):
    response = client.get("/settings").text
    for label in ("Automático", "Claro", "Escuro"):
        assert label in response

    assert response.count('type="radio" name="theme"') == 3
    auto_input = re.search(r'name="theme" value="auto"[^>]*>', response).group()
    assert "checked" in auto_input


def test_settings_page_shows_the_three_font_options_with_current_one_checked(client):
    response = client.get("/settings").text
    for label in ("Padrão", "Nunito Sans + Bowlby One", "Oswald + Indie Flower"):
        assert label in response

    assert response.count('type="radio" name="font"') == 3
    default_input = re.search(r'name="font" value="default"[^>]*>', response).group()
    assert "checked" in default_input


def test_saving_a_theme_redirects_and_applies_it_everywhere(client):
    response = client.post("/settings", data={"theme": "dark"}, follow_redirects=True)
    assert "Configurações salvas." in response.text
    assert 'data-theme="dark"' in response.text
    assert 'data-theme="dark"' in client.get("/").text


def test_saving_theme_and_font_together_applies_both_everywhere(client):
    response = client.post(
        "/settings", data={"theme": "dark", "font": "nunito-bowlby"}, follow_redirects=True
    )
    assert "Configurações salvas." in response.text
    assert 'data-theme="dark"' in response.text
    assert 'data-font="nunito-bowlby"' in response.text

    page = client.get("/").text
    assert 'data-theme="dark"' in page
    assert 'data-font="nunito-bowlby"' in page


def test_saving_an_invalid_theme_is_rejected(client):
    response = client.post("/settings", data={"theme": "purple"})
    assert response.status_code == 400
    assert "Opção inválida para tema." in response.text
    assert 'data-theme="auto"' in client.get("/").text  # nothing was saved


def test_posting_only_theme_does_not_reset_a_previously_saved_font(client):
    client.post("/settings", data={"theme": "auto", "font": "oswald-indie"})
    response = client.post("/settings", data={"theme": "dark"}, follow_redirects=True)

    assert 'data-theme="dark"' in response.text
    assert 'data-font="oswald-indie"' in response.text  # untouched


def test_card_glow_is_on_by_default_and_its_script_is_loaded(client):
    page = client.get("/").text
    assert 'data-card-glow="on"' in page
    assert "js/card-glow.js" in page


def test_settings_page_has_card_glow_switch_checked_by_default(client):
    page = client.get("/settings").text
    switch = re.search(r'<input class="switch"[^>]*>', page).group()
    assert 'name="card_glow"' in switch and "checked" in switch
    assert 'type="hidden" name="card_glow" value="off"' in page  # sent when the switch is off


def test_turning_card_glow_off_and_on_again(client):
    # Switch off: the browser only sends the hidden field.
    client.post("/settings", data={"theme": "auto", "card_glow": "off"})
    assert 'data-card-glow="off"' in client.get("/").text

    # Switch on: the browser sends the hidden "off" AND the checkbox "on" — the last one wins.
    client.post("/settings", data={"theme": "auto", "card_glow": ["off", "on"]})
    assert 'data-card-glow="on"' in client.get("/").text


def test_invalid_card_glow_value_is_rejected(client):
    response = client.post("/settings", data={"card_glow": "maybe"})
    assert response.status_code == 400
    assert "Opção inválida para brilho nos cards." in response.text


def test_category_page_has_dot_banner_with_its_icon(client):
    page = client.get(f"/categories/{ELECTRONICS_ID}").text
    banner = re.search(r"<div class=\"dot-banner\".*?</div>", page, re.S).group()
    cpu_svg = client.application.jinja_env.from_string(
        '{% from "_icons.html" import icon %}{{ icon("cpu", 100) }}'
    ).render()
    assert cpu_svg in banner  # the Eletrônicos icon is what the dots will draw
    assert "js/dot-transition.js" in page


def test_all_products_page_banner_uses_grid_icon(client):
    grid_svg = client.application.jinja_env.from_string(
        '{% from "_icons.html" import icon %}{{ icon("grid", 100) }}'
    ).render()
    assert grid_svg in client.get("/").text


def test_search_page_has_no_dot_banner(client):
    add_ram(client)
    page = client.get("/search?q=kingston").text
    assert "data-dot-banner" not in page
    assert "js/dot-transition.js" not in page


def test_turning_category_animation_off_removes_banner(client):
    client.post("/settings", data={"category_animation": "off"})
    page = client.get(f"/categories/{ELECTRONICS_ID}").text
    assert "data-dot-banner" not in page
    assert "js/dot-transition.js" not in page


# ---------- "Capturar preço" bookmarklet ----------

ML_PAGE = "https://www.mercadolivre.com.br/memoria-kingston/p/MLB18623867?pdp_filters=item_id"


def test_settings_page_has_bookmarklet_pointing_to_this_site(client):
    page = client.get("/settings").text
    href = re.search(r'<a class="button button-ghost bookmarklet" href="([^"]+)"', page).group(1)
    assert href.startswith("javascript:")
    assert 'var appUrl = "http://localhost/";' in unquote(href)  # the test client's host


def test_capture_page_recognizes_registered_link(client):
    add_ram(client, links=f"{KABUM_URL}\nhttps://www.mercadolivre.com.br/x/p/MLB18623867")
    response = client.get("/capture", query_string={
        "url": ML_PAGE, "price": "899.90", "name": "Memória Kingston KF432C16BB1/16", "mpn": "KF432C16BB1/16",
    })

    assert response.status_code == 200
    assert "Mercado Livre" in response.text
    assert 'value="R$ 899,90"' in response.text
    assert RAM_NAME in response.text
    assert "código confere" in response.text
    assert 'name="link_id"' in response.text


def test_capture_page_for_unknown_page_offers_products_and_new_product(client):
    add_ram(client)
    response = client.get("/capture", query_string={"url": ML_PAGE, "price": "", "name": "Algo novo"})

    assert 'name="product_id"' in response.text  # choose an existing product
    assert "Cadastrar como novo produto" in response.text
    assert "Não foi possível ler o preço" in response.text


def test_capture_page_with_invalid_url(client):
    response = client.get("/capture", query_string={"url": "javascript:alert(1)"})
    assert response.status_code == 400
    assert "link de produto válido" in response.text


def test_saving_capture_on_registered_link_becomes_best_price(client):
    add_ram(client, links=f"{KABUM_URL}\nhttps://www.mercadolivre.com.br/x/p/MLB18623867")
    response = client.post("/capture", data={
        "url": ML_PAGE, "price": "R$ 899,90", "name": "Memória KF432C16BB1/16", "mpn": "KF432C16BB1/16", "link_id": "2",
    }, follow_redirects=True)

    assert "Preço da Mercado Livre capturado: R$ 899,90." in response.text
    assert "capturado da página" in response.text
    best = re.search(r'class="best-price">([^<]+)<', response.text).group(1)
    assert best == "R$ 899,90"


def test_saving_capture_as_new_source_of_a_product(client):
    add_ram(client)
    response = client.post("/capture", data={"url": ML_PAGE, "price": "899,90", "product_id": "1"}, follow_redirects=True)
    assert "Preço da Mercado Livre capturado" in response.text
    assert "Mercado Livre" in response.text

    # Capturing the same page again reuses that source instead of failing as a duplicate.
    response = client.post("/capture", data={"url": ML_PAGE + "#x", "price": "880,00", "product_id": "1"}, follow_redirects=True)
    assert "capturado: R$ 880,00" in response.text


def test_saving_capture_errors(client):
    add_ram(client)
    no_price = client.post("/capture", data={"url": ML_PAGE, "price": "", "product_id": "1"})
    assert no_price.status_code == 400 and "Informe um preço válido" in no_price.text

    no_product = client.post("/capture", data={"url": ML_PAGE, "price": "10"})
    assert no_product.status_code == 400 and "Escolha o produto" in no_product.text

    wrong_link = client.post("/capture", data={"url": ML_PAGE, "price": "10", "link_id": "1"})  # link 1 is KaBuM!
    assert wrong_link.status_code == 400 and "não corresponde" in wrong_link.text


def test_new_product_form_can_be_prefilled(client):
    page = client.get("/products/new", query_string={"name": "RAM nova", "code": "ABC-1", "links": ML_PAGE}).text
    assert 'value="RAM nova"' in page and 'value="ABC-1"' in page
    assert "MLB18623867" in page


def db_products(client):
    with closing(db.connect(client.application.config["DB_PATH"])) as conn:
        return db.list_products(conn)
