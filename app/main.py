from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import auth, catalog, digitalizacao, health, operations, pages, registration
from app.routers import meetings, meeting_demo
from app.routers import datasheet_batches
from app.routers import store_integrations
from app.routers import store_registration
from app.routers import batch_publication
from app.routers import image_resolution
from app.routers import store_file_removal
from app.routers import accounts
from app.routers import local_uploads
from app.dependencies import require_module_access


settings = get_settings()
app = FastAPI(
    title="PRM",
    version="0.1.0",
    description="Dashboard interno de inteligência de catálogos e colaboração.",
)
app.mount("/static", StaticFiles(directory=Path("app/static")), name="static")
app.include_router(health.router)
app.include_router(auth.router)
for protected in (catalog, digitalizacao, datasheet_batches, store_integrations,
                  store_registration, batch_publication, image_resolution, local_uploads, store_file_removal, registration, operations, meetings, meeting_demo):
    app.include_router(protected.router, dependencies=[Depends(require_module_access)])
app.include_router(accounts.router)
app.include_router(pages.router)  # Catch-all page route must follow the API routes.
