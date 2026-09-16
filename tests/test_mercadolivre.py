from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from monitor import db, mercadolivre
from monitor.mercadolivre import AppCredentials, MercadoLivreError

CREDENTIALS = AppCredentials(
    client_id="123", client_secret="segredo", redirect_uri="http://127.0.0.1:5000/mercadolivre/callback"
)
CATALOG_URL = "https://www.mercadolivre.com.br/memoria-kingston/p/MLB18623867"
ITEM_URL = "https://produto.mercadolivre.com.br/MLB-1234567890-memoria-kingston-_JM"

ITEM_ANSWER = {
    "id": "MLB1234567890",
    "title": "Memória Kingston Fury Beast 16GB",
    "price": Decimal("899.90"),
    "available_quantity": 5,
    "status": "active",
    "pictures": [{"secure_url": "https://http2.mlstatic.com/foto.jpg"}],
    "attributes": [
        {"id": "BRAND", "value_name": "Kingston"},
        {"id": "GTIN", "value_name": "740617319880"},
        {"id": "MPN", "value_name": "KF432C16BB1/16"},
    ],
}
CATALOG_ANSWER = {
    "id": "MLB18623867",
    "name": "Memória Kingston Fury Beast 16GB DDR4",
    "pictures": [{"url": "https://http2.mlstatic.com/catalogo.jpg"}],
    "buy_box_winner": {"item_id": "MLB1", "price": Decimal("929.99"), "available_quantity": 3},
    "attributes": [{"id": "GTIN", "value_name": "740617319880"}],
}


class FakeApi:
    """Stands in for the Mercado Livre API: answers what the test wants and records the calls."""

    def __init__(self, answers=None, token_answer=None):
        self.answers = answers or {}
        self.token_answer = token_answer or {
            "access_token": "TOKEN-NOVO", "refresh_token": "REFRESH-NOVO", "expires_in": 21600
        }
        self.calls = []
        self.token_calls = []

    def get_json(self, url, token):
        self.calls.append({"url": url, "token": token})
        if url not in self.answers:
            raise MercadoLivreError("Anúncio não encontrado na API (pode ter sido removido).")
        return self.answers[url]

    def post_form(self, url, data):
        self.token_calls.append(data)
        return self.token_answer


def connect(conn, api=None, expires_in=21600):
    """Connects with TOKEN-1; from then on the fake API answers renewals with TOKEN-NOVO."""
    api = api or FakeApi()
    api.token_answer = {"access_token": "TOKEN-1", "refresh_token": "REFRESH-1", "expires_in": expires_in}
    mercadolivre.connect(conn, CREDENTIALS, "CODE-123", post_form=api.post_form)
    api.token_answer = {"access_token": "TOKEN-NOVO", "refresh_token": "REFRESH-NOVO", "expires_in": 21600}
    return api


# ---------- Links ----------

@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (CATALOG_URL, ("products", "MLB18623867")),
        (CATALOG_URL + "?pdp_filters=item_id#reco", ("products", "MLB18623867")),
        (ITEM_URL, ("items", "MLB1234567890")),
        ("https://www.kabum.com.br/produto/172366", None),
        ("https://www.mercadolivre.com.br/ofertas", None),
    ],
)
def test_resource_from_url(url, expected):
    assert mercadolivre.resource_from_url(url) == expected


def test_handles_only_mercado_livre():
    assert mercadolivre.handles(ITEM_URL)
    assert not mercadolivre.handles("https://www.amazon.com.br/dp/B097K2MRS3")


def test_authorization_url():
    url = mercadolivre.authorization_url(CREDENTIALS, "estado-aleatorio")

    assert url.startswith("https://auth.mercadolivre.com.br/authorization?")
    assert "response_type=code" in url
    assert "client_id=123" in url
    assert "state=estado-aleatorio" in url


def test_pkce_pair():
    import base64
    import hashlib

    verifier, challenge = mercadolivre.make_pkce_pair()

    assert 43 <= len(verifier) <= 128  # length PKCE allows
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected  # the challenge is the SHA-256 of the verifier
    assert mercadolivre.make_pkce_pair()[0] != verifier  # random every time


