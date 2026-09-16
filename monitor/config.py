"""Reads the .env file (passwords and other settings that must stay out of Git).

A .env file has one "NAME=value" per line. There is a library for this (python-dotenv),
but reading it is ten lines, so the project keeps one less dependency — and it is easier
to explain what happens.
"""

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path(".env")


def load_env_file(path: Path | str = DEFAULT_ENV_PATH) -> None:
    """Copy the values of the file into the environment variables.

    A variable that already exists in the environment wins, so running
    `MONITOR_SMTP_USER=... flask run` still overrides the file.
    """
    path = Path(path)
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
