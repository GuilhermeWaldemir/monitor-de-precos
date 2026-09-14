import pytest

from monitor import db
from monitor.similar import find_similar, name_tokens, similarity
from tests.helpers import CLOTHING_ID, ELECTRONICS_ID, KABUM_URL, PERFUMES_ID, RAM_CODE

RAM = "Memória Kingston Fury Beast 16GB DDR4 3200MHz CL16"


def test_name_tokens_ignore_accents_case_and_stopwords():
    assert name_tokens("Memória RAM de 16GB, para PC") == {"memoria", "ram", "16gb", "pc"}


def test_same_name_is_fully_similar():
    assert similarity(RAM, RAM.upper()) == 1.0


def test_similar_ram_names():
    assert similarity(RAM, "Memoria RAM Kingston Fury Beast 16GB 3200MHz") >= 0.5


def test_unrelated_products():
    assert similarity(RAM, "Perfume Malbec Eau de Toilette 100ml") == 0.0


@pytest.mark.parametrize("empty", ["", "de para com", "!!!"])
def test_empty_names_are_not_similar(empty):
    assert similarity(RAM, empty) == 0.0


def add(conn, name, category_id=ELECTRONICS_ID, code=None):
    return db.create_product(conn, name=name, category_id=category_id, urls=[KABUM_URL], manufacturer_code=code)


def test_find_similar_by_name_and_code(conn):
    ram_id = add(conn, RAM, code=RAM_CODE)
    other_name_id = add(conn, "Pente de memória genérico", code="kf432c16bb1-16")  # same code, other name
    add(conn, "Perfume Malbec 100ml", PERFUMES_ID)

    found = find_similar(conn, "Memoria Kingston Fury Beast 16GB", RAM_CODE)

    assert [p.id for p in found] == [ram_id, other_name_id]
    assert all(p.same_code for p in found)


def test_find_similar_excludes_the_product_itself_and_prefers_same_category(conn):
    ram_id = add(conn, RAM)
    shirt_id = add(conn, "Kingston Fury Beast camiseta 16GB", CLOTHING_ID)
    similar_ram_id = add(conn, "Kingston Fury Beast 16GB DDR4")

    found = find_similar(conn, RAM, category_id=ELECTRONICS_ID, exclude_id=ram_id)

    assert ram_id not in [p.id for p in found]
    assert [p.id for p in found] == [similar_ram_id, shirt_id]


def test_find_similar_respects_limit(conn):
    for i in range(6):
        add(conn, f"{RAM} v{i}")
    assert len(find_similar(conn, RAM, limit=4)) == 4
