from __future__ import annotations

import json
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
        quoted_cols = [f'"{col}"' for col in cols]
        query = (
            f'INSERT INTO "{table}" ({", ".join(quoted_cols)}) VALUES ({placeholders})'
        )
        values = []
        for row in data:
            row_values = []
            for col in cols:
                val = row[col]
                if isinstance(val, (dict, list)):
                    val = json.dumps(val)
                row_values.append(val)
            values.append(row_values)
        cur = self._conn.cursor()
        cur.executemany(query, values)
        self._conn.commit()

    def execute(self, query: str, params: tuple = ()) -> None:
        cur = self._conn.cursor()
        cur.execute(query, params)
        self._conn.commit()

    def create_table(self, schema: dict) -> None:
        full_name = schema["full_name"]
        parts = full_name.split(".")

        for i in range(len(parts) - 1):
            schema_name = ".".join(parts[: i + 1])
            self.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')

        columns = []
        for col_name, col_def in schema["columns"].items():
            col_sql = f'"{col_name}" {col_def["type"]}'
            if col_def.get("primary_key"):
                col_sql += " PRIMARY KEY"
            if col_def.get("not_null"):
                col_sql += " NOT NULL"
            if col_def.get("default"):
                col_sql += f" DEFAULT {col_def['default']}"
            columns.append(col_sql)

        table_name = ".".join(parts)
        query = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({", ".join(columns)})'
        self.execute(query)
