"""User accounts: the rules for e-mail and password, sign up and log in.

The password is never stored. `generate_password_hash` (Werkzeug, which comes with Flask)
turns it into a long code that cannot be turned back into the password; logging in hashes
what was typed and compares the two codes. So even someone reading the database file
cannot learn the passwords.
"""

import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from monitor import db

# Not a full e-mail validator (those are huge): "something@something.something", no spaces.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LENGTH = 200
MIN_PASSWORD_LENGTH = 8


def clean_email(email: str | None) -> str:
    """Trim and lowercase the e-mail. Raises ValueError when it doesn't look like one."""
    email = (email or "").strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        raise ValueError("Informe um e-mail válido, como voce@exemplo.com.")
    return email


def check_password_rules(password: str | None, confirmation: str | None = None) -> str:
    """Raises ValueError when the password is too short or the confirmation doesn't match."""
    password = password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha precisa de pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if confirmation is not None and password != confirmation:
        raise ValueError("As duas senhas não são iguais.")
    return password


def register(conn: sqlite3.Connection, email: str, password: str, confirmation: str | None = None) -> int:
    """Create an account and return its id. Raises ValueError with a message for the user."""
    email = clean_email(email)
    password = check_password_rules(password, confirmation)
    return db.create_user(conn, email, generate_password_hash(password))


def authenticate(conn: sqlite3.Connection, email: str, password: str | None) -> sqlite3.Row | None:
    """The user when the e-mail and password match, None otherwise.

    The same None for "no such e-mail" and "wrong password": telling them apart would
    let someone discover which e-mails have an account here.
    """
    try:
        email = clean_email(email)
    except ValueError:
        return None
    user = db.get_user_by_email(conn, email)
    if user is None or not check_password_hash(user["password_hash"], password or ""):
        return None
    return user


def safe_next_path(value: str | None) -> str | None:
    """The page to open after logging in, only if it is a path inside this site.

    Blocks "open redirect": a link like /login?next=https://site-falso.com would otherwise
    send the user somewhere else right after they typed their password.
    """
    value = (value or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    return None
