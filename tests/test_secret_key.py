"""The key that signs the session cookie: it comes from .env, or from the database."""

from monitor import db
from monitor.app import create_app
from tests.helpers import fake_fetch


def build(db_path, mailbox):
    return create_app(db_path=db_path, fetch=fake_fetch, send_email=mailbox)


def test_the_key_from_the_env_wins(db_path, mailbox, monkeypatch):
    monkeypatch.setenv("MONITOR_SECRET_KEY", "chave-de-producao")
    assert build(db_path, mailbox).config["SECRET_KEY"] == "chave-de-producao"


def test_spaces_around_the_key_are_ignored(db_path, mailbox, monkeypatch):
    monkeypatch.setenv("MONITOR_SECRET_KEY", "  chave-de-producao  ")
    assert build(db_path, mailbox).config["SECRET_KEY"] == "chave-de-producao"


def test_an_empty_variable_falls_back_to_the_database(db_path, mailbox, monkeypatch):
    monkeypatch.setenv("MONITOR_SECRET_KEY", "   ")
    key = build(db_path, mailbox).config["SECRET_KEY"]
    assert key.strip() != ""
    with db.connect(db_path) as conn:
        assert db.get_or_create_secret_key(conn) == key


def test_without_the_variable_a_random_key_is_created_and_kept(db_path, mailbox):
    """Restarting the server must not log everybody out."""
    first = build(db_path, mailbox).config["SECRET_KEY"]
    second = build(db_path, mailbox).config["SECRET_KEY"]
    assert first == second
    assert len(first) > 20


def test_each_database_gets_its_own_key(tmp_path, mailbox):
    one = build(tmp_path / "one.db", mailbox).config["SECRET_KEY"]
    other = build(tmp_path / "other.db", mailbox).config["SECRET_KEY"]
    assert one != other


def test_the_key_never_reaches_the_settings_page(client):
    """It shares the settings table, so make sure it is not shown or editable there."""
    page = client.get("/settings").get_data(as_text=True)
    with db.connect(client.application.config["DB_PATH"]) as conn:
        key = db.get_or_create_secret_key(conn)
    assert key not in page


def test_the_login_still_works_with_the_generated_key(client):
    """A round trip: the cookie is signed with the key that came from the database."""
    page = client.get("/").get_data(as_text=True)
    assert "Sair" in page  # the `client` fixture is logged in


def test_the_database_path_can_come_from_the_environment(tmp_path, mailbox, monkeypatch):
    """On a server the database is not in ./data (see MONITOR_DB_PATH in .env.example)."""
    wanted = tmp_path / "outro-lugar" / "monitor.db"
    wanted.parent.mkdir()
    monkeypatch.setenv("MONITOR_DB_PATH", str(wanted))
    app = create_app(fetch=fake_fetch, send_email=mailbox)
    assert str(app.config["DB_PATH"]) == str(wanted)
    assert wanted.exists()
