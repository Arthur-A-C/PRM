from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, catalog, digitalizacao, health, pages, registration


settings = get_settings()
app = FastAPI(
    title="PRM",
    version="0.1.0",
    description="Dashboard interno de inteligência de catálogos e colaboração.",
)
app.mount("/static", StaticFiles(directory=Path("app/static")), name="static")
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(digitalizacao.router)
app.include_router(registration.router)
app.include_router(pages.router)  # Catch-all page route must follow the API routes.
