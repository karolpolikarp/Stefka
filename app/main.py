import logging
import logging.handlers

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import LOG_FILE
from app.routers import upload, status, download
from app.services.llm import check_ollama_health


def _setup_logging():
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — rotates at 5 MB, keeps 3 backups
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)


_setup_logging()

app = FastAPI(
    title="Stefka",
    description="Lokalna aplikacja do transkrypcji audio i strukturyzowania notatek",
    version="1.0.0",
)

# Mount static files
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Include routers
app.include_router(upload.router)
app.include_router(status.router)
app.include_router(download.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    ollama_ok = await check_ollama_health()
    return {
        "status": "ok" if ollama_ok else "degraded",
        "ollama": ollama_ok,
    }
