"""Checks whether a store page is really the product we want.

Names change from store to store, but identification codes do not:
- manufacturer code (part number), e.g. KF432C16BB1/16 -> JSON-LD "mpn";
- EAN (barcode), e.g. 7891234567895 -> JSON-LD "gtin13".
Similar codes are different products: KF432C16BB1/16 and KF432C16BB/16
are two different memory modules.
"""

import re

_TOKEN_SEPARATORS = re.compile(r"[\s,;()\[\]|]+")
_EAN = re.compile(r"\d{8,14}")


def normalize_code(code: str) -> str:
    """"kf432c16bb1/16" -> "KF432C16BB116" (only letters and digits, uppercase)."""
    return re.sub(r"[^A-Za-z0-9]", "", code).upper()


def looks_like_ean(code: str) -> bool:
    """EAN/GTIN barcodes have only digits: 8, 12, 13 or 14 of them."""
    return _EAN.fullmatch(normalize_code(code)) is not None


def same_code(a: str, b: str) -> bool:
    """Compare two codes. Barcodes ignore leading zeros (GTIN-14 "0740..." = EAN-13 "740...")."""
    a, b = normalize_code(a), normalize_code(b)
    if a.isdigit() and b.isdigit():
        a, b = a.lstrip("0"), b.lstrip("0")
    return bool(a) and a == b


def title_has_code(title: str, code: str) -> bool:
    """True when some word of the title is exactly the code.

    Compares whole words, not substrings, so "KF432C16BB1/16WP" does not
    count as "KF432C16BB1/16".
    """
    if not normalize_code(code):
        return False
    return any(same_code(token, code) for token in _TOKEN_SEPARATORS.split(title))


def code_matches(
    code: str | None,
    page_code: str | None = None,
    page_gtin: str | None = None,
    page_title: str | None = None,
) -> bool | None:
    """Is the store page the product with this code?

    True  = confirmed (the page's mpn, gtin or a word of its title is the code).
    False = the page declares a different code of the same kind.
    None  = could not confirm (no code registered, or the page shows none).
    """
    if not code or not normalize_code(code):
        return None
    if any(same_code(declared, code) for declared in (page_code, page_gtin) if declared):
        return True
    if page_title and title_has_code(page_title, code):
        return True

    # Only say "different" when comparing like with like: EAN vs gtin, part number vs mpn.
    same_kind = page_gtin if looks_like_ean(code) else page_code
    return False if same_kind else None