def test_authorization_url_with_pkce():
    url = mercadolivre.authorization_url(CREDENTIALS, "estado", code_challenge="DESAFIO")
    assert "code_challenge=DESAFIO" in url
    assert "code_challenge_method=S256" in url


def test_connect_sends_the_pkce_verifier(conn):
    api = FakeApi(token_answer={"access_token": "T", "refresh_token": "R", "expires_in": 60})
    mercadolivre.connect(conn, CREDENTIALS, "CODE", post_form=api.post_form, code_verifier="VERIFICADOR")
    assert api.token_calls[0]["code_verifier"] == "VERIFICADOR"


@pytest.mark.parametrize(
    ("body", "expected_hint"),
    [
        ('{"error": "invalid_grant", "message": "Error validating grant"}', "expirou"),
        ('{"error": "invalid_client", "message": "invalid client_id"}', "App ID ou a Secret Key"),
        ('{"error": "invalid_request", "message": "redirect_uri mismatch"}', "URL de retorno"),
        ("<html>erro</html>", "Confira o App ID"),
    ],
)
def test_token_error_message_explains_what_to_do(body, expected_hint):
    message = mercadolivre.token_error_message(400, body)
    assert expected_hint in message
    assert message.startswith("O Mercado Livre recusou a autorização (")


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("TG-abc123", "TG-abc123"),
        ("  TG-abc123 ", "TG-abc123"),
        ("https://exemplo.com/callback?code=TG-abc123&state=xyz", "TG-abc123"),
    ],
)
def test_code_from_answer(answer, expected):
    assert mercadolivre.code_from_answer(answer) == expected


@pytest.mark.parametrize("answer", ["", "   ", "não é um código"])
def test_code_from_answer_rejects_nonsense(answer):
    with pytest.raises(MercadoLivreError, match="Cole o código"):
        mercadolivre.code_from_answer(answer)


# ---------- Tokens ----------

def test_connect_saves_both_tokens(conn):
    api = connect(conn)

    assert api.token_calls[0]["grant_type"] == "authorization_code"
    assert api.token_calls[0]["code"] == "CODE-123"
    token = db.get_oauth_token(conn, "mercadolivre")
    assert (token["access_token"], token["refresh_token"]) == ("TOKEN-1", "REFRESH-1")
    assert mercadolivre.is_connected(conn)


def test_valid_token_is_reused(conn):
    api = connect(conn)
    assert mercadolivre.access_token(conn, CREDENTIALS, api.post_form) == "TOKEN-1"
    assert len(api.token_calls) == 1  # no new call to the API


def test_token_about_to_expire_is_renewed(conn):
    api = connect(conn, expires_in=60)  # expires in one minute

    assert mercadolivre.access_token(conn, CREDENTIALS, api.post_form) == "TOKEN-NOVO"
    assert api.token_calls[-1]["grant_type"] == "refresh_token"
    assert api.token_calls[-1]["refresh_token"] == "REFRESH-1"
    # The refresh token is single use: the new one has to be saved.
    assert db.get_oauth_token(conn, "mercadolivre")["refresh_token"] == "REFRESH-NOVO"


def test_reading_without_connecting(conn):
    with pytest.raises(MercadoLivreError, match="Conecte a conta"):
        mercadolivre.access_token(conn, CREDENTIALS)


def test_disconnect(conn):
    connect(conn)
    mercadolivre.disconnect(conn)
    assert not mercadolivre.is_connected(conn)


def test_broken_token_answer_names_the_missing_field(conn):
    api = FakeApi(token_answer={"token_type": "Bearer", "user_id": 123})
    with pytest.raises(MercadoLivreError, match="faltou access_token, expires_in") as error:
        mercadolivre.connect(conn, CREDENTIALS, "CODE", post_form=api.post_form)
    assert "token_type" in str(error.value)  # tells which fields DID come (names only)
    assert not mercadolivre.is_connected(conn)


def test_connect_with_refresh_token_renews_itself(conn):
    api = FakeApi(token_answer={"access_token": "A", "refresh_token": "R", "expires_in": 21600})
    assert mercadolivre.connect(conn, CREDENTIALS, "CODE", post_form=api.post_form) is True


