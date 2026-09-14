"""The fixed list of icons a category can use.

Single source of truth: both the create/edit forms (icon picker) and the server-side
validation in monitor/db.py read from CATEGORY_ICONS, so a name typed by hand in a form
that isn't in this dict is always rejected. The SVGs themselves live in
monitor/templates/_icons.html (one Jinja macro branch per name here).
"""

# Order here is the order icons appear in the picker. Labels are Portuguese because
# they double as the accessible name (title/sr-only text) shown to the user.
CATEGORY_ICONS = {
    "tag": "Geral",
    "cpu": "Eletrônicos",
    "smartphone": "Celulares",
    "headphones": "Áudio",
    "gamepad-2": "Games",
    "shirt": "Roupas",
    "droplet": "Perfumes",
    "sparkles": "Beleza",
    "house": "Casa",
    "utensils": "Cozinha",
    "sofa": "Móveis",
    "wrench": "Ferramentas",
    "car": "Automotivo",
    "dumbbell": "Esportes",
    "book-open": "Livros",
    "baby": "Bebês",
    "paw-print": "Pets",
    "gift": "Presentes",
    "watch": "Relógios",
    "heart": "Favoritos",
}

DEFAULT_CATEGORY_ICON = "tag"
