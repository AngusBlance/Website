"""Request/response capture (website/server/request_log.py), through the real app.

`persist` is swapped for one that records the row in a list instead of writing it, so
no network is needed; the SQLite file is a temporary one (see conftest.py).
"""

import asyncio
import time
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import website.server.main as main
from website.server import request_log, store


@pytest.fixture
def logged(monkeypatch):
    """The app with logging captured into a list (no database)."""
    rows: list[dict] = []

    async def persist(record):
        rows.append(record)

    monkeypatch.setattr(main, "persist", persist)
    return rows


@contextmanager
def client():
    with TestClient(main.app) as c:
        yield c
        c.portal.call(request_log.wait_for_logs)


def only(rows):
    assert len(rows) == 1, rows
    return rows[0]


def test_page_request_and_response_are_captured(logged):
    with client() as c:
        resp = c.get("/index.html?ref=home", headers={"User-Agent": "pytest-browser", "X-Forwarded-For": "203.0.113.7"})
    row = only(logged)
    assert resp.status_code == 200
    assert row["method"] == "GET" and row["path"] == "/index.html"
    assert row["url"] == "http://testserver/index.html?ref=home" and row["scheme"] == "http"
    assert row["http_version"] == "1.1"
    assert row["query_string"] == "ref=home" and row["query_params"] == {"ref": "home"}
    assert row["ip"] == "203.0.113.7" and row["client_host"] == "testclient" and row["client_port"] == 50000
    assert row["headers"]["user-agent"] == "pytest-browser"
    assert row["route"] == "/index.html" and row["endpoint"] == "index" and row["path_params"] == {}
    assert row["status_code"] == 200 and row["response_content_type"].startswith("text/html")
    assert row["response_size"] == len(resp.content)
    assert 0 <= row["time_to_headers_ms"] <= row["duration_ms"]
    assert row["request_started_at"].tzinfo is not None
    assert uuid.UUID(row["request_uuid"]).version == 4
    assert row["scope"]["type"] == "http" and row["scope"]["server"] == ["testserver", 80]
    assert row["body"] is None and row["body_size"] == 0 and row["body_truncated"] is False


def test_static_files_and_404s_are_captured(logged):
    with client() as c:
        c.get("/stylesheets/main.css")
        c.get("/does-not-exist")
    css, missing = sorted(logged, key=lambda r: r["path"], reverse=True)
    assert css["status_code"] == 200 and css["response_size"] > 0 and css["response_content_type"].startswith("text/css")
    assert css["route"] == "/stylesheets/{path}"
    assert missing["status_code"] == 404 and missing["route"] is None


def test_secret_headers_are_redacted_but_kept_by_name(logged):
    with client() as c:
        c.get("/", headers=[("Cookie", "session=abc"), ("Authorization", "Bearer xyz"), ("X-Api-Key", "k"),
                            ("X-Session-Id", "s1"), ("Accept", "text/html"), ("Accept", "application/json")])
    row = only(logged)
    for name in ("cookie", "authorization", "x-api-key", "x-session-id"):
        assert row["headers"][name] == "[redacted]"
    assert ["accept", "text/html"] in row["raw_headers"] and ["accept", "application/json"] in row["raw_headers"]
    assert row["headers"]["accept"] == "text/html, application/json"
    assert not any("abc" in v or "xyz" in v for _, v in row["raw_headers"])


def test_response_set_cookie_is_redacted():
    pairs = [("set-cookie", "id=1"), ("content-type", "text/plain")]
    assert request_log.redact_dict(pairs) == {"set-cookie": "[redacted]", "content-type": "text/plain"}


def test_small_bodies_are_kept_big_ones_only_measured(logged):
    with client() as c:
        c.post("/api/visitors", json={"hello": "world"})
        c.post("/api/visitors", content=b"x" * (request_log.BODY_LIMIT + 1), headers={"Content-Type": "text/plain"})
    small, big = sorted(logged, key=lambda r: r["body_size"])
    assert small["body"] == {"hello": "world"} and small["body_content_type"] == "application/json"
    assert small["status_code"] == 405  # GET-only endpoint: still logged
    assert big["body"] is None and big["body_truncated"] is True and big["body_size"] == request_log.BODY_LIMIT + 1


def test_text_bodies_lose_nul_characters():
    assert request_log.body_fields(b"a\x00b", "text/plain")["body"] == "ab"


def test_an_error_in_the_app_is_logged_as_a_500(logged):
    async def boom():
        raise RuntimeError("kaboom")

    main.app.add_api_route("/__boom", boom)
    try:
        with TestClient(main.app, raise_server_exceptions=False) as c:
            assert c.get("/__boom").status_code == 500
            c.portal.call(request_log.wait_for_logs)
    finally:
        main.app.router.routes.pop()
    row = only(logged)
    assert row["status_code"] == 500 and row["error"] == "RuntimeError: kaboom" and row["route"] == "/__boom"


def test_pages_never_wait_for_logging(logged, monkeypatch):
    async def slow_persist(record):
        await asyncio.sleep(1.5)
        logged.append(record)

    monkeypatch.setattr(main, "persist", slow_persist)
    with TestClient(main.app) as c:
        t0 = time.perf_counter()
        assert c.get("/").status_code == 200
        assert time.perf_counter() - t0 < 1.0, "the page waited for logging"
        c.portal.call(request_log.wait_for_logs)
    assert only(logged)["path"] == "/"


def test_logging_failures_never_break_pages(logged, monkeypatch):
    async def broken_persist(record):
        raise ConnectionError("database down")

    monkeypatch.setattr(main, "persist", broken_persist)
    with client() as c:
        assert c.get("/").status_code == 200

    monkeypatch.setattr(request_log, "request_fields", lambda *a: 1 / 0)
    with client() as c:
        assert c.get("/").status_code == 200


def test_every_captured_field_is_a_table_column(logged):
    with client() as c:
        c.get("/")
    assert set(only(logged)) <= set(store.COLUMNS)
