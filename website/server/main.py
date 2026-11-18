import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from website.server import request_log, store
import uvicorn
import httpx

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()  # creates data/website.db, its tables and the visitors view if needed
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


# The `visitors` view (store.py) merges the lakehouse's gold table with requests newer than
# it, grouped by pseudonymous visitor, so IPs, headers and request bodies never leave the
# server. Coordinates are rounded to city level.
VISITORS_QUERY = """
    SELECT
        visits                     AS "visits",
        first_seen_at              AS "firstSeen",
        last_seen_at               AS "lastSeen",
        COALESCE(country, '—')     AS "country",
        COALESCE(city, '—')        AS "city",
        lat                        AS "lat",
        lon                        AS "lon",
        COALESCE(user_agent, '—')  AS "userAgent"
    FROM visitors
    ORDER BY last_seen_at DESC
    LIMIT 10
"""


@app.get("/api/visitors")
def visitors():
    return store.select(VISITORS_QUERY)


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


async def persist(record: dict) -> None:
    """Runs in the background after the response: location lookup, then the insert."""
    record["location"] = await lookup_location(record.get("ip"))
    await asyncio.to_thread(store.write_request, record)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
