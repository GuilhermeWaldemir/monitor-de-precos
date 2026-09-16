import pytest

from monitor import auth, db
from tests.helpers import ELECTRONICS_ID, KABUM_URL
from tests.test_app import TEST_EMAIL, TEST_PASSWORD, anonymous_client, client, db_path  # noqa: F401

PASSWORD = "senha-secreta"


# ---------- Rules (no web) ----------

@pytest.mark.parametrize(
    ("typed", "expected"),
    [("  Ana@Exemplo.COM ", "ana@exemplo.com"), ("a@b.co", "a@b.co")],
)
def test_clean_email(typed, expected):
    assert auth.clean_email(typed) == expected


@pytest.mark.parametrize("typed", ["", "   ", "sem-arroba", "a@b", "a b@c.com", None, "x" * 200 + "@b.com"])
def test_invalid_email(typed):
    with pytest.raises(ValueError, match="e-mail válido"):
        auth.clean_email(typed)


def test_password_too_short():
    with pytest.raises(ValueError, match="8 caracteres"):
        auth.check_password_rules("1234567")


def test_passwords_must_match():
    with pytest.raises(ValueError, match="não são iguais"):
        auth.check_password_rules(PASSWORD, "outra-senha")


def test_register_stores_only_the_hash(conn):
    user_id = auth.register(conn, "Ana@Exemplo.com", PASSWORD, PASSWORD)
    user = db.get_user(conn, user_id)

    assert user["email"] == "ana@exemplo.com"
    assert PASSWORD not in user["password_hash"]  # the password itself is never saved
    assert len(user["password_hash"]) > 40


def test_email_is_unique_ignoring_case(conn):
    auth.register(conn, "ana@exemplo.com", PASSWORD)
    with pytest.raises(ValueError, match="Já existe uma conta"):
        auth.register(conn, "ANA@exemplo.com", PASSWORD)


def test_authenticate(conn):
    auth.register(conn, "ana@exemplo.com", PASSWORD)

    assert auth.authenticate(conn, "ANA@exemplo.com", PASSWORD)["email"] == "ana@exemplo.com"
    assert auth.authenticate(conn, "ana@exemplo.com", "senha-errada") is None
    assert auth.authenticate(conn, "outra@exemplo.com", PASSWORD) is None  # no such account
    assert auth.authenticate(conn, "nem-e-mail", PASSWORD) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/products/1", "/products/1"),
        ("https://site-falso.com", None),  # open redirect
        ("//site-falso.com", None),
        ("", None),
        (None, None),
    ],
)
def test_safe_next_path(value, expected):
    assert auth.safe_next_path(value) == expected


# ---------- Sign up, log in, log out on the site ----------

def signup(client, **changes):
    data = {"email": TEST_EMAIL, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD}
    data.update(changes)
    return client.post("/signup", data=data, follow_redirects=True)


def test_signup_logs_in_right_away(anonymous_client):
    response = signup(anonymous_client)

    assert "Conta criada." in response.text
    assert TEST_EMAIL in response.text  # shown in the top bar
    assert "Adicionar produto" in response.text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"email": "sem-arroba"}, "e-mail válido"),
        ({"password": "curta", "password_confirm": "curta"}, "8 caracteres"),
        ({"password_confirm": "outra-senha-diferente"}, "não são iguais"),
    ],
)
def test_signup_errors_keep_the_form(anonymous_client, changes, message):
    response = signup(anonymous_client, **changes)
    assert response.status_code == 400
    assert message in response.text


def test_signup_with_an_email_already_used(anonymous_client):
    signup(anonymous_client)
    anonymous_client.post("/logout")
    response = signup(anonymous_client)
    assert response.status_code == 400
    assert "Já existe uma conta" in response.text


def test_login_and_logout(anonymous_client):
    signup(anonymous_client)
    anonymous_client.post("/logout", follow_redirects=True)

    wrong = anonymous_client.post("/login", data={"email": TEST_EMAIL, "password": "errada"})
    assert wrong.status_code == 400
    assert "E-mail ou senha incorretos." in wrong.text

    response = anonymous_client.post(
        "/login", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}, follow_redirects=True
    )
    assert "Bem-vindo de volta" in response.text


def test_logout_hides_the_account_menu(client):
    response = client.post("/logout", follow_redirects=True)
    assert "Você saiu da sua conta." in response.text
    assert "Criar conta" in response.text
    assert "Sair" not in response.text


def test_login_goes_back_to_the_page_the_visitor_wanted(anonymous_client):
    blocked = anonymous_client.get("/products/new", follow_redirects=True)
    assert "Entre na sua conta para fazer isso." in blocked.text
    assert 'action="/login?next=/products/new"' in blocked.text  # the form remembers where to go back

    signup(anonymous_client)  # signing up from that form keeps the same flow
    response = anonymous_client.post(
        "/login?next=/products/new", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.headers["Location"] == "/products/new"


def test_login_ignores_a_link_to_another_site(anonymous_client):
    signup(anonymous_client)
    anonymous_client.post("/logout")
    response = anonymous_client.post(
        "/login?next=https://site-falso.com", data={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.headers["Location"] == "/"


# ---------- What a visitor can and cannot do ----------

def test_visitor_can_browse(anonymous_client, db_path):
    from contextlib import closing

    with closing(db.connect(db_path)) as conn:
        product_id = db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL])

    for path in ["/", f"/categories/{ELECTRONICS_ID}", f"/products/{product_id}", "/search?q=ram", "/settings"]:
        assert anonymous_client.get(path).status_code == 200

    page = anonymous_client.get(f"/products/{product_id}").text
    assert "Entrar para verificar preços" in page
    assert "Adicionar fonte" not in page  # nothing that changes data


@pytest.mark.parametrize(
    "path",
    ["/products/new", "/products/1/edit", "/capture?url=https://www.kabum.com.br/produto/1"],
)
def test_visitor_cannot_open_pages_that_change_data(anonymous_client, path):
    response = anonymous_client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")


@pytest.mark.parametrize(
    "path",
    ["/products", "/categories", "/products/1/check", "/products/1/delete", "/links/1/delete", "/settings"],
)
def test_visitor_cannot_post(anonymous_client, path):
    response = anonymous_client.post(path, data={})
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login")
