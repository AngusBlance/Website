"""The SQLite store (website/server/store.py): request ids, storage format, and the
visitors view that merges the lakehouse's gold table with requests newer than it."""

import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

import website.server.main as main
from website.server import store

PAGE = store.PAGE
GOLD_COLUMNS = ("visitor_id", "visits", "first_seen_at", "last_seen_at", "country", "city", "lat", "lon",
                "user_agent", "is_bot", "is_cloud")


def log(ip="203.0.113.1", path=PAGE, ua="browser/1", lat=56.46, lon=-2.97, city="Dundee", at=None):
    record = {"method": "GET", "path": path, "ip": ip, "headers": {"user-agent": ua} if ua else {},
              "query_params": {}, "status_code": 200, "body_truncated": False,
              "request_started_at": datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc),
              "location": {"country": "United Kingdom", "city": city, "lat": lat, "lon": lon} if city else None}
    request_id = store.write_request(record)
    if at:  # pretend it was logged at another time
        with store.connect() as conn:
            conn.execute("UPDATE fast_api_requests SET timestamp = ? WHERE fast_api_request_id = ?", (at, request_id))
    return request_id


def publish_gold(rows, through_id):
    """What the lakehouse's daily sync does: replace gold_visitors and move the watermark."""
    with store.connect() as conn:
        conn.execute("DELETE FROM gold_visitors")
        conn.executemany(f"INSERT INTO gold_visitors VALUES ({', '.join('?' * len(GOLD_COLUMNS))})",
                         [tuple(r.get(c) for c in GOLD_COLUMNS) for r in rows])
        conn.execute("INSERT OR REPLACE INTO sync_state VALUES ('gold_through_id', ?, '2026-11-18')", (through_id,))


def visitors():
    return {r["visitor_id"]: r for r in store.select("SELECT * FROM visitors")}


def test_ids_continue_after_the_postgres_ids_and_never_restart():
    assert log() == "req_00010001" and log() == "req_00010002"
    with store.connect() as conn:
        conn.execute("DELETE FROM fast_api_requests")  # pruning everything must not reuse ids
    store.init()                                       # nor must a restart
    assert log() == "req_00010003"


def test_rows_are_stored_like_the_old_postgres_table():
    log()
    row = store.select("SELECT * FROM fast_api_requests")[0]
    assert json.loads(row["headers"]) == {"user-agent": "browser/1"}
    assert json.loads(row["location"])["city"] == "Dundee"
    assert row["request_started_at"] == "2026-11-18T12:00:00.000000+00:00"
    assert row["timestamp"].endswith("+00:00") and len(row["timestamp"]) == 32
    assert row["status_code"] == 200 and row["body_truncated"] == 0


def test_visitor_ids_match_the_lakehouse():
    # derive.visitor_id_of in database-projects gives this for 203.0.113.100
    assert store.visitor_id_of("203.0.113.100, 10.0.0.1") == store.visitor_id_of("203.0.113.100")
    assert store.visitor_id_of("203.0.113.100") == "661bf36ddc82d710eabe00c80b54d173"
    assert store.visitor_id_of(None) is None


def test_view_before_any_gold_is_just_the_recent_requests():
    log(at="2026-11-18T10:00:00.000000+00:00", ua="old-ua")
    log(at="2026-11-18T11:00:00.000000+00:00", ua="new-ua", lat=56.5, lon=-3.0)
    log(path="/")  # other pages don't count
    v = visitors()[store.visitor_id_of("203.0.113.1")]
    assert (v["visits"], v["first_seen_at"][:13], v["last_seen_at"][:13]) == (2, "2026-11-18T10", "2026-11-18T11")
    assert v["user_agent"] == "new-ua" and v["lat"] == 56.5 and v["lon"] == -3.0


def test_view_merges_gold_with_requests_newer_than_it_and_never_double_counts():
    me, other = store.visitor_id_of("203.0.113.1"), store.visitor_id_of("203.0.113.2")
    already_in_gold = log(at="2026-11-17T09:00:00.000000+00:00", ua="gold-ua")
    publish_gold([
        {"visitor_id": me, "visits": 10, "first_seen_at": "2026-09-01T00:00:00.000000+00:00",
         "last_seen_at": "2026-11-17T09:00:00.000000+00:00", "country": "United Kingdom", "city": "Dundee",
         "lat": 56.0, "lon": -3.0, "user_agent": "gold-ua", "is_bot": 0, "is_cloud": 0},
        {"visitor_id": other, "visits": 1, "first_seen_at": "2026-10-01T00:00:00.000000+00:00",
         "last_seen_at": "2026-10-01T00:00:00.000000+00:00", "country": None, "city": None,
         "lat": None, "lon": None, "user_agent": None, "is_bot": 1, "is_cloud": 1},
    ], through_id=already_in_gold)
    log(at="2026-11-18T12:00:00.000000+00:00", ua="new-ua", lat=57.0, lon=-3.0)  # newer than gold

    v = visitors()
    assert v[me]["visits"] == 11                       # 10 in gold + 1 new; the row gold has isn't counted again
    assert v[me]["first_seen_at"].startswith("2026-09-01") and v[me]["last_seen_at"].startswith("2026-11-18T12")
    assert v[me]["user_agent"] == "new-ua"
    assert v[me]["lat"] == round((56.0 * 10 + 57.0) / 11, 1)   # weighted by visits
    assert v[other]["visits"] == 1 and v[other]["lat"] is None


def test_api_visitors_shows_the_10_most_recent():
    for i in range(12):
        log(ip=f"203.0.113.{i}", at=f"2026-11-18T{i:02d}:00:00.000000+00:00", city=None, ua=None)
    with TestClient(main.app) as c:
        rows = c.get("/api/visitors").json()
    assert len(rows) == 10 and rows[0]["lastSeen"].startswith("2026-11-18T11")
    assert set(rows[0]) == {"visits", "firstSeen", "lastSeen", "country", "city", "lat", "lon", "userAgent"}
    assert rows[0]["country"] == "—" and rows[0]["userAgent"] == "—" and rows[0]["lat"] is None
    assert not any("203.0.113" in json.dumps(r) for r in rows)  # IPs never leave the server


def test_a_request_through_the_app_lands_in_sqlite(monkeypatch):
    async def no_lookup(ip):
        return None

    monkeypatch.setattr(main, "lookup_location", no_lookup)
    with TestClient(main.app) as c:
        c.get("/index.html", headers={"X-Forwarded-For": "203.0.113.9"})
        c.portal.call(main.request_log.wait_for_logs)
    row = store.select("SELECT * FROM fast_api_requests")[0]
    assert row["fast_api_request_id"] == "req_00010001" and row["path"] == "/index.html"
    assert row["ip"] == "203.0.113.9" and row["status_code"] == 200 and row["duration_ms"] > 0
    assert json.loads(row["scope"])["type"] == "http"
