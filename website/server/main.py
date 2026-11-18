import json
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg2.extras import Json
from database import DatabaseManager, tables
import uvicorn
import httpx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with DatabaseManager() as db:
        tables.fast_api_requests.create(db)
    yield


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
    try:
        await _log_request(request)
    except Exception:
        # A logging failure must never take down the page being requested.
        logger.exception("Failed to log %s %s", request.method, request.url.path)
    return await call_next(request)


async def _log_request(request: Request) -> None:
    body = await request.body()

    try:
        body_json = json.loads(body) if body else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Postgres JSONB cannot store NUL characters.
        body_json = body.decode("utf-8", errors="replace").replace("\x00", "")

    ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else None)
    location = None
    if ip:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}", timeout=3)
                location = resp.json()
        except Exception:
            pass

    with DatabaseManager() as db:
        log_entry = {
            "fast_api_request_id": tables.fast_api_requests.next_id(db),
            "method": request.method,
            "path": request.url.path,
            "ip": ip,
            "headers": dict(request.headers),
            "body": Json(body_json) if body_json is not None else None,
            "query_params": dict(request.query_params),
            "client_host": ip,
            "location": location,
        }
        db.append("raw.requests.fast_api_requests", log_entry)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
