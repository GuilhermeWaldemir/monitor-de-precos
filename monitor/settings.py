"""Rules for the app's settings: which options exist, their defaults, and validation.

No SQL here — monitor/db.py owns the "settings" table and how rows are read/written.
This module only knows the *meaning* of each setting: which values are allowed, what
the default is, and the labels shown in the template. Keeping the rules separate from
the SQL makes it easy to add a new setting (e.g. font) without touching the database code.
"""

from collections.abc import Mapping
from sqlite3 import Connection

from monitor.db import get_settings_rows, save_settings_rows

# Every setting the app understands, and the values each one accepts.
# New settings (accent color, animations...) get one more entry here.
CHOICES: dict[str, tuple[str, ...]] = {
    "theme": ("auto", "light", "dark"),
    "font": ("default", "nunito-bowlby", "oswald-indie"),
    "card_glow": ("on", "off"),  # soft light following the mouse over product cards
    "category_animation": ("on", "off"),  # dots forming the category icon on category pages
}

# Used when nothing is saved yet, and when a saved value is no longer valid.
DEFAULTS: dict[str, str] = {
    "theme": "auto",
    "font": "default",
    "card_glow": "on",
    "category_animation": "on",
}

# Portuguese name of each setting, used in error messages ("Opção inválida para tema.").
_FIELD_NAMES: dict[str, str] = {
    "theme": "tema",
    "font": "fonte",
    "card_glow": "brilho nos cards",
    "category_animation": "animação das categorias",
}

THEME_LABELS = {
    "auto": "Automático",
    "light": "Claro",
    "dark": "Escuro",
}

THEME_DESCRIPTIONS = {
    "auto": "Segue o tema do sistema",
    "light": "Sempre com fundo claro",
    "dark": "Sempre com fundo escuro",
}

FONT_LABELS = {
    "default": "Padrão",
    "nunito-bowlby": "Nunito Sans + Bowlby One",
    "oswald-indie": "Oswald + Indie Flower",
}

FONT_DESCRIPTIONS = {
    "default": "Fonte do sistema, a mais legível",
    "nunito-bowlby": "Títulos marcantes, texto arredondado",
    "oswald-indie": "Títulos condensados, texto manuscrito (pode cansar em textos longos)",
}


def load_settings(conn: Connection) -> dict[str, str]:
    """Every setting, defaults merged with what's saved.

    Unknown keys (e.g. from an older version of the app) and saved values that are no
    longer one of CHOICES fall back to the default instead of breaking the page.
    """
    saved = get_settings_rows(conn)
    settings = dict(DEFAULTS)
    for key, choices in CHOICES.items():
        if key in saved and saved[key] in choices:
            settings[key] = saved[key]
    return settings


def save_settings(conn: Connection, values: Mapping[str, str]) -> None:
    """Save every known key in `values`.

    Validates all of them first: if any value is invalid, nothing is saved and a
    ValueError with a Portuguese message is raised. All the keys are written in a
    single transaction (see monitor/db.py), so saving theme and font together never
    leaves the database with only one of them changed.
    """
    to_save = {key: value for key, value in values.items() if key in CHOICES}
    for key, value in to_save.items():
        if value not in CHOICES[key]:
            raise ValueError(f"Opção inválida para {_FIELD_NAMES[key]}.")

    save_settings_rows(conn, to_save)