def test_connect_without_offline_access_still_works_for_6_hours(conn):
    """Without the offline_access permission Mercado Livre sends no refresh token."""
    api = FakeApi(token_answer={"access_token": "SO-6-HORAS", "token_type": "Bearer", "expires_in": 21600})

    assert mercadolivre.connect(conn, CREDENTIALS, "CODE", post_form=api.post_form) is False
    assert mercadolivre.is_connected(conn)
    assert mercadolivre.access_token(conn, CREDENTIALS, api.post_form) == "SO-6-HORAS"


def test_expired_access_without_refresh_token_asks_to_connect_again(conn):
    api = FakeApi(token_answer={"access_token": "VELHO", "expires_in": 60})  # expires in 1 minute
    mercadolivre.connect(conn, CREDENTIALS, "CODE", post_form=api.post_form)

    with pytest.raises(MercadoLivreError, match="expirou. Conecte de novo"):
        mercadolivre.access_token(conn, CREDENTIALS, api.post_form)
    assert len(api.token_calls) == 1  # did not try to renew with an empty refresh token


# ---------- Reading a product ----------

def test_read_listing(conn):
    api = connect(conn)
    api.answers = {"https://api.mercadolibre.com/items/MLB1234567890": ITEM_ANSWER}

    info = mercadolivre.read_product(conn, ITEM_URL, CREDENTIALS, api.get_json, api.post_form)

    assert info.name == "Memória Kingston Fury Beast 16GB"
    assert info.price == Decimal("899.90") and isinstance(info.price, Decimal)
    assert info.in_stock is True
    assert info.image_url == "https://http2.mlstatic.com/foto.jpg"
    assert (info.mpn, info.gtin) == ("KF432C16BB1/16", "740617319880")
    assert api.calls[0]["token"] == "TOKEN-1"  # sent in the Authorization header


def test_read_catalog_page(conn):
    api = connect(conn)
    api.answers = {"https://api.mercadolibre.com/products/MLB18623867": CATALOG_ANSWER}

    info = mercadolivre.read_product(conn, CATALOG_URL, CREDENTIALS, api.get_json, api.post_form)

    assert info.price == Decimal("929.99")
    assert info.name == "Memória Kingston Fury Beast 16GB DDR4"
    assert info.in_stock is True
    assert info.gtin == "740617319880"


@pytest.mark.parametrize(
    ("changes", "expected_stock"),
    [({"status": "paused"}, False), ({"available_quantity": 0}, False), ({}, True)],
)
def test_stock_comes_from_status_and_quantity(conn, changes, expected_stock):
    api = connect(conn)
    api.answers = {"https://api.mercadolibre.com/items/MLB1234567890": {**ITEM_ANSWER, **changes}}

    info = mercadolivre.read_product(conn, ITEM_URL, CREDENTIALS, api.get_json, api.post_form)
    assert info.in_stock is expected_stock


def test_catalog_without_a_winning_offer_uses_the_cheapest_new_seller(conn):
    """Real case (perfume, 2026-09-16): buy_box_winner was null but 30 sellers had prices."""
    api = connect(conn)
    api.answers = {
        "https://api.mercadolibre.com/products/MLB18623867": {**CATALOG_ANSWER, "buy_box_winner": None},
        "https://api.mercadolibre.com/products/MLB18623867/items": {
            "results": [
                {"item_id": "MLB1", "price": Decimal("51.90"), "condition": "new", "available_quantity": None},
                {"item_id": "MLB2", "price": Decimal("30.00"), "condition": "used"},  # used: ignored
                {"item_id": "MLB3", "price": Decimal("45.90"), "condition": "new", "available_quantity": None},
                {"item_id": "MLB4", "price": None},  # no price: ignored
            ]
        },
    }

    info = mercadolivre.read_product(conn, CATALOG_URL, CREDENTIALS, api.get_json, api.post_form)

    assert info.price == Decimal("45.90")  # cheapest NEW offer
    assert info.in_stock is None  # the API hid the quantity: unknown, not "out of stock"
    assert info.name == "Memória Kingston Fury Beast 16GB DDR4"


