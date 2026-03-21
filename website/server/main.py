import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI()

app.mount("/stylesheets", StaticFiles(directory=os.path.join(BASE_DIR, "stylesheets")), name="stylesheets")
app.mount("/scripts", StaticFiles(directory=os.path.join(BASE_DIR, "scripts")), name="scripts")
app.mount("/component", StaticFiles(directory=os.path.join(BASE_DIR, "component")), name="component")


@app.get("/")
@app.get("/index.html")
def index():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))


@app.get("/differentiation.html")
def differentiation():
    return FileResponse(os.path.join(BASE_DIR, "differentiation.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
