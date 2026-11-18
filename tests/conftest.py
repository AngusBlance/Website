import pytest

from website.server import store


@pytest.fixture(autouse=True)
def temporary_database(tmp_path, monkeypatch):
    """Every test gets its own empty SQLite file (the app creates the schema on start)."""
    path = tmp_path / "website.db"
    monkeypatch.setattr(store, "DB_PATH", path)
    store.init(path)
    return path
