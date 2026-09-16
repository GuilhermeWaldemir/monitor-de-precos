"""Shared pytest fixtures (pytest loads this file automatically)."""

import pytest

from monitor import db
from monitor.app import create_app
from tests.helpers import TEST_EMAIL, TEST_PASSWORD, fake_fetch


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


@pytest.fixture
def anonymous_client(db_path, mailbox):
    """A visitor: can look around, but cannot change anything."""
    app = create_app(db_path=db_path, fetch=fake_fetch, send_email=mailbox)
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def client(anonymous_client):
    """Logged in, because almost every test changes something."""
    anonymous_client.post(
        "/signup",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "password_confirm": TEST_PASSWORD},
    )
    return anonymous_client
