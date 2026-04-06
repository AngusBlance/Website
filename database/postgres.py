from __future__ import annotations

import os
from typing import Any, Optional, Tuple

import psycopg2
from psycopg2 import extensions

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "mydatabase"),
}
