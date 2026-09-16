"""Sends e-mail through SMTP.

SMTP is the protocol e-mail servers speak, and `smtplib` comes with Python, so there is
no new dependency. The account and password come from environment variables (.env), never
from the code: a password inside the repository would be public on GitHub.

With Gmail, the password here is an **app password** (myaccount.google.com → Segurança →
Senhas de app), not the account's real password: it only sends e-mail and can be revoked.
"""

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20


class EmailError(Exception):
    """The e-mail could not be sent. The message is shown to the user."""


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str  # the "From" address

    @classmethod
    def from_env(cls) -> "SmtpConfig | None":
        """The configuration, or None when the .env does not have the account yet."""
        user = os.environ.get("MONITOR_SMTP_USER", "").strip()
        # Google shows the app password in groups of four ("abcd efgh ijkl mnop"), but the
        # spaces are only to make it readable: the password itself has none.
        password = os.environ.get("MONITOR_SMTP_PASSWORD", "").replace(" ", "").strip()
        if not user or not password:
            return None
        return cls(
            host=os.environ.get("MONITOR_SMTP_HOST", "smtp.gmail.com").strip(),
            port=int(os.environ.get("MONITOR_SMTP_PORT", "587")),
            user=user,
            password=password,
            sender=os.environ.get("MONITOR_EMAIL_FROM", user).strip(),
        )


def build_message(sender: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def send_email(to: str, subject: str, body: str, config: SmtpConfig | None = None) -> None:
    """Send one e-mail. Raises EmailError with a message in Portuguese when it fails."""
    config = config or SmtpConfig.from_env()
    if config is None:
        raise EmailError(
            "Envio de e-mail não configurado: falta MONITOR_SMTP_USER e MONITOR_SMTP_PASSWORD no .env."
        )

    message = build_message(config.sender, to, subject, body)
    try:
        if config.port == 465:  # port 465 is encrypted from the first byte
            with smtplib.SMTP_SSL(config.host, config.port, timeout=TIMEOUT_SECONDS,
                                  context=ssl.create_default_context()) as server:
                server.login(config.user, config.password)
                server.send_message(message)
        else:  # 587: starts as plain text and upgrades to encrypted with STARTTLS
            with smtplib.SMTP(config.host, config.port, timeout=TIMEOUT_SECONDS) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(config.user, config.password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise EmailError("O servidor recusou o login. Confira o usuário e a senha de app no .env.") from None
    except (smtplib.SMTPException, OSError) as error:
        logger.exception("Could not send e-mail to %s", to)
        raise EmailError(f"Não foi possível enviar o e-mail: {error.__class__.__name__}.") from None
