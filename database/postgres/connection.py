from __future__ import annotations

from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from .postgres import DB_CONFIG


class DatabaseManager:
    def __init__(self, db_config: dict | None = None):
        self._config = db_config or DB_CONFIG
        self._conn = None

    def __enter__(self) -> DatabaseManager:
        self._conn = psycopg2.connect(**self._config)
        return self

    def __exit__(self, *args):
        if self._conn:
            self._conn.close()

    def select(self, query: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(query, params)
        return cur.fetchall()

    def append(self, table: str, data: dict | list[dict]) -> None:
        if isinstance(data, dict):
            data = [data]
        cols = list(data[0].keys())
        placeholders = ", ".join(["%s"] * len(cols))
        query = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
        values = [[row[col] for col in cols] for row in data]
        cur = self._conn.cursor()
        cur.executemany(query, values)
        self._conn.commit()

    def execute(self, query: str, params: tuple = ()) -> None:
        cur = self._conn.cursor()
        cur.execute(query, params)
        self._conn.commit()
