"""Shared pytest fixtures (pytest loads this file automatically)."""

import pytest

from monitor import db


@pytest.fixture
def conn(tmp_path):
    """A fresh database in a temporary folder for each test."""
    connection = db.connect(tmp_path / "test.db")
    db.init_db(connection)
    yield connection
    connection.close()
