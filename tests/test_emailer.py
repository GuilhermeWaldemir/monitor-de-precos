from decimal import Decimal

import pytest

from monitor import alerts, emailer
from monitor.config import load_env_file

SMTP_VARS = ["MONITOR_SMTP_USER", "MONITOR_SMTP_PASSWORD", "MONITOR_SMTP_HOST", "MONITOR_SMTP_PORT", "MONITOR_EMAIL_FROM"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Each test starts without SMTP settings, whatever the machine has in its .env."""
    for name in SMTP_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------- Reading the settings ----------

def test_no_settings_means_not_configured():
    assert emailer.SmtpConfig.from_env() is None


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("MONITOR_SMTP_USER", "eu@gmail.com")
    monkeypatch.setenv("MONITOR_SMTP_PASSWORD", "senha-de-app")

    config = emailer.SmtpConfig.from_env()
    assert (config.host, config.port) == ("smtp.gmail.com", 587)  # defaults
    assert config.sender == "eu@gmail.com"  # the sender defaults to the account


def test_settings_can_be_changed(monkeypatch):
    monkeypatch.setenv("MONITOR_SMTP_USER", "eu@exemplo.com")
    monkeypatch.setenv("MONITOR_SMTP_PASSWORD", "x")
    monkeypatch.setenv("MONITOR_SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.setenv("MONITOR_SMTP_PORT", "465")
    monkeypatch.setenv("MONITOR_EMAIL_FROM", "avisos@exemplo.com")

    config = emailer.SmtpConfig.from_env()
    assert (config.host, config.port, config.sender) == ("smtp.exemplo.com", 465, "avisos@exemplo.com")


def test_spaces_in_the_app_password_are_ignored(monkeypatch):
    """Google shows the app password in groups of four; the spaces are not part of it."""
    monkeypatch.setenv("MONITOR_SMTP_USER", "eu@gmail.com")
    monkeypatch.setenv("MONITOR_SMTP_PASSWORD", "abcd efgh ijkl mnop")

    assert emailer.SmtpConfig.from_env().password == "abcdefghijklmnop"


def test_sending_without_settings_explains_what_is_missing():
    with pytest.raises(emailer.EmailError, match="não configurado"):
        emailer.send_email("ana@exemplo.com", "Oi", "Corpo")


# ---------- The .env file ----------

def test_load_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        '# comentário\n\nMONITOR_SMTP_USER="eu@gmail.com"\nMONITOR_SMTP_PASSWORD = senha de app \nlinha-sem-igual\n',
        encoding="utf-8",
    )
    load_env_file(env)

    assert emailer.SmtpConfig.from_env().user == "eu@gmail.com"
    assert emailer.SmtpConfig.from_env().password == "senhadeapp"  # spaces removed on purpose


def test_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITOR_SMTP_USER", "do-ambiente@gmail.com")
    monkeypatch.setenv("MONITOR_SMTP_PASSWORD", "x")
    env = tmp_path / ".env"
    env.write_text("MONITOR_SMTP_USER=do-arquivo@gmail.com\n", encoding="utf-8")

    load_env_file(env)
    assert emailer.SmtpConfig.from_env().user == "do-ambiente@gmail.com"


def test_missing_env_file_is_fine(tmp_path):
    load_env_file(tmp_path / "nao-existe.env")  # must not raise


# ---------- The message itself ----------

def test_build_message():
    message = emailer.build_message("de@x.com", "para@y.com", "Assunto", "Corpo do e-mail")

    assert message["From"] == "de@x.com"
    assert message["To"] == "para@y.com"
    assert message["Subject"] == "Assunto"
    assert message.get_content().strip() == "Corpo do e-mail"


def test_price_drop_email_text():
    drop = alerts.PriceDrop(
        product_id=1, product_name="Memória Kingston", old_price=Decimal("1000.00"),
        new_price=Decimal("900.00"), store="KaBuM!",
    )
    subject, body = alerts.drop_email(drop, "http://127.0.0.1:5000/products/1")

    assert subject == "Caiu 10,0%: Memória Kingston"
    assert "De:    R$ 1.000,00" in body
    assert "Por:   R$ 900,00  (na KaBuM!)" in body
    assert "Economia: R$ 100,00" in body
    assert "http://127.0.0.1:5000/products/1" in body


def test_price_drop_email_without_link():
    drop = alerts.PriceDrop(
        product_id=1, product_name="X", old_price=Decimal("100.00"),
        new_price=Decimal("90.00"), store="KaBuM!",
    )
    _, body = alerts.drop_email(drop)
    assert "http" not in body
