from database.postgres.connection import DatabaseManager

# One row per HTTP request. The first block is the original table; everything after
# "full request/response capture" was added later and is NULL on older rows.
FAST_API_REQUESTS_SCHEMA = {
    "full_name": "raw.fast_api_requests",
    "columns": {
        "fast_api_request_id": {"type": "TEXT", "not_null": True, "primary_key": True},
        "method": {"type": "TEXT", "not_null": True},
        "path": {"type": "TEXT", "not_null": True},
        "ip": {"type": "TEXT"},
        "headers": {"type": "JSONB"},
        "body": {"type": "JSONB"},
        "query_params": {"type": "JSONB"},
        "client_host": {"type": "TEXT"},
        "location": {"type": "JSONB"},
        "timestamp": {"type": "TIMESTAMPTZ", "default": "NOW()"},
        # ---- full request/response capture -------------------------------------------------
        "request_uuid": {"type": "TEXT"},
        "request_started_at": {"type": "TIMESTAMPTZ"},
        "url": {"type": "TEXT"},
        "scheme": {"type": "TEXT"},
        "http_version": {"type": "TEXT"},
        "query_string": {"type": "TEXT"},
        "raw_headers": {"type": "JSONB"},
        "client_port": {"type": "INTEGER"},
        "body_size": {"type": "INTEGER"},
        "body_content_type": {"type": "TEXT"},
        "body_truncated": {"type": "BOOLEAN"},
        "route": {"type": "TEXT"},
        "endpoint": {"type": "TEXT"},
        "path_params": {"type": "JSONB"},
        "scope": {"type": "JSONB"},
        "status_code": {"type": "INTEGER"},
        "response_headers": {"type": "JSONB"},
        "response_content_type": {"type": "TEXT"},
        "response_size": {"type": "BIGINT"},
        "time_to_headers_ms": {"type": "DOUBLE PRECISION"},
        "duration_ms": {"type": "DOUBLE PRECISION"},
        "error": {"type": "TEXT"},
    },
}

JSONB_COLUMNS = frozenset(n for n, c in FAST_API_REQUESTS_SCHEMA["columns"].items() if c["type"] == "JSONB")


def create(db: DatabaseManager) -> None:
    """Create the table if needed and add any columns it's missing (runs on every start)."""
    db.execute("CREATE SEQUENCE IF NOT EXISTS fast_api_requests_id_seq")
    db.create_table(FAST_API_REQUESTS_SCHEMA)
    db.add_missing_columns(FAST_API_REQUESTS_SCHEMA)


def next_id(db: DatabaseManager) -> str:
    result = db.select("SELECT nextval('fast_api_requests_id_seq')")
    num = result[0]["nextval"]
    return f"req_{num:08d}"
