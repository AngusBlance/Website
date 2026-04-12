import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from database import DatabaseManager, tables
import uvicorn

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()

    try:
        body_json = json.loads(body) if body else None
    except json.JSONDecodeError:
        body_json = body.decode("utf-8") if body else None

    with DatabaseManager() as db:
        log_entry = {
            "fast_api_request_id": tables.fast_api_requests.next_id(db),
            "method": request.method,
            "path": request.url.path,
            "ip": request.client.host if request.client else None,
            "headers": dict(request.headers),
            "body": body_json,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
        }
        db.append("raw.requests.fast_api_requests", log_entry)

    response = await call_next(request)
    return response


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
