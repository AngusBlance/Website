from database.postgres.connection import DatabaseManager

FAST_API_REQUESTS_SCHEMA = {
    "full_name": "raw.requests.fast_api_requests",
    "columns": {
        "fast_api_request_id": {"type": "TEXT", "not_null": True, "primary_key": True},
        "method": {"type": "TEXT", "not_null": True},
        "path": {"type": "TEXT", "not_null": True},
        "ip": {"type": "TEXT"},
        "headers": {"type": "JSONB"},
        "body": {"type": "JSONB"},
        "query_params": {"type": "JSONB"},
        "client_host": {"type": "TEXT"},
        "timestamp": {"type": "TIMESTAMPTZ", "default": "NOW()"},
    },
}


def create(db: DatabaseManager) -> None:
    db.execute("CREATE SEQUENCE IF NOT EXISTS fast_api_requests_id_seq")
    db.create_table(FAST_API_REQUESTS_SCHEMA)


def next_id(db: DatabaseManager) -> str:
    result = db.select("SELECT nextval('fast_api_requests_id_seq')")
    num = result[0]["nextval"]
    return f"req_{num:08d}"
