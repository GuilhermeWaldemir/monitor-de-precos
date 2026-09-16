from decimal import Decimal

import pytest

from monitor import auth, daily_check, db
from monitor.emailer import EmailError
from tests.conftest import FakeMailbox
from tests.helpers import ELECTRONICS_ID, KABUM_URL, ML_URL, TEST_EMAIL, fake_fetch


@pytest.fixture
def product_id(conn):
    """One product with a store that works (KaBuM!) and one that is blocked (Mercado Livre)."""
    auth.register(conn, TEST_EMAIL, "senha-de-teste")
    return db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL, ML_URL])


def run(conn, mailbox=None):
    """Runs the daily check without touching the internet and without pauses."""
    return daily_check.run(conn, fetch=fake_fetch, send_email=mailbox or FakeMailbox(), pause=0)


def test_checks_every_product_and_counts_what_happened(conn, product_id):
    summary = run(conn)

    assert summary == {"products": 1, "prices": 1, "failures": 1, "drops": 0, "emails": 0}
    # The KaBuM! price is in the history and became the alert reference.
    assert db.get_alert_reference(conn, product_id) == Decimal("929.99")


def test_price_drop_is_emailed(conn, product_id):
    run(conn)  # first run: reference is R$ 929,99

    link = db.list_links(conn, product_id)[1]  # Mercado Livre, by hand
    db.add_price_check(conn, link["id"], source="manual", price=Decimal("800.00"))

    mailbox = FakeMailbox()
    summary = daily_check.run(conn, fetch=fake_fetch, send_email=mailbox, pause=0, site_url="http://meusite")

    assert summary["drops"] == 1 and summary["emails"] == 1
    [message] = mailbox.sent
    assert message["to"] == TEST_EMAIL
    assert message["subject"].startswith("Caiu 14,0%")
    assert f"http://meusite/products/{product_id}" in message["body"]
    assert db.list_price_alerts(conn, product_id)[0]["emailed_at"] is not None


def test_email_failure_keeps_the_alert_for_later(conn, product_id):
    run(conn)
    link = db.list_links(conn, product_id)[1]
    db.add_price_check(conn, link["id"], source="manual", price=Decimal("800.00"))

    mailbox = FakeMailbox()
    mailbox.error = EmailError("O servidor recusou o login.")
    summary = daily_check.run(conn, fetch=fake_fetch, send_email=mailbox, pause=0)

    assert summary["drops"] == 1 and summary["emails"] == 0
    assert db.list_price_alerts(conn, product_id)[0]["emailed_at"] is None  # can be retried


def test_without_accounts_nothing_is_emailed(conn):
    # No account was registered in this test, so there is nobody to warn.
    product_id = db.create_product(conn, name="RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL, ML_URL])
    run(conn)
    # The cheaper price goes on the blocked store, so the next run does not overwrite it.
    db.add_price_check(conn, db.list_links(conn, product_id)[1]["id"], source="manual", price=Decimal("100.00"))

    mailbox = FakeMailbox()
    summary = daily_check.run(conn, fetch=fake_fetch, send_email=mailbox, pause=0)
    assert summary["drops"] == 1 and summary["emails"] == 0
    assert mailbox.sent == []


def test_one_broken_product_does_not_stop_the_others(conn, product_id, monkeypatch):
    other_id = db.create_product(conn, name="Outra RAM", category_id=ELECTRONICS_ID, urls=[KABUM_URL])

    original = daily_check.checker.check_product

    def explode_on_the_first(connection, pid, **kwargs):
        if pid == other_id:  # newest product is checked first
            raise RuntimeError("bug")
        return original(connection, pid, **kwargs)

    monkeypatch.setattr(daily_check.checker, "check_product", explode_on_the_first)
    summary = run(conn)

    assert summary["products"] == 2
    assert summary["prices"] == 1  # the working product was still checked
    assert db.get_alert_reference(conn, product_id) == Decimal("929.99")


def test_nothing_to_do_with_no_products(conn):
    assert run(conn) == {"products": 0, "prices": 0, "failures": 0, "drops": 0, "emails": 0}
