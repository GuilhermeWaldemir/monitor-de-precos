"""The CSRF protection: a POST only works when it carries this session's token."""

import pytest

from monitor import csrf
from tests.helpers import TEST_EMAIL, TEST_PASSWORD


# ---------- the rule by itself (no Flask) ----------


def test_the_token_is_created_once_and_kept():
    session = {}
    first = csrf.token_for(session)
    assert first == csrf.token_for(session)
    assert len(first) > 20  # long enough not to be guessed


def test_two_sessions_get_different_tokens():
    assert csrf.token_for({}) != csrf.token_for({})


@pytest.mark.parametrize("sent", ["outro-token", "", None])
def test_only_the_session_token_is_valid(sent):
    session = {}
    good = csrf.token_for(session)
    assert csrf.is_valid(session, good) is True
    assert csrf.is_valid(session, sent) is False


def test_a_session_without_a_token_refuses_everything():
    assert csrf.is_valid({}, "qualquer-coisa") is False


def test_the_hidden_field_carries_the_token():
    session = {}
    field = str(csrf.hidden_field(session))
    assert 'name="csrf_token"' in field
    assert session["csrf_token"] in field


# ---------- the site ----------


def sign_up_without_help(plain_client, email):
    """Creates an account with a client that does not add the token by itself.

    Even signing up needs the token, so the test writes it once, by hand, the way the
    page would. Logging in matters here because the login check runs before this one.
    """
    with plain_client.session_transaction() as session:
        token = csrf.token_for(session)
    plain_client.post("/signup", data={
        "email": email, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD,
        csrf.FIELD_NAME: token,
    })


def test_forms_carry_the_hidden_field(client):
    page = client.get("/products/new").get_data(as_text=True)
    assert 'name="csrf_token"' in page


def test_a_post_without_the_token_is_refused(client_without_token):
    sign_up_without_help(client_without_token, TEST_EMAIL)
    answer = client_without_token.post("/categories", data={"name": "Jardinagem"})
    assert answer.status_code == 400


def test_a_post_with_the_wrong_token_is_refused(client):
    answer = client.post("/categories", data={"name": "Livros", "csrf_token": "token-falso"})
    assert answer.status_code == 400


def test_the_same_post_works_with_the_token(client):
    answer = client.post("/categories", data={"name": "Livros"}, follow_redirects=True)
    assert answer.status_code == 200
    assert "Livros" in answer.get_data(as_text=True)


def test_nothing_changed_when_the_token_is_missing(client_without_token, client):
    """The refused POST must not have created the category."""
    sign_up_without_help(client_without_token, "outro@exemplo.com")
    client_without_token.post("/categories", data={"name": "Jardinagem"})
    page = client.get("/").get_data(as_text=True)
    assert "Jardinagem" not in page


def test_reading_pages_needs_no_token(client_without_token):
    assert client_without_token.get("/").status_code == 200
