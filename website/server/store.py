"""The website's own database: one SQLite file (data/website.db).

    fast_api_requests   every request, written by the logging middleware (request_log.py).
                        The lakehouse copies new rows to raw storage daily; rows are deleted
                        once they're in gold AND older than 2 days.
    gold_visitors       copy of the lakehouse table website.gold.visitors (everything up to
                        gold_through_id), replaced daily by the database platform.
    sync_state          gold_through_id: the newest request id included in gold_visitors.
    visitors (view)     gold_visitors + this page's requests newer than gold_through_id,
                        merged per visitor. /api/visitors reads it.

        website ──writes──▶ fast_api_requests ──daily──▶ raw ▶ bronze ▶ silver ▶ gold
           ▲                        │                                          │
           └──── visitors (view) ◀──┴──────────── gold_visitors ◀──daily copy──┘

The website_sqlite_sync DAG (database-projects) does the daily copy, the gold refresh and
the pruning; this file owns the schema. Visitors are pseudonymous: visitor_id() hashes
the IP exactly like the lakehouse does, so gold and recent rows line up.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(os.getenv("WEBSITE_DB") or Path(__file__).resolve().parents[2] / "data" / "website.db")

# Postgres (retired 2026-11-18) used ids up to about req_00008000; SQLite ids start at
# req_00010001 so the two never clash in the lakehouse.
IDS_START_AFTER = 10_000

PAGE = "/server_logging.html"

# Same columns as the old Postgres table. JSON values are stored as JSON text, times as
# ISO-8601 UTC text with microseconds (so text order = time order), booleans as 0/1.
COLUMNS: dict[str, str] = {
    "fast_api_request_id": "TEXT UNIQUE",
    "method": "TEXT NOT NULL",
    "path": "TEXT NOT NULL",
    "ip": "TEXT",
    "headers": "TEXT",
    "body": "TEXT",
    "query_params": "TEXT",
    "client_host": "TEXT",
    "location": "TEXT",
    "timestamp": "TEXT NOT NULL",
    "request_uuid": "TEXT",
    "request_started_at": "TEXT",
    "url": "TEXT",
    "scheme": "TEXT",
    "http_version": "TEXT",
    "query_string": "TEXT",
    "raw_headers": "TEXT",
    "client_port": "INTEGER",
    "body_size": "INTEGER",
    "body_content_type": "TEXT",
    "body_truncated": "INTEGER",
    "route": "TEXT",
    "endpoint": "TEXT",
    "path_params": "TEXT",
    "scope": "TEXT",
    "status_code": "INTEGER",
    "response_headers": "TEXT",
    "response_content_type": "TEXT",
    "response_size": "INTEGER",
    "time_to_headers_ms": "REAL",
    "duration_ms": "REAL",
    "error": "TEXT",
}
JSON_COLUMNS = frozenset({"headers", "body", "query_params", "location", "raw_headers", "path_params", "scope",
                          "response_headers"})
WRITABLE = [c for c in COLUMNS if c != "fast_api_request_id"]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS fast_api_requests (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    {", ".join(f'"{name}" {type_}' for name, type_ in COLUMNS.items())}
);
CREATE INDEX IF NOT EXISTS fast_api_requests_path ON fast_api_requests (path, fast_api_request_id);
CREATE INDEX IF NOT EXISTS fast_api_requests_timestamp ON fast_api_requests (timestamp);

CREATE TABLE IF NOT EXISTS gold_visitors (
    visitor_id TEXT PRIMARY KEY,
    visits INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    country TEXT,
    city TEXT,
    lat REAL,
    lon REAL,
    user_agent TEXT,
    is_bot INTEGER,
    is_cloud INTEGER
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO sqlite_sequence (name, seq)
SELECT 'fast_api_requests', {IDS_START_AFTER}
WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'fast_api_requests');

DROP VIEW IF EXISTS visitors;
CREATE VIEW visitors AS
WITH recent AS (            -- requests to the page that gold doesn't include yet
    SELECT visitor_id(ip)                            AS visitor_id,
           timestamp,
           json_extract(location, '$.country')       AS country,
           json_extract(location, '$.city')          AS city,
           json_extract(location, '$.lat')           AS lat,
           json_extract(location, '$.lon')           AS lon,
           json_extract(headers, '$."user-agent"')   AS user_agent
    FROM fast_api_requests
    WHERE path = '{PAGE}'
      AND fast_api_request_id > COALESCE((SELECT value FROM sync_state WHERE key = 'gold_through_id'), '')
),
both_ AS (                  -- one row per gold visitor + one row per recent request
    SELECT visitor_id, visits, first_seen_at, last_seen_at, country, city,
           lat * visits AS lat_sum, lon * visits AS lon_sum, IIF(lat IS NULL, 0, visits) AS located, user_agent
    FROM gold_visitors
    UNION ALL
    SELECT visitor_id, 1, timestamp, timestamp, country, city, lat, lon, IIF(lat IS NULL, 0, 1), user_agent
    FROM recent
)
SELECT
    visitor_id,
    SUM(visits)                                       AS visits,
    MIN(first_seen_at)                                AS first_seen_at,
    MAX(last_seen_at)                                 AS last_seen_at,
    MAX(country)                                      AS country,
    MAX(city)                                         AS city,
    ROUND(SUM(lat_sum) / NULLIF(SUM(located), 0), 1)  AS lat,
    ROUND(SUM(lon_sum) / NULLIF(SUM(located), 0), 1)  AS lon,
    (SELECT b.user_agent FROM both_ b WHERE b.visitor_id IS a.visitor_id
     ORDER BY b.last_seen_at DESC LIMIT 1)            AS user_agent
FROM both_ a
GROUP BY visitor_id;
"""


def visitor_id_of(ip: str | None) -> str | None:
    """Pseudonymous visitor id; must match derive.visitor_id_of in database-projects."""
    if not ip:
        return None
    first = ip.split(",")[0].strip()
    return hashlib.sha256(f"website-visitor:{first}".encode()).hexdigest()[:32]


def iso(dt: datetime) -> str:
    """UTC, always with microseconds: '2026-11-18T10:47:01.289249+00:00'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.create_function("visitor_id", 1, visitor_id_of, deterministic=True)
    return conn


def init(path: Path | str | None = None) -> None:
    """Create the file, tables and view if needed (safe on every start)."""
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")  # readers never block the writer
        conn.executescript(SCHEMA)
    conn.close()


def _value(name: str, value: Any) -> Any:
    if value is None:
        return None
    if name in JSON_COLUMNS:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime):
        return iso(value)
    return value


def write_request(record: dict[str, Any], path: Path | str | None = None) -> str:
    """Insert one logged request; returns its id (req_00010001, ...)."""
    row = {c: _value(c, record.get(c)) for c in WRITABLE}
    row["timestamp"] = iso(datetime.now(timezone.utc))
    columns = ", ".join(f'"{c}"' for c in row)
    conn = connect(path)
    try:
        with conn:  # one transaction: insert, then derive the id from the row's sequence number
            cur = conn.execute(f"INSERT INTO fast_api_requests ({columns}) VALUES ({', '.join('?' * len(row))})",
                               list(row.values()))
            request_id = f"req_{cur.lastrowid:08d}"
            conn.execute("UPDATE fast_api_requests SET fast_api_request_id = ? WHERE seq = ?",
                         (request_id, cur.lastrowid))
        return request_id
    finally:
        conn.close()


def select(query: str, params: tuple = (), path: Path | str | None = None) -> list[dict[str, Any]]:
    conn = connect(path)
    try:
        return [dict(r) for r in conn.execute(query, params)]
    finally:
        conn.close()
