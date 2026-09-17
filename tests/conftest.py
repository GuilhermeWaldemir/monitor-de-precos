"""Shared pytest fixtures (pytest loads this file automatically)."""

import pytest
from flask.testing import FlaskClient

from monitor import csrf, db
from monitor.app import create_app
from tests.helpers import TEST_EMAIL, TEST_PASSWORD, fake_fetch


# Real credentials (Mercado Livre, Gmail) live in the developer's .env. If they leaked into
# the tests, a test could call the real API by accident — tests must never touch the internet.
SECRET_VARIABLES = (
    "MONITOR_ML_CLIENT_ID", "MONITOR_ML_CLIENT_SECRET", "MONITOR_ML_REDIRECT_URI",
    "MONITOR_SMTP_USER", "MONITOR_SMTP_PASSWORD",
)


@pytest.fixture(autouse=True)
def isolate_from_the_real_env(monkeypatch):
    """Every test runs as if the machine had no .env."""
    monkeypatch.setattr("monitor.app.load_env_file", lambda *args, **kwargs: None)
    for name in SECRET_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def conn(tmp_path):
    """A fresh database in a temporary folder for each test."""
    connection = db.connect(tmp_path / "test.db")
    db.init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "app.db"


class FakeMailbox:
    """Stands in for sending e-mail: keeps the messages instead of sending them."""

    def __init__(self):
        self.sent = []
        self.error = None  # set to an EmailError to simulate a server that refuses

    def __call__(self, to, subject, body):
        if self.error is not None:
            raise self.error
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture
def mailbox():
    return FakeMailbox()


class BrowserClient(FlaskClient):
    """Posts like a real browser: carries the CSRF token that the forms would carry.

    Without this, every POST in the tests would be refused. Turning the protection off
    during the tests would be worse: they would stop testing the real site.
    """

    def post(self, *args, **kwargs):
        data = kwargs.get("data")
        if data is None or (isinstance(data, dict) and csrf.FIELD_NAME not in data):
            with self.session_transaction() as session:
                token = csrf.token_for(session)
            kwargs["data"] = {**(data or {}), csrf.FIELD_NAME: token}
        return super().post(*args, **kwargs)


@pytest.fixture
def app(db_path, mailbox):
    application = create_app(db_path=db_path, fetch=fake_fetch, send_email=mailbox)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def anonymous_client(app):
    """A visitor: can look around, but cannot change anything."""
    app.test_client_class = BrowserClient
    return app.test_client()


@pytest.fixture
def client(anonymous_client):
    """Logged in, because almost every test changes something."""
    anonymous_client.post(
        "/signup",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD},
    )
    return anonymous_client


@pytest.fixture
def client_without_token(app):
    """A plain client that sends no CSRF token: used to test the protection itself."""
    app.test_client_class = FlaskClient
    return app.test_client()
