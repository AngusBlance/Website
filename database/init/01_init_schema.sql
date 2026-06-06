CREATE SCHEMA IF NOT EXISTS raw;

CREATE SEQUENCE IF NOT EXISTS fast_api_requests_id_seq;

CREATE TABLE IF NOT EXISTS raw.fast_api_requests (
    fast_api_request_id TEXT PRIMARY KEY NOT NULL,
    method              TEXT NOT NULL,
    path                TEXT NOT NULL,
    ip                  TEXT,
    headers             JSONB,
    body                JSONB,
    query_params        JSONB,
    client_host         TEXT,
    location            JSONB,
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);
