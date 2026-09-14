"""Finds products already registered that look like a given one.

Used to avoid registering the same product twice and to show
"similar products" on the product page.
"""

import re
import sqlite3
import unicodedata
from dataclasses import dataclass

from monitor import db
from monitor.matching import same_code

# Words that say nothing about the product.
STOPWORDS = {"a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "para", "com", "sem", "por"}
SIMILARITY_THRESHOLD = 0.3


@dataclass
class SimilarProduct:
    id: int
    name: str
    image_url: str | None
    category_id: int
    category_name: str
    score: float  # 0.0 to 1.0
    same_code: bool


def normalize_text(text: str) -> str:
    """"Memória RAM" -> "memoria ram" (lowercase, no accents)."""
    # NFKD splits "ó" into "o" + accent mark; then we drop the marks.
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def name_tokens(name: str) -> set[str]:
    """"Memória RAM de 16GB" -> {"memoria", "ram", "16gb"}."""
    words = re.findall(r"[a-z0-9]+", normalize_text(name))
    return {word for word in words if len(word) >= 2 and word not in STOPWORDS}


def similarity(name_a: str, name_b: str) -> float:
    """Jaccard similarity: words in common / all different words of both names."""
    a, b = name_tokens(name_a), name_tokens(name_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_similar(
    conn: sqlite3.Connection,
    name: str,
    code: str | None = None,
    *,
    category_id: int | None = None,
    exclude_id: int | None = None,
    limit: int = 4,
) -> list[SimilarProduct]:
    """Products with the same code or a similar name.

    Order: same code first, then same category, then the most similar names.
    """
    found = []
    for product in db.list_products(conn):
        if product["id"] == exclude_id:
            continue
        has_same_code = bool(code and product["manufacturer_code"] and same_code(code, product["manufacturer_code"]))
        score = similarity(name, product["name"])
        if has_same_code or score >= SIMILARITY_THRESHOLD:
            found.append(
                SimilarProduct(
                    id=product["id"],
                    name=product["name"],
                    image_url=product["image_url"],
                    category_id=product["category_id"],
                    category_name=product["category_name"],
                    score=score,
                    same_code=has_same_code,
                )
            )

    found.sort(key=lambda p: (not p.same_code, p.category_id != category_id, -p.score))
    return found[:limit]