def test_catalog_with_no_offers_at_all(conn):
    api = connect(conn)
    api.answers = {
        "https://api.mercadolibre.com/products/MLB18623867": {**CATALOG_ANSWER, "buy_box_winner": None},
        "https://api.mercadolibre.com/products/MLB18623867/items": {"results": []},
    }
    with pytest.raises(MercadoLivreError, match="sem nenhuma oferta"):
        mercadolivre.read_product(conn, CATALOG_URL, CREDENTIALS, api.get_json, api.post_form)


def test_catalog_product_that_no_longer_exists(conn):
    """Real case (RAM, 2026-09-16): the catalog page MLB18623867 was removed."""
    api = connect(conn)  # no answers: the fake API says "não encontrado"
    with pytest.raises(MercadoLivreError, match="não existe mais no catálogo"):
        mercadolivre.read_product(conn, CATALOG_URL, CREDENTIALS, api.get_json, api.post_form)


def test_link_without_an_mlb_code(conn):
    connect(conn)
    with pytest.raises(MercadoLivreError, match="código do anúncio"):
        mercadolivre.read_product(conn, "https://www.mercadolivre.com.br/ofertas", CREDENTIALS)


def test_without_credentials_in_the_env(conn, monkeypatch):
    monkeypatch.delenv("MONITOR_ML_CLIENT_ID", raising=False)
    monkeypatch.delenv("MONITOR_ML_CLIENT_SECRET", raising=False)
    with pytest.raises(MercadoLivreError, match=".env"):
        mercadolivre.read_product(conn, ITEM_URL)


def test_credentials_from_env(monkeypatch):
    monkeypatch.setenv("MONITOR_ML_CLIENT_ID", "app-id")
    monkeypatch.setenv("MONITOR_ML_CLIENT_SECRET", "secret")
    monkeypatch.delenv("MONITOR_ML_REDIRECT_URI", raising=False)

    credentials = AppCredentials.from_env()
    assert credentials.client_id == "app-id"
    assert credentials.redirect_uri == "http://127.0.0.1:5000/mercadolivre/callback"


# ---------- The checker uses the API when connected ----------

def test_checker_uses_the_api_for_mercado_livre(conn):
    from monitor import checker
    from tests.helpers import ELECTRONICS_ID, KABUM_URL, fake_fetch

    product_id = db.create_product(
        conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL, ITEM_URL]
    )
    api = connect(conn)
    api.answers = {"https://api.mercadolibre.com/items/MLB1234567890": ITEM_ANSWER}

    def read_ml(connection, url):
        return mercadolivre.read_product(connection, url, CREDENTIALS, api.get_json, api.post_form)

    results = checker.check_product(conn, product_id, fetch=fake_fetch, read_ml=read_ml)

    assert [(r.store, r.ok, r.message) for r in results] == [
        ("KaBuM!", True, "R$ 929,99"),
        ("Mercado Livre", True, "R$ 899,90"),  # read through the API, not the blocked page
    ]


def test_checker_falls_back_to_the_page_when_not_connected(conn):
    from monitor import checker
    from tests.helpers import ELECTRONICS_ID, ML_URL, fake_fetch

    product_id = db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[ML_URL])
    [result] = checker.check_product(conn, product_id, fetch=fake_fetch)

    assert result.ok is False
    assert "anti-robô" in result.message  # the saved bot-check page


def test_api_error_does_not_stop_the_other_stores(conn):
    from monitor import checker
    from tests.helpers import ELECTRONICS_ID, KABUM_URL, fake_fetch

    product_id = db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL, ITEM_URL])
    api = connect(conn)  # no answers: the API "does not find" the listing

    def read_ml(connection, url):
        return mercadolivre.read_product(connection, url, CREDENTIALS, api.get_json, api.post_form)

    results = checker.check_product(conn, product_id, fetch=fake_fetch, read_ml=read_ml)
    assert [r.ok for r in results] == [True, False]
    assert "não encontrado" in results[1].message
