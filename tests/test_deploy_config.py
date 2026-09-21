"""A receita do deploy (render.yaml) é lida por um teste, e não só por um humano distraído.

O erro que este arquivo existe para impedir é o pior possível: publicar o site sem o modo
demonstração, ou com um segredo escrito dentro do repositório.
"""

from pathlib import Path

import pytest

RECIPE = Path(__file__).resolve().parent.parent / "render.yaml"


@pytest.fixture
def recipe() -> str:
    return RECIPE.read_text(encoding="utf-8")


def test_the_recipe_exists():
    assert RECIPE.exists()


def test_the_published_site_runs_in_demo_mode(recipe):
    assert "MONITOR_DEMO" in recipe
    assert 'value: "1"' in recipe


def test_it_starts_with_a_production_server(recipe):
    assert "gunicorn" in recipe
    assert "monitor.app:create_app()" in recipe


def test_the_secret_key_is_generated_by_the_server(recipe):
    """generateValue: o Render sorteia a chave; ela nunca aparece no Git."""
    assert "MONITOR_SECRET_KEY" in recipe
    assert "generateValue: true" in recipe


def test_gunicorn_is_installed_on_the_server():
    requirements = (RECIPE.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "gunicorn" in requirements
