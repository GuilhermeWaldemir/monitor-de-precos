import pytest

from monitor import settings


def defaults_with(**changes):
    """All the defaults plus the given changes. Comparing against this (instead of
    writing every key) keeps these tests valid when a new setting is added."""
    return {**settings.DEFAULTS, **changes}


def test_defaults_when_nothing_saved(conn):
    assert settings.load_settings(conn) == {
        "theme": "auto", "font": "default", "card_glow": "on", "category_animation": "on",
    }


def test_category_animation_can_be_turned_off(conn):
    settings.save_settings(conn, {"category_animation": "off"})
    assert settings.load_settings(conn) == defaults_with(category_animation="off")


def test_save_and_load(conn):
    settings.save_settings(conn, {"theme": "dark"})
    assert settings.load_settings(conn) == defaults_with(theme="dark")


def test_saving_again_overwrites(conn):
    settings.save_settings(conn, {"theme": "dark"})
    settings.save_settings(conn, {"theme": "light"})
    assert settings.load_settings(conn) == defaults_with(theme="light")


def test_invalid_value_raises_and_saves_nothing(conn):
    with pytest.raises(ValueError, match="Opção inválida para tema"):
        settings.save_settings(conn, {"theme": "purple"})
    assert settings.load_settings(conn) == defaults_with()


def test_stale_invalid_value_in_db_falls_back_to_default(conn):
    # Simulates an old/edited row that no longer matches CHOICES.
    from monitor.db import save_settings_rows

    save_settings_rows(conn, {"theme": "purple"})
    assert settings.load_settings(conn) == defaults_with()


def test_unknown_keys_are_ignored(conn):
    # "accent_color" doesn't exist yet (a future setting); CHOICES doesn't know it.
    from monitor.db import save_settings_rows

    save_settings_rows(conn, {"accent_color": "purple"})
    assert settings.load_settings(conn) == defaults_with()

    settings.save_settings(conn, {"accent_color": "purple", "theme": "dark"})
    assert settings.load_settings(conn) == defaults_with(theme="dark")


# ---------- Font ----------

def test_font_default_when_nothing_saved(conn):
    assert settings.load_settings(conn)["font"] == "default"


def test_save_font(conn):
    settings.save_settings(conn, {"font": "nunito-bowlby"})
    assert settings.load_settings(conn) == defaults_with(font="nunito-bowlby")


def test_invalid_font_raises_and_saves_nothing(conn):
    with pytest.raises(ValueError, match="Opção inválida para fonte"):
        settings.save_settings(conn, {"font": "comic-sans"})
    assert settings.load_settings(conn) == defaults_with()


# ---------- Card glow ----------

def test_card_glow_is_on_by_default_and_can_be_turned_off(conn):
    assert settings.load_settings(conn)["card_glow"] == "on"
    settings.save_settings(conn, {"card_glow": "off"})
    assert settings.load_settings(conn) == defaults_with(card_glow="off")


def test_invalid_card_glow_raises_and_saves_nothing(conn):
    with pytest.raises(ValueError, match="brilho nos cards"):
        settings.save_settings(conn, {"theme": "dark", "card_glow": "maybe"})
    assert settings.load_settings(conn) == defaults_with()


# ---------- Saving several settings together (single transaction) ----------

def test_saving_theme_and_font_together(conn):
    settings.save_settings(conn, {"theme": "dark", "font": "oswald-indie"})
    assert settings.load_settings(conn) == defaults_with(theme="dark", font="oswald-indie")


def test_one_invalid_value_saves_neither(conn):
    with pytest.raises(ValueError):
        settings.save_settings(conn, {"theme": "dark", "font": "comic-sans"})
    # All-or-nothing: the valid "theme" was not saved either.
    assert settings.load_settings(conn) == defaults_with()


def test_keys_missing_from_values_keep_their_saved_value(conn):
    settings.save_settings(conn, {"theme": "dark", "font": "nunito-bowlby"})
    settings.save_settings(conn, {"theme": "light"})  # font not mentioned this time
    assert settings.load_settings(conn) == defaults_with(theme="light", font="nunito-bowlby")
