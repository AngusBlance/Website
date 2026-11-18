import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg2.extras import Json
from database import DatabaseManager, tables
from website.server import request_log
import uvicorn
import httpx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with DatabaseManager() as db:
        tables.fast_api_requests.create(db)  # creates the table, or adds columns it's missing
    yield
    await request_log.wait_for_logs()  # finish writing logs of the last requests before exiting


app = FastAPI(lifespan=lifespan)


app.mount(
    "/stylesheets",
    StaticFiles(directory=os.path.join(BASE_DIR, "stylesheets")),
    name="stylesheets",
)
app.mount(
    "/scripts", StaticFiles(directory=os.path.join(BASE_DIR, "scripts")), name="scripts"
)
app.mount(
    "/component",
    StaticFiles(directory=os.path.join(BASE_DIR, "component")),
    name="component",
)


@app.get("/")
@app.get("/index.html")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.get("/differentiation.html")
def differentiation():
    return FileResponse(os.path.join(BASE_DIR, "differentiation.html"))


@app.get("/server_logging.html")
def server_logging():
    return FileResponse(os.path.join(BASE_DIR, "server_logging.html"))


# Visitors are grouped by IP in the database so that IPs, headers and request
# bodies never leave the server. Coordinates are rounded to city level.
VISITORS_QUERY = """
    SELECT
        COUNT(*) AS "visits",
        MIN(timestamp) AS "firstSeen",
        MAX(timestamp) AS "lastSeen",
        COALESCE(MAX(location->>'country'), '—') AS "country",
        COALESCE(MAX(location->>'city'), '—') AS "city",
        ROUND(AVG((location->>'lat')::numeric), 1) AS "lat",
        ROUND(AVG((location->>'lon')::numeric), 1) AS "lon",
        COALESCE((ARRAY_AGG(headers->>'user-agent' ORDER BY timestamp DESC))[1], '—') AS "userAgent"
    FROM raw.fast_api_requests
    WHERE path = '/server_logging.html'
    GROUP BY ip
    ORDER BY "lastSeen" DESC
    LIMIT 10
"""


@app.get("/api/visitors")
def visitors():
    with DatabaseManager() as db:
        return db.select(VISITORS_QUERY)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Logs the request and its response after the response is sent; see request_log.py
    return await request_log.capture(request, call_next, persist)


async def lookup_location(ip: str | None) -> dict | None:
    """ip-api.com lookup for the visitor's IP (the first address in X-Forwarded-For)."""
    first = ip.split(",")[0].strip() if ip else None
    if not first:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://ip-api.com/json/{first}", timeout=3)
            return resp.json()
    except Exception:
        return None


def write_row(record: dict) -> None:
    """Insert one request into raw.fast_api_requests (blocking; run in a thread)."""
    jsonb = tables.fast_api_requests.JSONB_COLUMNS
    row = {k: (Json(v) if k in jsonb and v is not None else v) for k, v in record.items()}
    with DatabaseManager() as db:
        row["fast_api_request_id"] = tables.fast_api_requests.next_id(db)
        db.append("raw.fast_api_requests", row)


async def persist(record: dict) -> None:
    """Runs in the background after the response: location lookup, then the insert."""
    record["location"] = await lookup_location(record.get("ip"))
    await asyncio.to_thread(write_row, record)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
