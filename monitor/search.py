"""Search products already registered, by name or code."""

import sqlite3

from monitor import db
from monitor.matching import normalize_code
from monitor.similar import name_tokens, normalize_text

MAX_QUERY_LENGTH = 100
MIN_CODE_LENGTH = 3  # avoid "16" matching every code that has "16" in it


def search_products(conn: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Products whose name has every word of the query, or whose code contains the query.

    Ignores case, accents and small words: "memoria king" finds "Memória Kingston".
    Parts of words count too ("king" finds "Kingston"). Newest products first.
    """
    query = query.strip()[:MAX_QUERY_LENGTH]
    words = name_tokens(query)
    code = normalize_code(query)
    if not words and len(code) < MIN_CODE_LENGTH:
        return []

    results = []
    for product in db.list_products(conn):
        name = normalize_text(product["name"])
        name_match = bool(words) and all(word in name for word in words)
        product_code = normalize_code(product["manufacturer_code"] or "")
        code_match = len(code) >= MIN_CODE_LENGTH and code in product_code
        if name_match or code_match:
            results.append(product)
    return results
