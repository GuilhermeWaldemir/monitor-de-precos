"""Guards a rule that a regular test can't check: two CSS blocks must stay identical.

style.css has dark-theme tokens in two places (explicit "dark" and "auto" + OS preference).
A future edit to one that forgets the other would make the two ways of getting dark mode
look different. This test extracts both blocks and compares them.
"""

import re
from pathlib import Path

from monitor.settings import CHOICES

STATIC_DIR = Path(__file__).parent.parent / "monitor" / "static"
CSS_PATH = STATIC_DIR / "style.css"


def _declarations(css: str, selector: str) -> str:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"selector not found in style.css: {selector}"
    return re.sub(r"\s+", " ", match.group(1)).strip()


def test_dark_theme_blocks_are_identical():
    css = CSS_PATH.read_text(encoding="utf-8")
    explicit_dark = _declarations(css, ':root[data-theme="dark"]')
    auto_dark = _declarations(css, ':root[data-theme="auto"]')

    assert explicit_dark  # sanity check: the block actually has content
    assert explicit_dark == auto_dark


def test_every_font_face_url_points_to_a_real_woff2_file():
    """Every @font-face src must resolve to a file that exists and really is a woff2
    (starts with the 4-byte magic number "wOF2"), not e.g. a 404 HTML page saved by mistake.
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    font_faces = re.findall(r"@font-face\s*\{([^}]*)\}", css)
    assert font_faces  # sanity check: there is at least one @font-face rule

    urls = []
    for block in font_faces:
        urls.extend(re.findall(r'url\(["\']?([^"\')]+)["\']?\)', block))
    assert urls

    for url in urls:
        path = STATIC_DIR / url
        assert path.is_file(), f"font file referenced in style.css does not exist: {url}"
        with open(path, "rb") as file:
            assert file.read(4) == b"wOF2", f"not a real woff2 file: {url}"


def test_every_font_choice_has_a_matching_css_rule():
    """Every non-default value in settings.CHOICES["font"] must have a :root[data-font="..."]
    rule in style.css, so a valid setting never silently does nothing.
    """
    css = CSS_PATH.read_text(encoding="utf-8")
    for value in CHOICES["font"]:
        if value == "default":
            continue  # "default" deliberately has no override: it just uses --font-system
        assert f':root[data-font="{value}"]' in css, f"missing CSS rule for font={value}"


def test_card_glow_only_shows_when_on_with_mouse_and_motion_allowed():
    """The glow layers start invisible; the only rule that shows them is inside the
    hover/reduced-motion media query and requires data-card-glow="on"."""
    css = CSS_PATH.read_text(encoding="utf-8")
    media = re.search(
        r"@media \(hover: hover\) and \(prefers-reduced-motion: no-preference\)\s*\{(.*?)\n\}", css, re.S
    )
    assert media, "card glow media query not found"
    assert ':root[data-card-glow="on"] .product-card:hover::before' in media.group(1)
    assert "opacity: 1" in media.group(1)
