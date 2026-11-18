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
    timestamp           TIMESTAMPTZ DEFAULT NOW(),
    -- full request/response capture (added later; the app also adds these on start)
    request_uuid          TEXT,
    request_started_at    TIMESTAMPTZ,
    url                   TEXT,
    scheme                TEXT,
    http_version          TEXT,
    query_string          TEXT,
    raw_headers           JSONB,
    client_port           INTEGER,
    body_size             INTEGER,
    body_content_type     TEXT,
    body_truncated        BOOLEAN,
    route                 TEXT,
    endpoint              TEXT,
    path_params           JSONB,
    scope                 JSONB,
    status_code           INTEGER,
    response_headers      JSONB,
    response_content_type TEXT,
    response_size         BIGINT,
    time_to_headers_ms    DOUBLE PRECISION,
    duration_ms           DOUBLE PRECISION,
    error                 TEXT
);
